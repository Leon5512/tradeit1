# -*- coding: utf-8 -*-
"""
Blueprint системы подарков и их NFT-улучшения.

Подключение в app.py:

    from nft_routes import nft_bp, init_nft_db
    app.register_blueprint(nft_bp)

    # внутри @app.before_request def setup(): рядом с init_db()
    init_nft_db(get_db())

И добавь ссылку в nav (base.html):
    <a href="{{ url_for('nft.gifts_shop') }}" class="btn btn-ghost btn-sm">🎁 Подарки</a>
"""

import time
from flask import Blueprint, render_template, request, session, redirect, url_for, flash, jsonify, abort

from database import get_db
from nft_gifts import (
    GIFT_CATALOG, RARITY_LABELS, RARITY_COLORS, RARITY_ORDER,
    roll_nft_attributes, model_drop_chance,
)

nft_bp = Blueprint("nft", __name__)


def init_nft_db(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS gifts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            gift_type TEXT NOT NULL,
            is_nft INTEGER DEFAULT 0,
            nft_model TEXT DEFAULT '',
            nft_tier TEXT DEFAULT '',
            nft_backdrop TEXT DEFAULT '',
            nft_pattern TEXT DEFAULT '',
            nft_number INTEGER DEFAULT 0,
            for_sale INTEGER DEFAULT 0,
            sale_price REAL DEFAULT 0,
            created_at INTEGER NOT NULL,
            upgraded_at INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS nft_mint_counters (
            gift_type TEXT PRIMARY KEY,
            last_number INTEGER DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_gifts_user ON gifts(user_id);
        CREATE INDEX IF NOT EXISTS idx_gifts_nft ON gifts(is_nft);
    """)
    db.commit()


def _gift_row_to_dict(row):
    d = dict(row)
    cfg = GIFT_CATALOG.get(d["gift_type"], {})
    d["gift_name"] = cfg.get("name", d["gift_type"])
    d["emoji"] = cfg.get("emoji", "🎁")
    d["supply"] = cfg.get("supply", 0)
    if d["is_nft"]:
        d["tier_label"] = RARITY_LABELS.get(d["nft_tier"], d["nft_tier"])
        d["tier_color"] = RARITY_COLORS.get(d["nft_tier"], "#8a97a8")
    return d


# ── Магазин подарков ─────────────────────────────────
@nft_bp.route("/gifts")
def gifts_shop():
    if "user_id" not in session:
        return redirect(url_for("login"))
    db = get_db()
    balance_row = db.execute("SELECT balance FROM users WHERE id=?", (session["user_id"],)).fetchone()
    balance = balance_row["balance"] if balance_row else 0
    catalog = []
    for gift_type, cfg in GIFT_CATALOG.items():
        item = dict(cfg)
        item["type"] = gift_type
        item["models_display"] = [
            {"name": m[0], "tier": m[2], "tier_label": RARITY_LABELS[m[2]],
             "color": RARITY_COLORS[m[2]], "chance": model_drop_chance(gift_type, m[0])}
            for m in cfg["models"]
        ]
        catalog.append(item)
    return render_template("nft_shop.html", catalog=catalog, balance=balance)


@nft_bp.route("/api/gifts/buy", methods=["POST"])
def api_buy_gift():
    if "user_id" not in session:
        return jsonify({"ok": False, "msg": "Войди в аккаунт"})
    data = request.get_json(silent=True) or {}
    gift_type = data.get("gift_type", "")
    cfg = GIFT_CATALOG.get(gift_type)
    if not cfg:
        return jsonify({"ok": False, "msg": "Такого подарка не существует"})

    uid = session["user_id"]
    db = get_db()
    user = db.execute("SELECT balance FROM users WHERE id=?", (uid,)).fetchone()
    if not user or user["balance"] < cfg["price"]:
        return jsonify({"ok": False, "msg": "Недостаточно средств на балансе"})

    now = int(time.time())
    db.execute("UPDATE users SET balance = balance - ? WHERE id=?", (cfg["price"], uid))
    db.execute(
        "INSERT INTO gifts (user_id, gift_type, is_nft, created_at) VALUES (?,?,0,?)",
        (uid, gift_type, now),
    )
    db.execute(
        "INSERT INTO transactions (user_id, amount, type, description, created_at) VALUES (?,?,?,?,?)",
        (uid, -cfg["price"], "gift_buy", f"Покупка подарка «{cfg['name']}»", now),
    )
    db.commit()
    new_balance = db.execute("SELECT balance FROM users WHERE id=?", (uid,)).fetchone()[0]
    return jsonify({"ok": True, "balance": new_balance})


# ── Инвентарь подарков ───────────────────────────────
@nft_bp.route("/gifts/mine")
def gifts_mine():
    if "user_id" not in session:
        return redirect(url_for("login"))
    db = get_db()
    rows = db.execute(
        "SELECT * FROM gifts WHERE user_id=? ORDER BY is_nft ASC, created_at DESC",
        (session["user_id"],),
    ).fetchall()
    gifts = [_gift_row_to_dict(r) for r in rows]
    return render_template("nft_inventory.html", gifts=gifts, catalog=GIFT_CATALOG,
                            upgrade_costs={k: v["upgrade_cost"] for k, v in GIFT_CATALOG.items()})


# ── Улучшение до NFT ──────────────────────────────────
@nft_bp.route("/api/gifts/<int:gift_id>/upgrade", methods=["POST"])
def api_upgrade_gift(gift_id):
    if "user_id" not in session:
        return jsonify({"ok": False, "msg": "Войди в аккаунт"})
    uid = session["user_id"]
    db = get_db()
    gift = db.execute("SELECT * FROM gifts WHERE id=? AND user_id=?", (gift_id, uid)).fetchone()
    if not gift:
        return jsonify({"ok": False, "msg": "Подарок не найден"})
    if gift["is_nft"]:
        return jsonify({"ok": False, "msg": "Этот подарок уже улучшен до NFT"})

    cfg = GIFT_CATALOG.get(gift["gift_type"])
    if not cfg:
        return jsonify({"ok": False, "msg": "Неизвестный тип подарка"})

    user = db.execute("SELECT balance FROM users WHERE id=?", (uid,)).fetchone()
    if user["balance"] < cfg["upgrade_cost"]:
        return jsonify({"ok": False, "msg": "Недостаточно средств для улучшения"})

    # Проверяем лимит тиража коллекции
    minted = db.execute(
        "SELECT COALESCE(last_number,0) AS n FROM nft_mint_counters WHERE gift_type=?",
        (gift["gift_type"],),
    ).fetchone()
    current_minted = minted["n"] if minted else 0
    if current_minted >= cfg["supply"]:
        return jsonify({"ok": False, "msg": "Тираж этой NFT-коллекции полностью выпущен"})

    model_name, model_tier, backdrop_name, pattern_name = roll_nft_attributes(gift["gift_type"])

    now = int(time.time())
    db.execute("UPDATE users SET balance = balance - ? WHERE id=?", (cfg["upgrade_cost"], uid))

    db.execute(
        "INSERT INTO nft_mint_counters (gift_type, last_number) VALUES (?,1) "
        "ON CONFLICT(gift_type) DO UPDATE SET last_number = last_number + 1",
        (gift["gift_type"],),
    )
    number_row = db.execute(
        "SELECT last_number FROM nft_mint_counters WHERE gift_type=?", (gift["gift_type"],)
    ).fetchone()
    mint_number = number_row["last_number"]

    db.execute(
        """UPDATE gifts SET is_nft=1, nft_model=?, nft_tier=?, nft_backdrop=?, nft_pattern=?,
           nft_number=?, upgraded_at=? WHERE id=?""",
        (model_name, model_tier, backdrop_name, pattern_name, mint_number, now, gift_id),
    )
    db.execute(
        "INSERT INTO transactions (user_id, amount, type, description, created_at) VALUES (?,?,?,?,?)",
        (uid, -cfg["upgrade_cost"], "nft_upgrade", f"Улучшение «{cfg['name']}» до NFT", now),
    )
    db.commit()

    new_balance = db.execute("SELECT balance FROM users WHERE id=?", (uid,)).fetchone()[0]
    return jsonify({
        "ok": True,
        "balance": new_balance,
        "gift": {
            "id": gift_id,
            "gift_name": cfg["name"],
            "emoji": cfg["emoji"],
            "model": model_name,
            "tier": model_tier,
            "tier_label": RARITY_LABELS[model_tier],
            "tier_color": RARITY_COLORS[model_tier],
            "backdrop": backdrop_name,
            "pattern": pattern_name,
            "number": mint_number,
            "supply": cfg["supply"],
        },
    })


# ── Карточка NFT ──────────────────────────────────────
@nft_bp.route("/gifts/<int:gift_id>")
def gift_card(gift_id):
    db = get_db()
    row = db.execute(
        "SELECT g.*, u.username FROM gifts g JOIN users u ON g.user_id=u.id WHERE g.id=?",
        (gift_id,),
    ).fetchone()
    if not row:
        flash("Подарок не найден", "error")
        return redirect(url_for("index"))
    is_owner = session.get("user_id") == row["user_id"]
    if not row["is_nft"] and not is_owner:
        abort(403)
    gift = _gift_row_to_dict(row)
    return render_template("nft_card.html", gift=gift, is_owner=is_owner)


# ── Выставить NFT на продажу (использует уже готовый механизм объявлений) ──
@nft_bp.route("/gifts/<int:gift_id>/sell", methods=["POST"])
def gift_sell(gift_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    db = get_db()
    gift = db.execute("SELECT * FROM gifts WHERE id=? AND user_id=?", (gift_id, session["user_id"])).fetchone()
    if not gift or not gift["is_nft"]:
        flash("NFT не найден", "error")
        return redirect(url_for("gifts_mine"))
    price = request.form.get("price", "").strip()
    try:
        price_val = float(price)
        if price_val <= 0:
            raise ValueError
    except ValueError:
        flash("Укажи корректную цену", "error")
        return redirect(url_for("nft.gift_card", gift_id=gift_id))

    cfg = GIFT_CATALOG[gift["gift_type"]]
    title = f"NFT «{cfg['name']}» — {gift['nft_model']} #{gift['nft_number']}"
    description = (
        f"{RARITY_LABELS[gift['nft_tier']]} NFT-подарок из коллекции «{cfg['name']}».\n"
        f"Модель: {gift['nft_model']}\nФон: {gift['nft_backdrop']}\nПаттерн: {gift['nft_pattern']}\n"
        f"Номер экземпляра: #{gift['nft_number']} из {cfg['supply']}."
    )
    now = int(time.time())
    db.execute(
        "INSERT INTO ads (user_id,title,description,price,category,city,image,active,created_at) "
        "VALUES (?,?,?,?,?,?,?,1,?)",
        (session["user_id"], title, description, price_val, "NFT-подарки", "", "", now),
    )
    db.execute("UPDATE gifts SET for_sale=1, sale_price=? WHERE id=?", (price_val, gift_id))
    db.commit()
    flash("NFT выставлен на продажу как объявление!", "success")
    return redirect(url_for("gifts_mine"))
