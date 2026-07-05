# -*- coding: utf-8 -*-
"""
Система пополнения баланса по ключам.

Логика:
- Только админ создаёт ключ на определённую сумму (в /admin/keys).
- Админ передаёт код ключа пользователю любым удобным способом (чат, лично и т.д.).
- Пользователь вводит код у себя в кошельке — баланс пополняется на сумму
  ключа, ключ становится одноразовым и больше не может быть использован.

Подключение в app.py:

    from balance_keys import keys_bp, init_keys_db
    app.register_blueprint(keys_bp)

    # в setup(), рядом с init_db()/init_nft_db()
    init_keys_db(get_db())
"""

import time
import secrets
import string
from flask import Blueprint, request, session, redirect, url_for, flash, jsonify, render_template, abort

from database import get_db

keys_bp = Blueprint("keys", __name__)

_ALPHABET = string.ascii_uppercase + string.digits


def init_keys_db(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS balance_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            amount REAL NOT NULL,
            created_by INTEGER NOT NULL,
            created_at INTEGER NOT NULL,
            used_by INTEGER,
            used_at INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_balance_keys_code ON balance_keys(code);
    """)
    db.commit()


def _generate_code():
    groups = ["".join(secrets.choice(_ALPHABET) for _ in range(4)) for _ in range(4)]
    return "-".join(groups)


def _require_admin():
    if "user_id" not in session:
        abort(redirect(url_for("login")))
    if not session.get("is_admin") or not session.get("admin_unlocked"):
        abort(403)


# ── Админ: страница управления ключами ───────────────
@keys_bp.route("/admin/keys")
def admin_keys():
    if "user_id" not in session:
        return redirect(url_for("login"))
    if not session.get("is_admin") or not session.get("admin_unlocked"):
        abort(403)
    db = get_db()
    rows = db.execute("""
        SELECT k.*, c.username AS creator_name, u.username AS used_by_name
        FROM balance_keys k
        JOIN users c ON k.created_by = c.id
        LEFT JOIN users u ON k.used_by = u.id
        ORDER BY k.created_at DESC
        LIMIT 200
    """).fetchall()
    return render_template("admin_keys.html", keys=rows)


@keys_bp.route("/admin/keys/create", methods=["POST"])
def admin_keys_create():
    if "user_id" not in session:
        return redirect(url_for("login"))
    if not session.get("is_admin") or not session.get("admin_unlocked"):
        abort(403)
    try:
        amount = float(request.form.get("amount", "0"))
    except ValueError:
        amount = 0
    if amount <= 0 or amount > 10_000_000:
        flash("Укажи корректную сумму ключа", "error")
        return redirect(url_for("keys.admin_keys"))

    db = get_db()
    code = _generate_code()
    # на случай крайне редкой коллизии — пробуем ещё раз
    while db.execute("SELECT 1 FROM balance_keys WHERE code=?", (code,)).fetchone():
        code = _generate_code()

    db.execute(
        "INSERT INTO balance_keys (code, amount, created_by, created_at) VALUES (?,?,?,?)",
        (code, amount, session["user_id"], int(time.time())),
    )
    db.commit()
    flash(f"Ключ создан: {code} — на {amount:,.0f} TEITS".replace(",", " "), "success")
    return redirect(url_for("keys.admin_keys"))


@keys_bp.route("/admin/keys/<int:key_id>/delete", methods=["POST"])
def admin_keys_delete(key_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    if not session.get("is_admin") or not session.get("admin_unlocked"):
        abort(403)
    db = get_db()
    key = db.execute("SELECT * FROM balance_keys WHERE id=?", (key_id,)).fetchone()
    if key and key["used_by"] is None:
        db.execute("DELETE FROM balance_keys WHERE id=?", (key_id,))
        db.commit()
        flash("Ключ удалён", "success")
    else:
        flash("Можно удалить только неиспользованный ключ", "error")
    return redirect(url_for("keys.admin_keys"))


# ── Пользователь: погашение ключа в кошельке ──────────
@keys_bp.route("/api/wallet/redeem", methods=["POST"])
def api_wallet_redeem():
    if "user_id" not in session:
        return jsonify({"ok": False, "msg": "Войди в аккаунт"})
    data = request.get_json(silent=True) or {}
    code = (data.get("code") or "").strip().upper()
    if not code:
        return jsonify({"ok": False, "msg": "Введи код ключа"})

    uid = session["user_id"]
    db = get_db()
    key = db.execute("SELECT * FROM balance_keys WHERE code=?", (code,)).fetchone()
    if not key:
        return jsonify({"ok": False, "msg": "Ключ не найден"})
    if key["used_by"] is not None:
        return jsonify({"ok": False, "msg": "Этот ключ уже был использован"})

    now = int(time.time())
    db.execute("UPDATE balance_keys SET used_by=?, used_at=? WHERE id=?", (uid, now, key["id"]))
    db.execute("UPDATE users SET balance = balance + ? WHERE id=?", (key["amount"], uid))
    db.execute(
        "INSERT INTO transactions (user_id, amount, type, description, created_at) VALUES (?,?,?,?,?)",
        (uid, key["amount"], "key_redeem", f"Пополнение по ключу {code}", now),
    )
    db.commit()
    new_balance = db.execute("SELECT balance FROM users WHERE id=?", (uid,)).fetchone()[0]
    return jsonify({"ok": True, "balance": new_balance, "amount": key["amount"]})
