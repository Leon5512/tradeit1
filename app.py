from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, abort, send_from_directory
from database import init_db, get_db
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from push_notifications import send_push_to_user, VAPID_PUBLIC_KEY
import os, time, functools, uuid as uuid_lib, secrets
import requests as http_requests


# ── 2FA зависимости ──────────────────────────────────
import pyotp
import qrcode
import io, base64

os.environ["OPENROUTER_API_KEY"] = "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"

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "avito_secret_2024_change_me")

import datetime
@app.template_filter('datetimeformat')
def datetimeformat(value):
    try:
        return datetime.datetime.fromtimestamp(int(value)).strftime('%d.%m.%Y %H:%M')
    except:
        return ''

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ADMIN_PANEL_PASSWORD = "r1blVzxo0"

RATE_LIMITS = {
    "default":  (60, 60),
    "login":    (10, 60),
    "register": (5, 300),
    "message":  (30, 60),
    "ad_new":   (10, 300),
}

def get_ip():
    return request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()

def check_rate_limit(endpoint):
    ip = get_ip()
    now = int(time.time())
    limit, window = RATE_LIMITS.get(endpoint, RATE_LIMITS["default"])
    db = get_db()
    row = db.execute("SELECT hits, window_start FROM rate_limit WHERE ip=? AND endpoint=?", (ip, endpoint)).fetchone()
    if row:
        if now - row["window_start"] > window:
            db.execute("UPDATE rate_limit SET hits=1, window_start=? WHERE ip=? AND endpoint=?", (now, ip, endpoint))
            db.commit(); return True
        if row["hits"] >= limit: return False
        db.execute("UPDATE rate_limit SET hits=hits+1 WHERE ip=? AND endpoint=?", (ip, endpoint))
    else:
        db.execute("INSERT OR IGNORE INTO rate_limit (ip,endpoint,hits,window_start) VALUES (?,?,1,?)", (ip, endpoint, now))
    db.commit(); return True

def rate_limit(endpoint_name):
    def decorator(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            if not check_rate_limit(endpoint_name):
                if request.is_json: return jsonify({"error": "Слишком много запросов"}), 429
                return render_template("error.html", code=429, msg="Слишком много запросов. Подожди немного."), 429
            return f(*args, **kwargs)
        return wrapper
    return decorator

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# ══════════════════════════════════════════════════════
# ── 2FA ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ══════════════════════════════════════════════════════

def _generate_qr_url(secret: str, username: str) -> str:
    uri = pyotp.totp.TOTP(secret).provisioning_uri(
        name=username, issuer_name="TradeIt"
    )
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

def _verify_totp(secret: str, code: str) -> bool:
    return pyotp.TOTP(secret).verify(code, valid_window=1)



# ── Service Worker ───────────────────────────────────
@app.route("/sw.js")
def sw_js():
    response = send_from_directory("static", "sw.js", mimetype="application/javascript")
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache"
    return response

@app.before_request
def setup():
    init_db()
    if "user_id" in session:
        db = get_db()
        user = db.execute("SELECT is_banned, is_admin FROM users WHERE id=?", (session["user_id"],)).fetchone()
        if not user:
            session.clear()
            return
        if user["is_banned"]:
            session.clear()
            flash("Ваш аккаунт заблокирован.", "error")
            return redirect(url_for("login"))
        session["is_admin"] = bool(user["is_admin"])

# ── Главная ──────────────────────────────────────────
@app.route("/")
def index():
    db = get_db()
    q = request.args.get("q", "")
    cat = request.args.get("cat", "")
    query = "SELECT a.*, u.username, u.accent_color FROM ads a JOIN users u ON a.user_id=u.id WHERE a.active=1 AND u.is_banned=0"
    params = []
    if q:
        query += " AND (a.title LIKE ? OR a.description LIKE ?)"; params += [f"%{q}%", f"%{q}%"]
    if cat:
        query += " AND a.category=?"; params.append(cat)
    query += " ORDER BY a.created_at DESC"
    ads = db.execute(query, params).fetchall()
    categories = db.execute("SELECT DISTINCT category FROM ads WHERE active=1").fetchall()
    return render_template("index.html", ads=ads, categories=categories, q=q, cat=cat)

# ── Регистрация ──────────────────────────────────────
@app.route("/register", methods=["GET", "POST"])
@rate_limit("register")
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        email    = request.form["email"].strip()
        password = request.form["password"]
        db = get_db()
        if db.execute("SELECT id FROM users WHERE username=? OR email=?", (username, email)).fetchone():
            flash("Пользователь уже существует", "error")
            return redirect(url_for("register"))
        count    = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        is_admin = 1 if count == 0 else 0
        token    = secrets.token_urlsafe(32)
        db.execute(
            "INSERT INTO users (username,email,password,is_admin,is_verified,verify_token,created_at) VALUES (?,?,?,?,?,?,?)",
            (username, email, generate_password_hash(password), is_admin, is_admin, token, int(time.time()))
        )
        db.commit()
        db.execute("UPDATE users SET is_verified=1 WHERE id=?", (db.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()[0],))
        db.commit()
        flash("Регистрация успешна! Войди в аккаунт.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

# ── Подтверждение email ──────────────────────────────
@app.route("/verify/<token>")
def verify_email(token):
    if not token:
        flash("Неверная ссылка", "error")
        return redirect(url_for("login"))
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE verify_token=?", (token,)).fetchone()
    if not user:
        flash("Ссылка недействительна или уже использована", "error")
        return redirect(url_for("login"))
    db.execute("UPDATE users SET is_verified=1, verify_token='' WHERE id=?", (user["id"],))
    db.commit()
    return render_template("verify_success.html")

# ── Вход ─────────────────────────────────────────────
@app.route("/login", methods=["GET", "POST"])
@rate_limit("login")
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if user and check_password_hash(user["password"], password):
            if user["is_banned"]:
                flash("Аккаунт заблокирован.", "error")
                return redirect(url_for("login"))
            if not user["is_verified"]:
                flash("Аккаунт не подтверждён. Обратись в поддержку.", "error")
                return redirect(url_for("login"))

            # ── 2FA ──────────────────────────────────
            if user["tfa_enabled"]:
                session.clear()
                session["tfa_pending_user_id"] = user["id"]
                session["tfa_method"]          = user["tfa_method"]
                if user["tfa_method"] == "totp":
                    return render_template("2fa_verify.html", method="totp")
                # email 2FA disabled - skip
                session.clear()
                session["user_id"] = user["id"]
                session["username"] = user["username"]
                session["is_admin"] = bool(user["is_admin"])
                session["admin_unlocked"] = False
                flash("Добро пожаловать!", "success")
                return redirect(url_for("index"))
            # ─────────────────────────────────────────

            session.clear()
            session["user_id"]        = user["id"]
            session["username"]       = user["username"]
            session["is_admin"]       = bool(user["is_admin"])
            session["admin_unlocked"] = False
            flash("Добро пожаловать!", "success")
            return redirect(url_for("index"))
        flash("Неверный логин или пароль", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear(); return redirect(url_for("index"))

# ══════════════════════════════════════════════════════
# ── 2FA МАРШРУТЫ
# ══════════════════════════════════════════════════════

@app.route("/settings/2fa/setup")
def tfa_setup():
    if "user_id" not in session:
        return redirect(url_for("login"))
    db     = get_db()
    user   = db.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    secret = pyotp.random_base32()
    qr_url = _generate_qr_url(secret, user["username"])
    session["pending_totp_secret"] = secret
    return render_template("2fa_setup.html", qr_url=qr_url, secret=secret)


@app.route("/settings/2fa/enable", methods=["POST"])
def tfa_enable():
    if "user_id" not in session:
        return jsonify({"ok": False, "msg": "Войди в аккаунт"})
    data   = request.get_json()
    code   = (data.get("code") or "").strip()
    method = (data.get("method") or "").strip()
    uid    = session["user_id"]
    db     = get_db()

    if method == "totp":
        secret = session.get("pending_totp_secret")
        if not secret:
            return jsonify({"ok": False, "msg": "Секрет не найден, обнови страницу"})
        if not _verify_totp(secret, code):
            return jsonify({"ok": False, "msg": "Неверный код"})
        db.execute(
            "UPDATE users SET tfa_enabled=1, tfa_method='totp', totp_secret=? WHERE id=?",
            (secret, uid)
        )
        db.commit()
        session.pop("pending_totp_secret", None)
        session["user_id"] = uid
        return jsonify({"ok": True})

    return jsonify({"ok": False, "msg": "Неизвестный метод"})

@app.route("/settings/2fa/disable", methods=["POST"])
def tfa_disable():
    if "user_id" not in session:
        return jsonify({"ok": False, "msg": "Войди в аккаунт"})
    data = request.get_json()
    pwd  = data.get("password", "")
    db   = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    if not check_password_hash(user["password"], pwd):
        return jsonify({"ok": False, "msg": "Неверный пароль"})
    db.execute(
        "UPDATE users SET tfa_enabled=0, tfa_method='', totp_secret='' WHERE id=?",
        (session["user_id"],)
    )
    db.commit()
    return jsonify({"ok": True})

@app.route("/login/2fa/verify", methods=["POST"])
def login_2fa_verify():
    pending_uid = session.get("tfa_pending_user_id")
    if not pending_uid:
        return jsonify({"ok": False, "msg": "Сессия истекла, войди снова"})
    data   = request.get_json()
    code   = (data.get("code") or "").strip()
    method = session.get("tfa_method", "")
    db     = get_db()
    user   = db.execute("SELECT * FROM users WHERE id=?", (pending_uid,)).fetchone()
    if not user:
        session.clear()
        return jsonify({"ok": False, "msg": "Пользователь не найден"})

    ok = False
    if method == "totp":
        ok = _verify_totp(user["totp_secret"], code)

    if not ok:
        return jsonify({"ok": False, "msg": "Неверный код. Попробуй ещё раз."})

    session.clear()
    session["user_id"]        = user["id"]
    session["username"]       = user["username"]
    session["is_admin"]       = bool(user["is_admin"])
    session["admin_unlocked"] = False
    return jsonify({"ok": True, "redirect": "/"})


# ── Настройки ────────────────────────────────────────
@app.route("/settings", methods=["GET", "POST"])
def settings():
    if "user_id" not in session: return redirect(url_for("login"))
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (session["user_id"],)).fetchone()
    if not user:
        session.clear()
        return redirect(url_for("login"))
    if request.method == "POST":
        bio = request.form.get("bio", "").strip()[:300]
        city = request.form.get("city", "").strip()
        accent_color = request.form.get("accent_color", "#00aeef")
        new_password = request.form.get("new_password", "").strip()
        avatar_path = user["avatar"]
        file = request.files.get("avatar")
        if file and allowed_file(file.filename):
            filename = secure_filename(f"avatar_{session['user_id']}_{int(time.time())}.{file.filename.rsplit('.',1)[1]}")
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
            avatar_path = filename
        updates = "bio=?, city=?, accent_color=?, avatar=?"
        params = [bio, city, accent_color, avatar_path]
        if new_password and len(new_password) >= 6:
            updates += ", password=?"; params.append(generate_password_hash(new_password))
        params.append(session["user_id"])
        db.execute(f"UPDATE users SET {updates} WHERE id=?", params)
        db.commit(); flash("Профиль обновлён!", "success"); return redirect(url_for("settings"))
    return render_template("settings.html", user=user)

# ── Профиль ──────────────────────────────────────────
@app.route("/user/<username>")
def profile(username):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    if not user: flash("Пользователь не найден", "error"); return redirect(url_for("index"))
    ads = db.execute("SELECT * FROM ads WHERE user_id=? AND active=1 ORDER BY created_at DESC", (user["id"],)).fetchall()
    return render_template("profile.html", user=user, ads=ads)

# ── Объявления ───────────────────────────────────────
@app.route("/ad/new", methods=["GET", "POST"])
@rate_limit("ad_new")
def new_ad():
    if "user_id" not in session: return redirect(url_for("login"))
    if request.method == "POST":
        title = request.form["title"].strip()
        description = request.form["description"].strip()
        price = request.form["price"]
        category = request.form["category"].strip()
        city = request.form["city"].strip()
        image_path = ""
        file = request.files.get("image")
        if file and allowed_file(file.filename):
            filename = secure_filename(f"{int(time.time())}_{file.filename}")
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
            image_path = filename
        db = get_db()
        db.execute("INSERT INTO ads (user_id,title,description,price,category,city,image,active,created_at) VALUES (?,?,?,?,?,?,?,1,?)",
                   (session["user_id"], title, description, price, category, city, image_path, int(time.time())))
        db.commit(); flash("Объявление опубликовано!", "success"); return redirect(url_for("index"))
    return render_template("new_ad.html")

@app.route("/ad/<int:ad_id>")
def view_ad(ad_id):
    db = get_db()
    ad = db.execute("SELECT a.*, u.username, u.id as owner_id, u.id as seller_id, u.accent_color, u.avatar, u.bio FROM ads a JOIN users u ON a.user_id=u.id WHERE a.id=?", (ad_id,)).fetchone()
    if not ad: flash("Объявление не найдено", "error"); return redirect(url_for("index"))
    purchase = None
    if "user_id" in session:
        purchase = db.execute("SELECT * FROM purchases WHERE ad_id=? AND buyer_id=?", (ad_id, session["user_id"])).fetchone()
        if not ad["active"] and not purchase and session["user_id"] != ad["owner_id"]:
            flash("Это объявление уже продано", "error"); return redirect(url_for("index"))
    elif not ad["active"]:
        flash("Это объявление уже продано", "error"); return redirect(url_for("index"))
    return render_template("view_ad.html", ad=ad, purchase=purchase)

@app.route("/ad/<int:ad_id>/edit", methods=["GET", "POST"])
def edit_ad(ad_id):
    if "user_id" not in session: return redirect(url_for("login"))
    db = get_db()
    ad = db.execute("SELECT * FROM ads WHERE id=?", (ad_id,)).fetchone()
    if not ad: flash("Объявление не найдено", "error"); return redirect(url_for("index"))
    if ad["user_id"] != session["user_id"] and not session.get("is_admin"):
        abort(403)
    if request.method == "POST":
        title = request.form["title"].strip()
        description = request.form["description"].strip()
        price = request.form["price"]
        category = request.form["category"].strip()
        city = request.form["city"].strip()
        image_path = ad["image"]
        file = request.files.get("image")
        if file and allowed_file(file.filename):
            filename = secure_filename(f"{int(time.time())}_{file.filename}")
            file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
            image_path = filename
        db.execute("UPDATE ads SET title=?,description=?,price=?,category=?,city=?,image=? WHERE id=?",
                   (title, description, price, category, city, image_path, ad_id))
        db.commit(); flash("Объявление обновлено!", "success"); return redirect(url_for("view_ad", ad_id=ad_id))
    return render_template("edit_ad.html", ad=ad)

@app.route("/ad/<int:ad_id>/delete")
def delete_ad(ad_id):
    if "user_id" not in session: return redirect(url_for("login"))
    db = get_db()
    ad = db.execute("SELECT user_id FROM ads WHERE id=?", (ad_id,)).fetchone()
    if ad and (ad["user_id"] == session["user_id"] or session.get("is_admin")):
        db.execute("UPDATE ads SET active=0 WHERE id=?", (ad_id,))
        db.commit(); flash("Объявление удалено", "success")
    return redirect(url_for("profile", username=session["username"]))

# ── Покупка ───────────────────────────────────────────
@app.route("/ad/<int:ad_id>/buy", methods=["POST"])
def buy_ad(ad_id):
    if "user_id" not in session:
        return jsonify({"ok": False, "msg": "Войди в аккаунт"})
    uid = session["user_id"]
    db = get_db()
    ad = db.execute("SELECT * FROM ads WHERE id=? AND active=1", (ad_id,)).fetchone()
    if not ad:
        return jsonify({"ok": False, "msg": "Объявление не найдено"})
    if ad["user_id"] == uid:
        return jsonify({"ok": False, "msg": "Нельзя купить своё объявление"})
    existing = db.execute("SELECT id FROM purchases WHERE ad_id=?", (ad_id,)).fetchone()
    if existing:
        return jsonify({"ok": False, "msg": "Уже куплено"})
    db.execute("INSERT INTO purchases (ad_id, buyer_id, seller_id, created_at) VALUES (?,?,?,?)",
               (ad_id, uid, ad["user_id"], int(time.time())))
    db.execute("UPDATE ads SET active=0 WHERE id=?", (ad_id,))
    db.commit()
    buyer = db.execute("SELECT username FROM users WHERE id=?", (uid,)).fetchone()
    buyer_name = buyer["username"] if buyer else "Покупатель"
    send_push_to_user(db, ad["user_id"], title="🎉 Твоё объявление куплено!", body=f"{buyer_name} купил «{ad['title'][:60]}»", url=f"/ad/{ad_id}", tag="purchase")
    return jsonify({"ok": True, "seller_id": ad["user_id"]})

@app.route("/ad/<int:ad_id>/purchase")
def view_purchase(ad_id):
    if "user_id" not in session: return redirect(url_for("login"))
    uid = session["user_id"]
    db = get_db()
    ad = db.execute("SELECT a.*, u.username as seller_name, u.id as seller_id FROM ads a JOIN users u ON a.user_id=u.id WHERE a.id=?", (ad_id,)).fetchone()
    purchase = db.execute("SELECT * FROM purchases WHERE ad_id=? AND buyer_id=?", (ad_id, uid)).fetchone()
    if not ad or not purchase:
        flash("Доступ запрещён", "error"); return redirect(url_for("index"))
    return render_template("view_ad.html", ad=ad, purchase=purchase)

# ── Отзывы ────────────────────────────────────────────
@app.route("/review/<int:to_user_id>", methods=["POST"])
def add_review(to_user_id):
    if "user_id" not in session:
        return jsonify({"ok": False, "msg": "Войди в аккаунт"})
    uid = session["user_id"]
    if uid == to_user_id:
        return jsonify({"ok": False, "msg": "Нельзя оставить отзыв себе"})
    data = request.get_json()
    rating = int(data.get("rating", 5))
    text = (data.get("text") or "").strip()[:500]
    if rating < 1 or rating > 5:
        return jsonify({"ok": False, "msg": "Рейтинг 1-5"})
    db = get_db()
    existing = db.execute("SELECT id FROM reviews WHERE from_user_id=? AND to_user_id=?", (uid, to_user_id)).fetchone()
    if existing:
        db.execute("UPDATE reviews SET rating=?, text=?, created_at=? WHERE from_user_id=? AND to_user_id=?",
                   (rating, text, int(time.time()), uid, to_user_id))
    else:
        db.execute("INSERT INTO reviews (from_user_id, to_user_id, rating, text, created_at) VALUES (?,?,?,?,?)",
                   (uid, to_user_id, rating, text, int(time.time())))
    db.commit()
    return jsonify({"ok": True})

@app.route("/api/reviews/<int:user_id>")
def api_reviews(user_id):
    db = get_db()
    rows = db.execute("""SELECT r.*, u.username as from_username FROM reviews r
        JOIN users u ON r.from_user_id=u.id
        WHERE r.to_user_id=? ORDER BY r.created_at DESC""", (user_id,)).fetchall()
    avg = db.execute("SELECT AVG(rating) FROM reviews WHERE to_user_id=?", (user_id,)).fetchone()[0]
    return jsonify({"reviews": [dict(r) for r in rows], "avg": round(avg, 1) if avg else None})

# ── Кошелёк ───────────────────────────────────────────
@app.route("/wallet")
def wallet():
    if "user_id" not in session: return redirect(url_for("login"))
    db = get_db()
    user = db.execute("SELECT id, username, balance FROM users WHERE id=?", (session["user_id"],)).fetchone()
    txs = db.execute("SELECT * FROM transactions WHERE user_id=? ORDER BY created_at DESC LIMIT 50", (session["user_id"],)).fetchall()
    return render_template("wallet.html", user=user, transactions=txs)

@app.route("/wallet/topup", methods=["POST"])
def wallet_topup():
    if "user_id" not in session:
        return jsonify({"ok": False, "msg": "Войди в аккаунт"})
    data = request.get_json()
    try:
        amount = float(data.get("amount", 0))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "msg": "Неверная сумма"})
    if amount <= 0 or amount > 1_000_000:
        return jsonify({"ok": False, "msg": "Сумма должна быть от 1 до 1 000 000 ₽"})
    uid = session["user_id"]
    db = get_db()
    db.execute("UPDATE users SET balance = balance + ? WHERE id=?", (amount, uid))
    db.execute("INSERT INTO transactions (user_id, amount, type, description, created_at) VALUES (?,?,?,?,?)",
               (uid, amount, "topup", "Пополнение баланса", int(time.time())))
    db.commit()
    new_balance = db.execute("SELECT balance FROM users WHERE id=?", (uid,)).fetchone()[0]
    return jsonify({"ok": True, "balance": new_balance})

@app.route("/api/balance")
def api_balance():
    if "user_id" not in session: return jsonify({"balance": 0})
    db = get_db()
    row = db.execute("SELECT balance FROM users WHERE id=?", (session["user_id"],)).fetchone()
    return jsonify({"balance": row["balance"] if row else 0})

# ── Сообщения ─────────────────────────────────────────
@app.route("/messages")
def messages():
    if "user_id" not in session: return redirect(url_for("login"))
    uid = session["user_id"]
    db = get_db()
    rows = db.execute("SELECT sender_id, receiver_id, text, created_at FROM messages WHERE sender_id=? OR receiver_id=? ORDER BY created_at DESC", (uid, uid)).fetchall()
    seen = {}
    for r in rows:
        other_id = r["receiver_id"] if r["sender_id"] == uid else r["sender_id"]
        if other_id not in seen:
            seen[other_id] = {"last_msg": r["text"], "created_at": r["created_at"]}
    dialogs = []
    for other_id, info in seen.items():
        other = db.execute("SELECT id, username, avatar, accent_color FROM users WHERE id=?", (other_id,)).fetchone()
        if not other: continue
        unread = db.execute("SELECT COUNT(*) FROM messages WHERE sender_id=? AND receiver_id=? AND is_read=0", (other_id, uid)).fetchone()[0]
        dialogs.append({"other_id": other["id"], "other_username": other["username"],
                        "other_avatar": other["avatar"], "accent_color": other["accent_color"],
                        "last_msg": info["last_msg"], "unread": unread})
    return render_template("messages.html", dialogs=dialogs)

@app.route("/messages/<int:other_id>", methods=["GET", "POST"])
def chat(other_id):
    if "user_id" not in session: return redirect(url_for("login"))
    db = get_db()
    other = db.execute("SELECT * FROM users WHERE id=?", (other_id,)).fetchone()
    if not other: return redirect(url_for("messages"))
    return render_template("chat.html", other=other)

# ── Техподдержка ──────────────────────────────────────
# ============================================================
# ВСТАВЬ ЭТОТ БЛОК В app.py
# Рекомендуем — после блока "── Техподдержка ──" (примерно строка 630)
# и до блока "── Избранное ──"
#
# Также нужно добавить новый маршрут в секцию "── Админ панель ──":
#   /admin/make_support/<int:user_id>   — назначить роль поддержки
#   /admin/remove_support/<int:user_id> — снять роль поддержки
#   /admin/assign_ticket/<int:ticket_user_id> — назначить тикет агенту
# ============================================================

# ──────────────────────────────────────────────────────────
# ВСПОМОГАТЕЛЬНЫЙ ДЕКОРАТОР: только агент поддержки или админ
# ──────────────────────────────────────────────────────────

def require_support(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        db = get_db()
        user = db.execute("SELECT is_support, is_admin FROM users WHERE id=?",
                          (session["user_id"],)).fetchone()
        if not user or (not user["is_support"] and not user["is_admin"]):
            abort(403)
        return f(*args, **kwargs)
    return wrapper


# ──────────────────────────────────────────────────────────
# СТРАНИЦА ПОДДЕРЖКИ ДЛЯ ПОЛЬЗОВАТЕЛЯ  (заменяет старый /support)
# ──────────────────────────────────────────────────────────

@app.route("/support", methods=["GET", "POST"])
def support():
    if "user_id" not in session:
        return redirect(url_for("login"))
    uid = session["user_id"]
    db  = get_db()

    if request.method == "POST":
        text = request.form.get("text", "").strip()
        if text:
            # Если у пользователя нет открытого тикета — создать заявку
            open_ticket = db.execute(
                "SELECT id FROM support_tickets WHERE user_id=? AND status='open' AND is_admin=0 AND is_support_agent=0 LIMIT 1",
                (uid,)
            ).fetchone()
            if not open_ticket:
                db.execute(
                    "INSERT INTO support_tickets (user_id, message, is_admin, is_support_agent, status, created_at) VALUES (?,?,0,0,'open',?)",
                    (uid, text, int(time.time()))
                )
            else:
                db.execute(
                    "INSERT INTO support_tickets (user_id, message, is_admin, is_support_agent, assigned_support_id, status, created_at) VALUES (?,?,0,0,(SELECT assigned_support_id FROM support_tickets WHERE user_id=? AND assigned_support_id IS NOT NULL LIMIT 1),'open',?)",
                    (uid, text, uid, int(time.time()))
                )
            db.commit()
        return redirect(url_for("support"))

    tickets = db.execute(
        "SELECT * FROM support_tickets WHERE user_id=? ORDER BY created_at",
        (uid,)
    ).fetchall()
    return render_template("support.html", tickets=tickets)


@app.route("/api/support/send", methods=["POST"])
def api_support_send():
    if "user_id" not in session:
        return jsonify({"ok": False})
    data = request.get_json()
    text = (data.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False})
    uid = session["user_id"]
    db  = get_db()

    # Определяем assigned_support_id из уже существующих сообщений
    assigned = db.execute(
        "SELECT assigned_support_id FROM support_tickets WHERE user_id=? AND assigned_support_id IS NOT NULL LIMIT 1",
        (uid,)
    ).fetchone()
    assigned_id = assigned["assigned_support_id"] if assigned else None

    db.execute(
        "INSERT INTO support_tickets (user_id, message, is_admin, is_support_agent, assigned_support_id, status, created_at) VALUES (?,?,0,0,?,'open',?)",
        (uid, text, assigned_id, int(time.time()))
    )
    db.commit()

    # История для AI
    history = db.execute(
        "SELECT message, is_admin, is_support_agent FROM support_tickets WHERE user_id=? ORDER BY created_at DESC LIMIT 10",
        (uid,)
    ).fetchall()
    history = list(reversed(history))

    messages_for_ai = []
    for h in history:
        role = "assistant" if (h["is_admin"] or h["is_support_agent"]) else "user"
        messages_for_ai.append({"role": role, "content": h["message"]})

    # Если нет назначенного агента — отвечает AI
    if not assigned_id:
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
                        {"role": "system", "content": "Ты техподдержка сайта TradeIt — это маркетплейс для продажи товаров. Помогай пользователям с вопросами о сайте: как разместить объявление, как написать продавцу, как редактировать профиль и т.д. Отвечай кратко, дружелюбно, на русском языке."}
                    ] + messages_for_ai
                },
                timeout=15
            )
            ai_text = resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            print("SUPPORT AI ERROR:", str(e))
            ai_text = "Ваш запрос принят. Скоро ответят."

        db.execute(
            "INSERT INTO support_tickets (user_id, message, is_admin, is_support_agent, status, created_at) VALUES (?,?,1,0,'open',?)",
            (uid, ai_text, int(time.time()))
        )
        db.commit()
        return jsonify({"ok": True, "reply": ai_text})

    # Если есть агент — уведомляем его (push) и просто подтверждаем
    agent = db.execute("SELECT id FROM users WHERE id=?", (assigned_id,)).fetchone()
    if agent:
        user_row = db.execute("SELECT username FROM users WHERE id=?", (uid,)).fetchone()
        uname = user_row["username"] if user_row else "Пользователь"
        send_push_to_user(
            db, assigned_id,
            title=f"💬 Новое сообщение от {uname}",
            body=text[:80],
            url="/support/panel",
            tag="support"
        )
    return jsonify({"ok": True, "reply": None})


# ──────────────────────────────────────────────────────────
# ПАНЕЛЬ АГЕНТА ПОДДЕРЖКИ
# ──────────────────────────────────────────────────────────

@app.route("/support/panel")
@require_support
def support_panel():
    uid = session["user_id"]
    db  = get_db()
    user = db.execute("SELECT is_admin FROM users WHERE id=?", (uid,)).fetchone()
    is_admin_user = bool(user["is_admin"]) if user else False

    if is_admin_user:
        # Администратор видит все тикеты
        open_users = db.execute("""
            SELECT DISTINCT st.user_id, u.username, u.avatar,
                   MAX(st.created_at) as last_msg,
                   st.assigned_support_id,
                   SUM(CASE WHEN st.is_admin=0 AND st.is_support_agent=0 THEN 1 ELSE 0 END) as user_msgs
            FROM support_tickets st
            JOIN users u ON st.user_id = u.id
            WHERE st.status = 'open'
            GROUP BY st.user_id
            ORDER BY last_msg DESC
        """).fetchall()
    else:
        # Агент видит только назначенные ему тикеты
        open_users = db.execute("""
            SELECT DISTINCT st.user_id, u.username, u.avatar,
                   MAX(st.created_at) as last_msg,
                   st.assigned_support_id,
                   SUM(CASE WHEN st.is_admin=0 AND st.is_support_agent=0 THEN 1 ELSE 0 END) as user_msgs
            FROM support_tickets st
            JOIN users u ON st.user_id = u.id
            WHERE st.status = 'open' AND st.assigned_support_id = ?
            GROUP BY st.user_id
            ORDER BY last_msg DESC
        """, (uid,)).fetchall()

    agents = db.execute(
        "SELECT id, username FROM users WHERE is_support=1 OR is_admin=1 ORDER BY username"
    ).fetchall()

    return render_template("support_panel.html",
                           open_users=open_users,
                           agents=agents,
                           is_admin_user=is_admin_user)


@app.route("/support/panel/<int:user_id>", methods=["GET", "POST"])
@require_support
def support_panel_chat(user_id):
    uid = session["user_id"]
    db  = get_db()

    if request.method == "POST":
        text = request.form.get("text", "").strip()
        if text:
            db.execute(
                "INSERT INTO support_tickets (user_id, message, is_admin, is_support_agent, assigned_support_id, status, created_at) VALUES (?,?,0,1,?,'open',?)",
                (user_id, text, uid, int(time.time()))
            )
            # Также помечаем все сообщения пользователя как назначенные этому агенту
            db.execute(
                "UPDATE support_tickets SET assigned_support_id=? WHERE user_id=? AND assigned_support_id IS NULL",
                (uid, user_id)
            )
            db.commit()
            # Push пользователю
            agent_name = db.execute("SELECT username FROM users WHERE id=?", (uid,)).fetchone()
            aname = agent_name["username"] if agent_name else "Поддержка"
            send_push_to_user(
                db, user_id,
                title=f"💬 Ответ от поддержки",
                body=text[:80],
                url="/support",
                tag="support"
            )
        return redirect(url_for("support_panel_chat", user_id=user_id))

    tickets = db.execute(
        "SELECT st.*, u.username as agent_name FROM support_tickets st LEFT JOIN users u ON st.assigned_support_id = u.id WHERE st.user_id=? ORDER BY st.created_at",
        (user_id,)
    ).fetchall()
    target_user = db.execute("SELECT id, username, avatar FROM users WHERE id=?", (user_id,)).fetchone()
    agents = db.execute(
        "SELECT id, username FROM users WHERE is_support=1 OR is_admin=1 ORDER BY username"
    ).fetchall()

    return render_template("support_panel_chat.html",
                           tickets=tickets,
                           target_user=target_user,
                           agents=agents,
                           current_agent_id=uid)


@app.route("/support/panel/close/<int:user_id>")
@require_support
def support_close_ticket(user_id):
    db = get_db()
    db.execute("UPDATE support_tickets SET status='closed' WHERE user_id=?", (user_id,))
    db.commit()
    flash("Тикет закрыт", "success")
    return redirect(url_for("support_panel"))


@app.route("/support/panel/assign/<int:user_id>", methods=["POST"])
@require_support
def support_assign(user_id):
    agent_id = request.form.get("agent_id", type=int)
    if not agent_id:
        flash("Выбери агента", "error")
        return redirect(url_for("support_panel_chat", user_id=user_id))
    db = get_db()
    db.execute(
        "UPDATE support_tickets SET assigned_support_id=? WHERE user_id=?",
        (agent_id, user_id)
    )
    db.commit()
    flash("Тикет назначен", "success")
    return redirect(url_for("support_panel_chat", user_id=user_id))


# ──────────────────────────────────────────────────────────
# ADMIN: назначение / снятие роли поддержки
# ──────────────────────────────────────────────────────────

@app.route("/admin/make_support/<int:user_id>")
def admin_make_support(user_id):
    if not session.get("is_admin") or not session.get("admin_unlocked"):
        abort(403)
    db = get_db()
    db.execute("UPDATE users SET is_support=1 WHERE id=?", (user_id,))
    db.commit()
    flash("Роль поддержки назначена", "success")
    return redirect(url_for("admin"))


@app.route("/admin/remove_support/<int:user_id>")
def admin_remove_support(user_id):
    if not session.get("is_admin") or not session.get("admin_unlocked"):
        abort(403)
    db = get_db()
    db.execute("UPDATE users SET is_support=0 WHERE id=?", (user_id,))
    db.commit()
    flash("Роль поддержки снята", "success")
    return redirect(url_for("admin"))

# ── Избранное ─────────────────────────────────────────
@app.route("/favorites")
def favorites():
    if "user_id" not in session: return redirect(url_for("login"))
    db = get_db()
    ads = db.execute("""SELECT a.*, u.username FROM ads a
        JOIN favorites f ON f.ad_id=a.id
        JOIN users u ON a.user_id=u.id
        WHERE f.user_id=? AND a.active=1 ORDER BY f.created_at DESC""", (session["user_id"],)).fetchall()
    return render_template("favorites.html", ads=ads)

@app.route("/favorites/toggle/<int:ad_id>")
def toggle_favorite(ad_id):
    if "user_id" not in session: return jsonify({"ok": False, "msg": "Войди в аккаунт"})
    uid = session["user_id"]
    db = get_db()
    existing = db.execute("SELECT id FROM favorites WHERE user_id=? AND ad_id=?", (uid, ad_id)).fetchone()
    if existing:
        db.execute("DELETE FROM favorites WHERE user_id=? AND ad_id=?", (uid, ad_id))
        db.commit(); return jsonify({"ok": True, "saved": False})
    else:
        db.execute("INSERT INTO favorites (user_id, ad_id, created_at) VALUES (?,?,?)", (uid, ad_id, int(time.time())))
        db.commit(); return jsonify({"ok": True, "saved": True})

@app.route("/api/favorite_status/<int:ad_id>")
def api_favorite_status(ad_id):
    if "user_id" not in session: return jsonify({"saved": False})
    db = get_db()
    existing = db.execute("SELECT id FROM favorites WHERE user_id=? AND ad_id=?", (session["user_id"], ad_id)).fetchone()
    return jsonify({"saved": bool(existing)})

# ── API сообщения ─────────────────────────────────────
@app.route("/api/messages/<int:other_id>")
def api_messages(other_id):
    if "user_id" not in session: return jsonify({"msgs": []})
    uid = session["user_id"]
    db = get_db()
    db.execute("UPDATE messages SET is_read=1 WHERE receiver_id=? AND sender_id=?", (uid, other_id))
    db.commit()
    rows = db.execute("SELECT id,sender_id,receiver_id,text,created_at FROM messages WHERE (sender_id=? AND receiver_id=?) OR (sender_id=? AND receiver_id=?) ORDER BY created_at",
                      (uid, other_id, other_id, uid)).fetchall()
    return jsonify({"msgs": [dict(r) for r in rows]})

@app.route("/api/send/<int:other_id>", methods=["POST"])
@rate_limit("message")
def api_send(other_id):
    if "user_id" not in session: return jsonify({"ok": False})
    uid = session["user_id"]
    data = request.get_json()
    text = (data.get("text") or "").strip()
    if not text: return jsonify({"ok": False})
    db = get_db()
    db.execute("INSERT INTO messages (sender_id,receiver_id,text,is_read,created_at) VALUES (?,?,?,0,?)",
               (uid, other_id, text, int(time.time())))
    db.commit()
    sender = db.execute("SELECT username FROM users WHERE id=?", (uid,)).fetchone()
    sender_name = sender["username"] if sender else "Кто-то"
    preview = text[:80] + ("…" if len(text) > 80 else "")
    send_push_to_user(db, other_id, title=f"✉️ Новое сообщение от {sender_name}", body=preview, url=f"/messages/{uid}", tag="msg")
    return jsonify({"ok": True})

@app.route("/api/unread")
def api_unread():
    if "user_id" not in session: return jsonify({"count": 0})
    db = get_db()
    count = db.execute("SELECT COUNT(*) FROM messages WHERE receiver_id=? AND is_read=0", (session["user_id"],)).fetchone()[0]
    return jsonify({"count": count})

# ── Web Push ──────────────────────────────────────────
@app.route("/api/push/vapid-public-key")
def api_push_vapid_key():
    return jsonify({"key": VAPID_PUBLIC_KEY})

@app.route("/api/push/subscribe", methods=["POST"])
def api_push_subscribe():
    if "user_id" not in session:
        return jsonify({"ok": False, "msg": "Войди в аккаунт"})
    data = request.get_json()
    endpoint = data.get("endpoint", "").strip()
    p256dh   = data.get("keys", {}).get("p256dh", "").strip()
    auth     = data.get("keys", {}).get("auth", "").strip()
    if not endpoint or not p256dh or not auth:
        return jsonify({"ok": False, "msg": "Неверные данные подписки"})
    uid = session["user_id"]
    db = get_db()
    existing = db.execute("SELECT id FROM push_subscriptions WHERE endpoint=?", (endpoint,)).fetchone()
    if existing:
        db.execute("UPDATE push_subscriptions SET user_id=?, p256dh=?, auth=? WHERE endpoint=?", (uid, p256dh, auth, endpoint))
    else:
        db.execute("INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth, created_at) VALUES (?,?,?,?,?)",
                   (uid, endpoint, p256dh, auth, int(time.time())))
    db.commit()
    return jsonify({"ok": True})

@app.route("/api/push/unsubscribe", methods=["POST"])
def api_push_unsubscribe():
    if "user_id" not in session:
        return jsonify({"ok": False})
    data = request.get_json()
    endpoint = data.get("endpoint", "").strip()
    db = get_db()
    db.execute("DELETE FROM push_subscriptions WHERE endpoint=? AND user_id=?", (endpoint, session["user_id"]))
    db.commit()
    return jsonify({"ok": True})

# ── Админ панель ──────────────────────────────────────
@app.route("/admin/auth", methods=["POST"])
def admin_auth():
    if "user_id" not in session: return jsonify({"ok": False})
    data = request.get_json()
    if data.get("password") == ADMIN_PANEL_PASSWORD:
        session["admin_unlocked"] = True; return jsonify({"ok": True})
    return jsonify({"ok": False})

@app.route("/admin")
def admin():
    if "user_id" not in session: return redirect(url_for("login"))
    if not session.get("is_admin") or not session.get("admin_unlocked"): abort(403)
    db = get_db()
    users = db.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
    ads = db.execute("SELECT a.*, u.username FROM ads a JOIN users u ON a.user_id=u.id ORDER BY a.created_at DESC LIMIT 50").fetchall()
    stats = {
        "users":    db.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        "ads":      db.execute("SELECT COUNT(*) FROM ads WHERE active=1").fetchone()[0],
        "messages": db.execute("SELECT COUNT(*) FROM messages").fetchone()[0],
        "banned":   db.execute("SELECT COUNT(*) FROM users WHERE is_banned=1").fetchone()[0],
    }
    rl = db.execute("SELECT ip, endpoint, hits FROM rate_limit ORDER BY hits DESC LIMIT 20").fetchall()
    tickets = db.execute("SELECT s.*, u.username FROM support_tickets s JOIN users u ON s.user_id=u.id ORDER BY s.created_at DESC LIMIT 100").fetchall()
    return render_template("admin.html", users=users, ads=ads, stats=stats, rl=rl, tickets=tickets)

@app.route("/admin/ban/<int:user_id>")
def admin_ban(user_id):
    if not session.get("is_admin") or not session.get("admin_unlocked"): abort(403)
    if user_id == session["user_id"]: flash("Нельзя забанить себя!", "error"); return redirect(url_for("admin"))
    db = get_db()
    db.execute("UPDATE users SET is_banned=1 WHERE id=?", (user_id,))
    db.commit(); flash("Заблокирован", "success"); return redirect(url_for("admin"))

@app.route("/admin/unban/<int:user_id>")
def admin_unban(user_id):
    if not session.get("is_admin") or not session.get("admin_unlocked"): abort(403)
    db = get_db()
    db.execute("UPDATE users SET is_banned=0 WHERE id=?", (user_id,))
    db.commit(); flash("Разблокирован", "success"); return redirect(url_for("admin"))

@app.route("/admin/delete_ad/<int:ad_id>")
def admin_delete_ad(ad_id):
    if not session.get("is_admin") or not session.get("admin_unlocked"): abort(403)
    db = get_db()
    db.execute("UPDATE ads SET active=0 WHERE id=?", (ad_id,))
    db.commit(); flash("Удалено", "success"); return redirect(url_for("admin"))

@app.route("/admin/make_admin/<int:user_id>")
def admin_make_admin(user_id):
    if not session.get("is_admin") or not session.get("admin_unlocked"): abort(403)
    db = get_db()
    db.execute("UPDATE users SET is_admin=1 WHERE id=?", (user_id,))
    db.commit(); flash("Назначен админом", "success"); return redirect(url_for("admin"))

@app.route("/admin/reply_support/<int:user_id>", methods=["POST"])
def admin_reply_support(user_id):
    if not session.get("is_admin") or not session.get("admin_unlocked"): abort(403)
    text = request.form.get("text", "").strip()
    if text:
        db = get_db()
        db.execute("INSERT INTO support_tickets (user_id, message, is_admin, created_at) VALUES (?,?,1,?)",
                   (user_id, text, int(time.time())))
        db.commit(); flash("Ответ отправлен", "success")
    return redirect(url_for("admin") + "#support")

@app.route("/admin/announce", methods=["POST"])
def admin_announce():
    if not session.get("is_admin") or not session.get("admin_unlocked"): abort(403)
    text = request.form.get("text", "").strip()
    if text:
        db = get_db()
        db.execute("INSERT INTO announcements (text, created_at) VALUES (?,?)", (text, int(time.time())))
        db.commit(); flash("Объявление опубликовано", "success")
    return redirect(url_for("admin"))

@app.route("/api/announcements")
def api_announcements():
    db = get_db()
    rows = db.execute("SELECT * FROM announcements ORDER BY created_at DESC LIMIT 5").fetchall()
    return jsonify({"items": [dict(r) for r in rows]})

@app.errorhandler(403)
def forbidden(e): return render_template("error.html", code=403, msg="Доступ запрещён"), 403

@app.errorhandler(404)
def not_found(e): return render_template("error.html", code=404, msg="Страница не найдена"), 404

# ══════════════════════════════════════════════════════
# ── МЕССЕНДЖЕР
# ══════════════════════════════════════════════════════

def msn_profile(user_id):
    return get_db().execute("SELECT * FROM messenger_profiles WHERE user_id=?", (user_id,)).fetchone()

def require_msn(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        if not msn_profile(session["user_id"]):
            return redirect(url_for("msn_setup"))
        return f(*args, **kwargs)
    return wrapper

def generate_msn_number():
    import random
    db = get_db()
    for _ in range(100):
        num = f"#{random.randint(10000, 99999)}"
        if not db.execute("SELECT id FROM messenger_profiles WHERE msn_number=?", (num,)).fetchone():
            return num
    return f"#{int(time.time()) % 100000}"

@app.route("/messenger")
def msn_index():
    if "user_id" not in session: return redirect(url_for("login"))
    profile = msn_profile(session["user_id"])
    if not profile: return redirect(url_for("msn_setup"))
    db = get_db()
    rows = db.execute("""
        SELECT m.*,
               s.msn_username as s_name, s.msn_number as s_num, s.avatar as s_av,
               r.msn_username as r_name, r.msn_number as r_num, r.avatar as r_av
        FROM msn_messages m
        JOIN messenger_profiles s ON m.sender_id = s.id
        JOIN messenger_profiles r ON m.receiver_id = r.id
        WHERE (m.sender_id=? OR m.receiver_id=?) AND m.group_id IS NULL
        ORDER BY m.created_at DESC
    """, (profile["id"], profile["id"])).fetchall()
    seen = {}
    for r in rows:
        other_id = r["receiver_id"] if r["sender_id"] == profile["id"] else r["sender_id"]
        if other_id not in seen:
            seen[other_id] = {
                "id": other_id,
                "name": r["r_name"] if r["sender_id"] == profile["id"] else r["s_name"],
                "num":  r["r_num"]  if r["sender_id"] == profile["id"] else r["s_num"],
                "av":   r["r_av"]   if r["sender_id"] == profile["id"] else r["s_av"],
                "last": r["text"], "ts": r["created_at"]
            }
    dialogs = list(seen.values())
    groups = db.execute("""
        SELECT g.* FROM msn_groups g
        JOIN msn_group_members gm ON g.id = gm.group_id
        WHERE gm.profile_id=? ORDER BY g.created_at DESC
    """, (profile["id"],)).fetchall()
    now = int(time.time())
    statuses = []
    for d in dialogs:
        st = db.execute("SELECT * FROM msn_statuses WHERE profile_id=? AND expires_at>? ORDER BY created_at DESC LIMIT 1",
                        (d["id"], now)).fetchone()
        if st:
            statuses.append({"name": d["name"], "text": st["text"]})
    unread = db.execute("SELECT COUNT(*) FROM msn_messages WHERE receiver_id=? AND is_read=0 AND group_id IS NULL",
                        (profile["id"],)).fetchone()[0]
    return render_template("messenger.html", profile=profile, dialogs=dialogs,
                           groups=groups, statuses=statuses, unread=unread)

@app.route("/messenger/setup", methods=["GET", "POST"])
def msn_setup():
    if "user_id" not in session: return redirect(url_for("login"))
    if msn_profile(session["user_id"]): return redirect(url_for("msn_index"))
    if request.method == "POST":
        msn_username = request.form.get("msn_username", "").strip()
        if not msn_username or len(msn_username) < 3:
            flash("Имя должно быть минимум 3 символа", "error")
            return redirect(url_for("msn_setup"))
        db = get_db()
        if db.execute("SELECT id FROM messenger_profiles WHERE msn_username=?", (msn_username,)).fetchone():
            flash("Это имя уже занято", "error")
            return redirect(url_for("msn_setup"))
        number = generate_msn_number()
        user = db.execute("SELECT avatar FROM users WHERE id=?", (session["user_id"],)).fetchone()
        db.execute("INSERT INTO messenger_profiles (user_id, msn_username, msn_number, avatar, created_at) VALUES (?,?,?,?,?)",
                   (session["user_id"], msn_username, number, user["avatar"] or "", int(time.time())))
        db.commit()
        flash(f"Добро пожаловать! Твой номер: {number}", "success")
        return redirect(url_for("msn_index"))
    return render_template("msn_setup.html")

@app.route("/messenger/chat/<int:other_profile_id>")
@require_msn
def msn_chat(other_profile_id):
    db = get_db()
    me = msn_profile(session["user_id"])
    other = db.execute("SELECT * FROM messenger_profiles WHERE id=?", (other_profile_id,)).fetchone()
    if not other: return redirect(url_for("msn_index"))
    db.execute("UPDATE msn_messages SET is_read=1 WHERE receiver_id=? AND sender_id=? AND group_id IS NULL",
               (me["id"], other_profile_id))
    db.commit()
    msgs = db.execute("""SELECT * FROM msn_messages
        WHERE ((sender_id=? AND receiver_id=?) OR (sender_id=? AND receiver_id=?)) AND group_id IS NULL
        ORDER BY created_at""", (me["id"], other_profile_id, other_profile_id, me["id"])).fetchall()
    return render_template("msn_chat.html", me=dict(me), other=dict(other), msgs=[dict(m) for m in msgs])

@app.route("/messenger/group/<int:group_id>")
@require_msn
def msn_group_chat(group_id):
    db = get_db()
    me = msn_profile(session["user_id"])
    group = db.execute("SELECT * FROM msn_groups WHERE id=?", (group_id,)).fetchone()
    if not group: return redirect(url_for("msn_index"))
    if not db.execute("SELECT * FROM msn_group_members WHERE group_id=? AND profile_id=?",
                      (group_id, me["id"])).fetchone():
        return redirect(url_for("msn_index"))
    msgs = db.execute("""SELECT m.*, p.msn_username, p.avatar FROM msn_group_messages m
        JOIN messenger_profiles p ON m.sender_id=p.id
        WHERE m.group_id=? ORDER BY m.created_at""", (group_id,)).fetchall()
    members = db.execute("""SELECT p.* FROM messenger_profiles p
        JOIN msn_group_members gm ON p.id=gm.profile_id WHERE gm.group_id=?""", (group_id,)).fetchall()
    return render_template("msn_group.html", me=dict(me), group=dict(group),
                           msgs=[dict(m) for m in msgs], members=members)

@app.route("/messenger/group/new", methods=["GET", "POST"])
@require_msn
def msn_new_group():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        if not name: flash("Введи название группы", "error"); return redirect(url_for("msn_new_group"))
        db = get_db()
        me = msn_profile(session["user_id"])
        gid = db.execute("INSERT INTO msn_groups (name, created_by, created_at) VALUES (?,?,?)",
                         (name, me["id"], int(time.time()))).lastrowid
        db.execute("INSERT INTO msn_group_members (group_id, profile_id, joined_at) VALUES (?,?,?)",
                   (gid, me["id"], int(time.time())))
        db.commit()
        flash("Группа создана!", "success")
        return redirect(url_for("msn_group_chat", group_id=gid))
    return render_template("msn_new_group.html")

@app.route("/messenger/status", methods=["POST"])
@require_msn
def msn_set_status():
    text = request.form.get("text", "").strip()[:200]
    if not text: return redirect(url_for("msn_index"))
    db = get_db()
    me = msn_profile(session["user_id"])
    db.execute("INSERT INTO msn_statuses (profile_id, text, created_at, expires_at) VALUES (?,?,?,?)",
               (me["id"], text, int(time.time()), int(time.time()) + 86400))
    db.commit()
    flash("Статус установлен!", "success")
    return redirect(url_for("msn_index"))

@app.route("/messenger/find")
@require_msn
def msn_find():
    q = request.args.get("q", "").strip()
    results = []
    db = get_db()
    me = msn_profile(session["user_id"])
    if q:
        results = db.execute("""SELECT * FROM messenger_profiles
            WHERE (msn_username LIKE ? OR msn_number=?) AND id != ? LIMIT 20""",
            (f"%{q}%", q, me["id"])).fetchall()
    return render_template("msn_find.html", results=results, q=q, profile=me)

@app.route("/api/msn/send/<int:other_id>", methods=["POST"])
@require_msn
def api_msn_send(other_id):
    data = request.get_json()
    text = (data.get("text") or "").strip()
    if not text: return jsonify({"ok": False})
    db = get_db()
    me = msn_profile(session["user_id"])
    db.execute("INSERT INTO msn_messages (sender_id, receiver_id, text, is_read, created_at) VALUES (?,?,?,0,?)",
               (me["id"], other_id, text, int(time.time())))
    db.commit()
    receiver = db.execute("SELECT user_id FROM messenger_profiles WHERE id=?", (other_id,)).fetchone()
    if receiver:
        preview = text[:80] + ("…" if len(text) > 80 else "")
        send_push_to_user(db, receiver["user_id"], title=f"🚀 {me['msn_username']} написал тебе", body=preview, url=f"/messenger/chat/{me['id']}", tag="msn")
    return jsonify({"ok": True})

@app.route("/api/msn/msgs/<int:other_id>")
@require_msn
def api_msn_msgs(other_id):
    db = get_db()
    me = msn_profile(session["user_id"])
    db.execute("UPDATE msn_messages SET is_read=1 WHERE receiver_id=? AND sender_id=? AND group_id IS NULL",
               (me["id"], other_id))
    db.commit()
    rows = db.execute("""SELECT * FROM msn_messages
        WHERE ((sender_id=? AND receiver_id=?) OR (sender_id=? AND receiver_id=?)) AND group_id IS NULL
        ORDER BY created_at""", (me["id"], other_id, other_id, me["id"])).fetchall()
    return jsonify({"msgs": [dict(r) for r in rows]})

@app.route("/api/msn/group/send/<int:group_id>", methods=["POST"])
@require_msn
def api_msn_group_send(group_id):
    data = request.get_json()
    text = (data.get("text") or "").strip()
    if not text: return jsonify({"ok": False})
    db = get_db()
    me = msn_profile(session["user_id"])
    if not db.execute("SELECT * FROM msn_group_members WHERE group_id=? AND profile_id=?",
                      (group_id, me["id"])).fetchone():
        return jsonify({"ok": False})
    db.execute("INSERT INTO msn_group_messages (group_id, sender_id, text, created_at) VALUES (?,?,?,?)",
               (group_id, me["id"], text, int(time.time())))
    db.commit()
    return jsonify({"ok": True})

@app.route("/api/msn/group/msgs/<int:group_id>")
@require_msn
def api_msn_group_msgs(group_id):
    db = get_db()
    me = msn_profile(session["user_id"])
    if not db.execute("SELECT * FROM msn_group_members WHERE group_id=? AND profile_id=?",
                      (group_id, me["id"])).fetchone():
        return jsonify({"msgs": []})
    rows = db.execute("""SELECT m.*, p.msn_username, p.avatar FROM msn_group_messages m
        JOIN messenger_profiles p ON m.sender_id=p.id
        WHERE m.group_id=? ORDER BY m.created_at""", (group_id,)).fetchall()
    return jsonify({"msgs": [dict(r) for r in rows]})

@app.route("/api/msn/group/invite/<int:group_id>", methods=["POST"])
@require_msn
def api_msn_invite(group_id):
    data = request.get_json()
    number = (data.get("number") or "").strip()
    db = get_db()
    me = msn_profile(session["user_id"])
    if not db.execute("SELECT * FROM msn_groups WHERE id=? AND created_by=?", (group_id, me["id"])).fetchone():
        return jsonify({"ok": False, "msg": "Нет доступа"})
    target = db.execute("SELECT * FROM messenger_profiles WHERE msn_number=?", (number,)).fetchone()
    if not target: return jsonify({"ok": False, "msg": "Пользователь не найден"})
    if db.execute("SELECT * FROM msn_group_members WHERE group_id=? AND profile_id=?",
                  (group_id, target["id"])).fetchone():
        return jsonify({"ok": False, "msg": "Уже в группе"})
    db.execute("INSERT INTO msn_group_members (group_id, profile_id, joined_at) VALUES (?,?,?)",
               (group_id, target["id"], int(time.time())))
    db.commit()
    return jsonify({"ok": True})

@app.route("/api/msn/unread")
def api_msn_unread():
    if "user_id" not in session: return jsonify({"count": 0})
    profile = msn_profile(session["user_id"])
    if not profile: return jsonify({"count": 0})
    count = get_db().execute("SELECT COUNT(*) FROM msn_messages WHERE receiver_id=? AND is_read=0 AND group_id IS NULL",
                              (profile["id"],)).fetchone()[0]
    return jsonify({"count": count})

# ── Звонки (WebRTC) ───────────────────────────────────
@app.route("/api/msn/call/initiate/<int:callee_profile_id>", methods=["POST"])
@require_msn
def api_msn_call_initiate(callee_profile_id):
    db = get_db()
    me = msn_profile(session["user_id"])
    callee = db.execute("SELECT * FROM messenger_profiles WHERE id=?", (callee_profile_id,)).fetchone()
    if not callee:
        return jsonify({"ok": False, "msg": "Пользователь не найден"})
    call_id = str(uuid_lib.uuid4())
    db.execute("INSERT INTO msn_calls (call_id, caller_id, callee_id, status, created_at) VALUES (?,?,?,?,?)",
               (call_id, me["id"], callee_profile_id, "ringing", int(time.time())))
    db.commit()
    callee_user = db.execute("SELECT user_id FROM messenger_profiles WHERE id=?", (callee_profile_id,)).fetchone()
    if callee_user:
        send_push_to_user(db, callee_user["user_id"], title=f"📞 Входящий звонок от {me['msn_username']}", body=f"Номер: {me['msn_number']} — нажми, чтобы ответить", url=f"/messenger/call/{call_id}", tag="call")
    return jsonify({"ok": True, "call_id": call_id})

@app.route("/api/msn/call/signal", methods=["POST"])
@require_msn
def api_msn_call_signal():
    data = request.get_json()
    call_id  = data.get("call_id")
    sig_type = data.get("type")
    payload  = data.get("payload", "")
    to_id    = data.get("to_id")
    if not call_id or not sig_type or not to_id:
        return jsonify({"ok": False})
    db = get_db()
    me = msn_profile(session["user_id"])
    db.execute("INSERT INTO msn_call_signals (call_id, from_id, to_id, type, payload, created_at) VALUES (?,?,?,?,?,?)",
               (call_id, me["id"], to_id, sig_type, payload, int(time.time())))
    if sig_type in ("reject", "hangup"):
        db.execute("UPDATE msn_calls SET status=?, ended_at=? WHERE call_id=?", (sig_type, int(time.time()), call_id))
    elif sig_type == "answer":
        db.execute("UPDATE msn_calls SET status='active', started_at=? WHERE call_id=?", (int(time.time()), call_id))
    db.commit()
    return jsonify({"ok": True})

@app.route("/api/msn/call/poll/<call_id>")
@require_msn
def api_msn_call_poll(call_id):
    since = int(request.args.get("since", 0))
    db = get_db()
    me = msn_profile(session["user_id"])
    rows = db.execute("SELECT * FROM msn_call_signals WHERE call_id=? AND to_id=? AND id>? ORDER BY id",
                      (call_id, me["id"], since)).fetchall()
    call = db.execute("SELECT * FROM msn_calls WHERE call_id=?", (call_id,)).fetchone()
    return jsonify({"signals": [dict(r) for r in rows], "call_status": call["status"] if call else None, "last_id": rows[-1]["id"] if rows else since})

@app.route("/api/msn/call/incoming")
@require_msn
def api_msn_call_incoming():
    db = get_db()
    me = msn_profile(session["user_id"])
    cutoff = int(time.time()) - 30
    call = db.execute("""SELECT c.*, p.msn_username as caller_name, p.msn_number as caller_num, p.avatar as caller_av
           FROM msn_calls c JOIN messenger_profiles p ON c.caller_id=p.id
           WHERE c.callee_id=? AND c.status='ringing' AND c.created_at>?
           ORDER BY c.created_at DESC LIMIT 1""", (me["id"], cutoff)).fetchone()
    if call:
        return jsonify({"incoming": True, "call": dict(call)})
    return jsonify({"incoming": False})

@app.route("/messenger/call/<call_id>")
@require_msn
def msn_call_page(call_id):
    db = get_db()
    me = msn_profile(session["user_id"])
    call = db.execute("SELECT * FROM msn_calls WHERE call_id=?", (call_id,)).fetchone()
    if not call: return redirect(url_for("msn_index"))
    other_id = call["callee_id"] if call["caller_id"] == me["id"] else call["caller_id"]
    other = db.execute("SELECT * FROM messenger_profiles WHERE id=?", (other_id,)).fetchone()
    is_caller = (call["caller_id"] == me["id"])
    return render_template("msn_call.html", me=me, other=other, call=dict(call), is_caller=is_caller)

@app.route("/api/messages/delete/<int:msg_id>", methods=["POST"])
def api_delete_message(msg_id):
    if "user_id" not in session: return jsonify({"ok": False})
    uid = session["user_id"]
    db = get_db()
    msg = db.execute("SELECT * FROM messages WHERE id=?", (msg_id,)).fetchone()
    if not msg or msg["sender_id"] != uid:
        return jsonify({"ok": False, "msg": "Нет доступа"})
    db.execute("DELETE FROM messages WHERE id=?", (msg_id,))
    db.commit()
    return jsonify({"ok": True})

@app.route("/api/send_media/<int:other_id>", methods=["POST"])
@rate_limit("message")
def api_send_media(other_id):
    if "user_id" not in session: return jsonify({"ok": False})
    uid = session["user_id"]
    file = request.files.get("file")
    if not file or not allowed_file(file.filename):
        return jsonify({"ok": False, "msg": "Недопустимый файл"})
    ext = file.filename.rsplit(".", 1)[1].lower()
    filename = secure_filename(f"msg_{uid}_{int(time.time())}.{ext}")
    file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
    text = f"[media]{filename}[/media]"
    db = get_db()
    db.execute("INSERT INTO messages (sender_id,receiver_id,text,is_read,created_at) VALUES (?,?,?,0,?)",
               (uid, other_id, text, int(time.time())))
    db.commit()
    sender = db.execute("SELECT username FROM users WHERE id=?", (uid,)).fetchone()
    sender_name = sender["username"] if sender else "Кто-то"
    send_push_to_user(db, other_id, title=f"📎 {sender_name} прислал файл", body="Медиафайл", url=f"/messages/{uid}", tag="msg")
    return jsonify({"ok": True})

@app.route("/api/msn/delete/<int:msg_id>", methods=["POST"])
@require_msn
def api_msn_delete(msg_id):
    db = get_db()
    me = msn_profile(session["user_id"])
    msg = db.execute("SELECT * FROM msn_messages WHERE id=?", (msg_id,)).fetchone()
    if not msg or msg["sender_id"] != me["id"]:
        return jsonify({"ok": False, "msg": "Нет доступа"})
    db.execute("DELETE FROM msn_messages WHERE id=?", (msg_id,))
    db.commit()
    return jsonify({"ok": True})

@app.route("/api/msn/send_media/<int:other_id>", methods=["POST"])
@require_msn
def api_msn_send_media(other_id):
    file = request.files.get("file")
    if not file or not allowed_file(file.filename):
        return jsonify({"ok": False, "msg": "Недопустимый файл"})
    db = get_db()
    me = msn_profile(session["user_id"])
    ext = file.filename.rsplit(".", 1)[1].lower()
    filename = secure_filename(f"msn_{me['id']}_{int(time.time())}.{ext}")
    file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
    text = f"[media]{filename}[/media]"
    db.execute("INSERT INTO msn_messages (sender_id,receiver_id,text,is_read,created_at) VALUES (?,?,?,0,?)",
               (me["id"], other_id, text, int(time.time())))
    db.commit()
    receiver = db.execute("SELECT user_id FROM messenger_profiles WHERE id=?", (other_id,)).fetchone()
    if receiver:
        send_push_to_user(db, receiver["user_id"], title=f"📎 {me['msn_username']} прислал файл", body="Медиафайл", url=f"/messenger/chat/{me['id']}", tag="msn")
        receiver_email = db.execute("SELECT email FROM users WHERE id=?", (receiver["user_id"],)).fetchone()
    return jsonify({"ok": True})

# ══════════════════════════════════════════════════════
# ── GAME TRACKER API
# Вставь этот блок в app.py (перед if __name__ == '__main__':)
# ══════════════════════════════════════════════════════

# Миграция колонок (вызывается автоматически через init_db в before_request)
# Добавь эти строки в список migrations внутри init_db() в database.py:
#   ("users", "current_game",    "TEXT DEFAULT ''"),
#   ("users", "game_updated_at", "INTEGER DEFAULT 0"),
#   ("users", "tracker_token",   "TEXT DEFAULT ''"),


@app.route("/api/tracker/token", methods=["POST"])
def tracker_get_token():
    """
    Генерирует или возвращает tracker_token для пользователя.
    POST JSON: { "user_id": 1, "password": "..." }
    Используется клиентским скриптом при первом запуске.
    """
    data = request.get_json(force=True, silent=True) or {}
    user_id  = data.get("user_id")
    password = data.get("password", "")

    if not user_id or not password:
        return jsonify({"ok": False, "msg": "Нужен user_id и password"}), 400

    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    if not user or not check_password_hash(user["password"], password):
        return jsonify({"ok": False, "msg": "Неверные данные"}), 401

    # Если токен уже есть — возвращаем его, иначе создаём
    token = user["tracker_token"] if user["tracker_token"] else secrets.token_hex(32)
    db.execute("UPDATE users SET tracker_token=? WHERE id=?", (token, user_id))
    db.commit()
    return jsonify({"ok": True, "token": token})


@app.route("/api/tracker/update", methods=["POST"])
def tracker_update_game():
    """
    Обновляет текущую игру пользователя.
    Header: Authorization: Bearer <tracker_token>
    POST JSON: { "game": "Counter-Strike 2" }  — или пустая строка если не в игре
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return jsonify({"ok": False, "msg": "Нет токена"}), 401
    token = auth[7:].strip()

    db = get_db()
    user = db.execute("SELECT * FROM users WHERE tracker_token=?", (token,)).fetchone()
    if not user:
        return jsonify({"ok": False, "msg": "Неверный токен"}), 401

    data = request.get_json(force=True, silent=True) or {}
    game = (data.get("game") or "").strip()[:100]

    db.execute(
        "UPDATE users SET current_game=?, game_updated_at=? WHERE id=?",
        (game, int(time.time()), user["id"])
    )
    db.commit()
    return jsonify({"ok": True})


@app.route("/api/tracker/status/<int:user_id>")
def tracker_status(user_id):
    """
    Публичный эндпоинт: возвращает текущую игру пользователя.
    GET /api/tracker/status/42
    """
    db = get_db()
    user = db.execute(
        "SELECT current_game, game_updated_at FROM users WHERE id=?", (user_id,)
    ).fetchone()
    if not user:
        return jsonify({"ok": False, "msg": "Не найден"}), 404

    # Если данные старше 5 минут — считаем что не в игре
    stale = (int(time.time()) - (user["game_updated_at"] or 0)) > 300
    game = "" if stale else (user["current_game"] or "")
    return jsonify({"ok": True, "game": game})

@app.route("/api/tracker/get_token", methods=["POST"])
def get_token():
    data = request.json
    user_id = data["user_id"]

    user = db.execute(
        "SELECT token FROM users WHERE id=?",
        (user_id,)
    ).fetchone()

    if not user:
        return {"ok": False}

    return {"ok": True, "token": user["token"]}

@app.route("/api/tracker/get_token", methods=["POST"])
def get_token():
    try:
        data = request.json
        user_id = data.get("user_id")

        if not user_id:
            return {"ok": False, "error": "no user_id"}, 400

        user = db.execute(
            "SELECT tracker_token FROM users WHERE id=?",
            (user_id,)
        ).fetchone()

        if not user:
            return {"ok": False, "error": "user not found"}, 404

        return {
            "ok": True,
            "token": user["tracker_token"] or ""
        }

    except Exception as e:
        print("ERROR:", e)
        return {"ok": False, "error": str(e)}, 500

if __name__ == "__main__":
    app.run(debug=True, port=5000)
