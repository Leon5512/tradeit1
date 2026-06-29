# ══════════════════════════════════════════════════════
# СИСТЕМА ТЕХПОДДЕРЖКИ — вставь эти маршруты в app.py
# Замени старый блок "# ── Техподдержка ──" на этот
# ══════════════════════════════════════════════════════

SUPPORT_CATEGORIES = {
    "payment":   "💳 Оплата и кошелёк",
    "ad":        "📋 Объявления",
    "account":   "👤 Аккаунт",
    "message":   "✉️ Сообщения",
    "bug":       "🐛 Ошибка на сайте",
    "other":     "💬 Другое",
}

SUPPORT_PRIORITIES = {
    "low":    ("🟢", "Низкий"),
    "normal": ("🟡", "Обычный"),
    "high":   ("🔴", "Высокий"),
}

SUPPORT_STATUSES = {
    "open":        ("🟠", "Открыт"),
    "in_progress": ("🔵", "В работе"),
    "resolved":    ("🟢", "Решён"),
    "closed":      ("⚫", "Закрыт"),
}

AI_SYSTEM_PROMPT = """Ты — вежливый сотрудник технической поддержки сайта TradeIt.
TradeIt — это маркетплейс для продажи вещей (как Авито).

Возможности сайта:
- Регистрация и вход (с 2FA)
- Публикация объявлений с фото, ценой, городом и категорией
- Поиск и фильтрация объявлений
- Личные сообщения между пользователями
- Встроенный мессенджер (TradeIt Messenger)
- Кошелёк и пополнение баланса
- Покупка товаров прямо на сайте
- Отзывы о продавцах
- Избранные объявления
- Настройки профиля (аватар, биография, город, цвет акцента)

Отвечай коротко, по делу, дружелюбно, на русском языке.
Если не знаешь ответа — напиши, что передашь вопрос живому оператору."""


# ── Список тикетов пользователя ──────────────────────
@app.route("/support")
def support():
    if "user_id" not in session:
        return redirect(url_for("login"))
    uid = session["user_id"]
    db = get_db()
    tickets = db.execute(
        "SELECT * FROM support_tickets_v2 WHERE user_id=? ORDER BY updated_at DESC",
        (uid,)
    ).fetchall()
    unread = {}
    for t in tickets:
        cnt = db.execute(
            "SELECT COUNT(*) FROM support_messages WHERE ticket_id=? AND is_admin=1 AND created_at > ?",
            (t["id"], t.get("last_read_at", 0) or 0)
        ).fetchone()[0]
        unread[t["id"]] = cnt
    return render_template("support.html",
                           tickets=tickets,
                           categories=SUPPORT_CATEGORIES,
                           priorities=SUPPORT_PRIORITIES,
                           statuses=SUPPORT_STATUSES,
                           unread=unread)


# ── Создание нового тикета ───────────────────────────
@app.route("/support/new", methods=["GET", "POST"])
def support_new():
    if "user_id" not in session:
        return redirect(url_for("login"))
    if request.method == "POST":
        title    = request.form.get("title", "").strip()[:200]
        category = request.form.get("category", "other")
        priority = request.form.get("priority", "normal")
        message  = request.form.get("message", "").strip()
        if not title or not message:
            flash("Заполни все поля", "error")
            return redirect(url_for("support_new"))
        if category not in SUPPORT_CATEGORIES:
            category = "other"
        if priority not in SUPPORT_PRIORITIES:
            priority = "normal"
        uid = session["user_id"]
        db  = get_db()
        now = int(time.time())
        ticket_id = db.execute(
            "INSERT INTO support_tickets_v2 (user_id,title,category,priority,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?)",
            (uid, title, category, priority, "open", now, now)
        ).lastrowid
        db.execute(
            "INSERT INTO support_messages (ticket_id,user_id,is_admin,message,created_at) VALUES (?,?,0,?,?)",
            (ticket_id, uid, message, now)
        )
        # AI-ответ
        try:
            resp = http_requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY', '')}"
                },
                json={
                    "model": "meta-llama/llama-3.1-8b-instruct:free",
                    "messages": [
                        {"role": "system", "content": AI_SYSTEM_PROMPT},
                        {"role": "user",   "content": f"Тема: {title}\n\n{message}"}
                    ]
                },
                timeout=15
            )
            ai_text = resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            print("SUPPORT AI ERROR:", e)
            ai_text = "Спасибо за обращение! Мы рассмотрим ваш вопрос в ближайшее время."
        db.execute(
            "INSERT INTO support_messages (ticket_id,user_id,is_admin,message,created_at) VALUES (?,?,1,?,?)",
            (ticket_id, uid, ai_text, now + 1)
        )
        db.execute(
            "UPDATE support_tickets_v2 SET status='in_progress', updated_at=? WHERE id=?",
            (now + 1, ticket_id)
        )
        db.commit()
        flash("Тикет создан! Мы уже ответили.", "success")
        return redirect(url_for("support_chat", ticket_id=ticket_id))
    return render_template("support_new.html",
                           categories=SUPPORT_CATEGORIES,
                           priorities=SUPPORT_PRIORITIES)


# ── Чат внутри тикета ────────────────────────────────
@app.route("/support/<int:ticket_id>")
def support_chat(ticket_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    uid = session["user_id"]
    db  = get_db()
    ticket = db.execute(
        "SELECT * FROM support_tickets_v2 WHERE id=?", (ticket_id,)
    ).fetchone()
    if not ticket:
        flash("Тикет не найден", "error")
        return redirect(url_for("support"))
    # только владелец или админ
    if ticket["user_id"] != uid and not session.get("is_admin"):
        abort(403)
    messages = db.execute(
        "SELECT sm.*, u.username, u.avatar FROM support_messages sm "
        "JOIN users u ON sm.user_id=u.id WHERE sm.ticket_id=? ORDER BY sm.created_at",
        (ticket_id,)
    ).fetchall()
    rating = db.execute(
        "SELECT * FROM support_ratings WHERE ticket_id=?", (ticket_id,)
    ).fetchone()
    return render_template("support_chat.html",
                           ticket=ticket,
                           messages=messages,
                           rating=rating,
                           categories=SUPPORT_CATEGORIES,
                           priorities=SUPPORT_PRIORITIES,
                           statuses=SUPPORT_STATUSES)


# ── Отправка сообщения в тикет (AJAX) ───────────────
@app.route("/api/support/<int:ticket_id>/send", methods=["POST"])
def api_support_send_v2(ticket_id):
    if "user_id" not in session:
        return jsonify({"ok": False, "msg": "Войди в аккаунт"})
    uid = session["user_id"]
    db  = get_db()
    ticket = db.execute("SELECT * FROM support_tickets_v2 WHERE id=?", (ticket_id,)).fetchone()
    if not ticket:
        return jsonify({"ok": False, "msg": "Тикет не найден"})
    if ticket["user_id"] != uid and not session.get("is_admin"):
        return jsonify({"ok": False, "msg": "Доступ запрещён"})
    if ticket["status"] in ("resolved", "closed"):
        return jsonify({"ok": False, "msg": "Тикет закрыт"})

    data    = request.get_json()
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"ok": False, "msg": "Сообщение не может быть пустым"})

    now      = int(time.time())
    is_admin = 1 if session.get("is_admin") else 0

    db.execute(
        "INSERT INTO support_messages (ticket_id,user_id,is_admin,message,created_at) VALUES (?,?,?,?,?)",
        (ticket_id, uid, is_admin, message, now)
    )
    db.execute(
        "UPDATE support_tickets_v2 SET updated_at=? WHERE id=?",
        (now, ticket_id)
    )

    ai_reply = None
    # Если пишет пользователь — авто-ответ от AI
    if not is_admin:
        history = db.execute(
            "SELECT message, is_admin FROM support_messages WHERE ticket_id=? ORDER BY created_at DESC LIMIT 8",
            (ticket_id,)
        ).fetchall()
        history = list(reversed(history))
        msgs_for_ai = [
            {"role": "assistant" if h["is_admin"] else "user", "content": h["message"]}
            for h in history
        ]
        try:
            resp = http_requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {os.environ.get('OPENROUTER_API_KEY', '')}"
                },
                json={
                    "model": "meta-llama/llama-3.1-8b-instruct:free",
                    "messages": [{"role": "system", "content": AI_SYSTEM_PROMPT}] + msgs_for_ai
                },
                timeout=15
            )
            ai_reply = resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            print("SUPPORT AI ERROR:", e)
            ai_reply = None

        if ai_reply:
            db.execute(
                "INSERT INTO support_messages (ticket_id,user_id,is_admin,message,created_at) VALUES (?,?,1,?,?)",
                (ticket_id, uid, ai_reply, now + 1)
            )
            db.execute(
                "UPDATE support_tickets_v2 SET status='in_progress', updated_at=? WHERE id=?",
                (now + 1, ticket_id)
            )

    db.commit()
    return jsonify({"ok": True, "ai_reply": ai_reply})


# ── Закрыть тикет ────────────────────────────────────
@app.route("/api/support/<int:ticket_id>/close", methods=["POST"])
def api_support_close(ticket_id):
    if "user_id" not in session:
        return jsonify({"ok": False})
    uid = session["user_id"]
    db  = get_db()
    ticket = db.execute("SELECT * FROM support_tickets_v2 WHERE id=?", (ticket_id,)).fetchone()
    if not ticket:
        return jsonify({"ok": False})
    if ticket["user_id"] != uid and not session.get("is_admin"):
        return jsonify({"ok": False})
    now = int(time.time())
    db.execute(
        "UPDATE support_tickets_v2 SET status='closed', closed_at=?, updated_at=? WHERE id=?",
        (now, now, ticket_id)
    )
    db.commit()
    return jsonify({"ok": True})


# ── Оценить поддержку ────────────────────────────────
@app.route("/api/support/<int:ticket_id>/rate", methods=["POST"])
def api_support_rate(ticket_id):
    if "user_id" not in session:
        return jsonify({"ok": False})
    uid = session["user_id"]
    db  = get_db()
    ticket = db.execute("SELECT * FROM support_tickets_v2 WHERE id=?", (ticket_id,)).fetchone()
    if not ticket or ticket["user_id"] != uid:
        return jsonify({"ok": False})
    data    = request.get_json()
    rating  = int(data.get("rating", 5))
    comment = (data.get("comment") or "").strip()[:500]
    if rating < 1 or rating > 5:
        return jsonify({"ok": False, "msg": "Оценка 1-5"})
    now = int(time.time())
    db.execute(
        "INSERT OR REPLACE INTO support_ratings (ticket_id, rating, comment, created_at) VALUES (?,?,?,?)",
        (ticket_id, rating, comment, now)
    )
    db.execute(
        "UPDATE support_tickets_v2 SET status='resolved', updated_at=? WHERE id=?",
        (now, ticket_id)
    )
    db.commit()
    return jsonify({"ok": True})


# ── Получить новые сообщения (polling) ───────────────
@app.route("/api/support/<int:ticket_id>/messages")
def api_support_messages(ticket_id):
    if "user_id" not in session:
        return jsonify({"ok": False})
    uid  = session["user_id"]
    db   = get_db()
    ticket = db.execute("SELECT * FROM support_tickets_v2 WHERE id=?", (ticket_id,)).fetchone()
    if not ticket:
        return jsonify({"ok": False})
    if ticket["user_id"] != uid and not session.get("is_admin"):
        return jsonify({"ok": False})
    since = int(request.args.get("since", 0))
    rows  = db.execute(
        "SELECT sm.*, u.username, u.avatar FROM support_messages sm "
        "JOIN users u ON sm.user_id=u.id "
        "WHERE sm.ticket_id=? AND sm.created_at>? ORDER BY sm.created_at",
        (ticket_id, since)
    ).fetchall()
    return jsonify({"ok": True, "messages": [dict(r) for r in rows]})


# ══════════════════════════════════════════════════════
# АДМИНСКИЕ МАРШРУТЫ — добавь в блок admin
# ══════════════════════════════════════════════════════

@app.route("/admin/support")
def admin_support():
    if not session.get("is_admin") or not session.get("admin_unlocked"):
        abort(403)
    db     = get_db()
    status = request.args.get("status", "")
    query  = "SELECT t.*, u.username FROM support_tickets_v2 t JOIN users u ON t.user_id=u.id"
    params = []
    if status:
        query += " WHERE t.status=?"
        params.append(status)
    query += " ORDER BY t.updated_at DESC LIMIT 100"
    tickets = db.execute(query, params).fetchall()
    stats   = {
        "open":        db.execute("SELECT COUNT(*) FROM support_tickets_v2 WHERE status='open'").fetchone()[0],
        "in_progress": db.execute("SELECT COUNT(*) FROM support_tickets_v2 WHERE status='in_progress'").fetchone()[0],
        "resolved":    db.execute("SELECT COUNT(*) FROM support_tickets_v2 WHERE status='resolved'").fetchone()[0],
        "closed":      db.execute("SELECT COUNT(*) FROM support_tickets_v2 WHERE status='closed'").fetchone()[0],
    }
    avg_rating = db.execute("SELECT AVG(rating) FROM support_ratings").fetchone()[0]
    return render_template("admin_support.html",
                           tickets=tickets,
                           stats=stats,
                           avg_rating=round(avg_rating, 1) if avg_rating else None,
                           categories=SUPPORT_CATEGORIES,
                           priorities=SUPPORT_PRIORITIES,
                           statuses=SUPPORT_STATUSES,
                           current_status=status)


@app.route("/admin/support/<int:ticket_id>/status", methods=["POST"])
def admin_support_status(ticket_id):
    if not session.get("is_admin") or not session.get("admin_unlocked"):
        abort(403)
    new_status = request.form.get("status", "")
    if new_status not in SUPPORT_STATUSES:
        abort(400)
    db  = get_db()
    now = int(time.time())
    db.execute(
        "UPDATE support_tickets_v2 SET status=?, updated_at=? WHERE id=?",
        (new_status, now, ticket_id)
    )
    db.commit()
    flash(f"Статус изменён на «{SUPPORT_STATUSES[new_status][1]}»", "success")
    return redirect(url_for("support_chat", ticket_id=ticket_id))
