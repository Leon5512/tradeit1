# -*- coding: utf-8 -*-
"""
Система NFT-улучшения подарков (по мотивам Telegram Gifts).

Пользователь покупает обычный подарок за баланс сайта, затем может
"улучшить" его до NFT-версии: сервер случайно выбирает модель/фон/паттерн
по весам редкости и присваивает подарку уникальный порядковый номер
в рамках лимитированного тиража коллекции.
"""

import random

RARITY_LABELS = {
    "common": "Обычная",
    "rare": "Редкая",
    "epic": "Эпическая",
    "legendary": "Легендарная",
}

RARITY_COLORS = {
    "common": "#8a97a8",
    "rare": "#3b82f6",
    "epic": "#a855f7",
    "legendary": "#f4b400",
}

RARITY_ORDER = ["common", "rare", "epic", "legendary"]

# Каждая коллекция: базовая цена подарка, стоимость улучшения в NFT,
# тираж (максимум NFT-экземпляров этого типа) и весовые таблицы атрибутов.
# models несут вес + тир редкости, backdrops/patterns — чисто косметические веса.
GIFT_CATALOG = {
    "teddy": {
        "name": "Плюшевый мишка",
        "emoji": "🧸",
        "price": 300,
        "upgrade_cost": 400,
        "supply": 5000,
        "models": [
            ("Классический мишка", 60, "common"),
            ("Серебряный мишка", 25, "rare"),
            ("Золотой мишка", 11, "epic"),
            ("Алмазный мишка", 4, "legendary"),
        ],
        "backdrops": [
            ("Мятный", 35), ("Розовый закат", 30), ("Ночная галактика", 25), ("Огненный", 10),
        ],
        "patterns": [
            ("Горошек", 45), ("Звёзды", 30), ("Молнии", 18), ("Корона", 7),
        ],
    },
    "rose": {
        "name": "Вечная роза",
        "emoji": "🌹",
        "price": 450,
        "upgrade_cost": 600,
        "supply": 3000,
        "models": [
            ("Алая роза", 58, "common"),
            ("Хрустальная роза", 27, "rare"),
            ("Чёрная роза", 11, "epic"),
            ("Радужная роза", 4, "legendary"),
        ],
        "backdrops": [
            ("Сад", 35), ("Сумерки", 30), ("Мрамор", 25), ("Аврора", 10),
        ],
        "patterns": [
            ("Лепестки", 45), ("Роса", 28), ("Терн", 20), ("Сияние", 7),
        ],
    },
    "ring": {
        "name": "Кольцо удачи",
        "emoji": "💍",
        "price": 700,
        "upgrade_cost": 900,
        "supply": 2000,
        "models": [
            ("Серебряное кольцо", 55, "common"),
            ("Платиновое кольцо", 28, "rare"),
            ("Изумрудное кольцо", 12, "epic"),
            ("Кольцо кометы", 5, "legendary"),
        ],
        "backdrops": [
            ("Бархат", 35), ("Полночь", 30), ("Опал", 25), ("Космос", 10),
        ],
        "patterns": [
            ("Гравировка", 45), ("Руны", 28), ("Искры", 20), ("Корона", 7),
        ],
    },
    "rocket": {
        "name": "Ракета удачи",
        "emoji": "🚀",
        "price": 900,
        "upgrade_cost": 1200,
        "supply": 1500,
        "models": [
            ("Стартовая ракета", 55, "common"),
            ("Титановая ракета", 27, "rare"),
            ("Плазменная ракета", 13, "epic"),
            ("Ракета вне закона", 5, "legendary"),
        ],
        "backdrops": [
            ("Стартовая площадка", 35), ("Стратосфера", 30), ("Туманность", 25), ("Чёрная дыра", 10),
        ],
        "patterns": [
            ("Полосы", 45), ("Пламя", 28), ("Звёздный след", 20), ("Молния", 7),
        ],
    },
    "crown": {
        "name": "Корона чемпиона",
        "emoji": "👑",
        "price": 1500,
        "upgrade_cost": 2000,
        "supply": 800,
        "models": [
            ("Бронзовая корона", 55, "common"),
            ("Серебряная корона", 27, "rare"),
            ("Золотая корона", 13, "epic"),
            ("Корона легенды", 5, "legendary"),
        ],
        "backdrops": [
            ("Трон", 35), ("Закат империи", 30), ("Мрамор", 25), ("Небо в огне", 10),
        ],
        "patterns": [
            ("Самоцветы", 45), ("Лавры", 28), ("Пламя", 20), ("Звёздная пыль", 7),
        ],
    },
}


def weighted_choice(options):
    """options: список (name, weight) или (name, weight, tier). Возвращает выбранный элемент целиком."""
    weights = [o[1] for o in options]
    return random.choices(options, weights=weights, k=1)[0]


def roll_nft_attributes(gift_type):
    """Возвращает (model, model_tier, backdrop, pattern) для данного типа подарка."""
    cfg = GIFT_CATALOG[gift_type]
    model_name, _, model_tier = weighted_choice(cfg["models"])
    backdrop_name, _ = weighted_choice(cfg["backdrops"])
    pattern_name, _ = weighted_choice(cfg["patterns"])
    return model_name, model_tier, backdrop_name, pattern_name


def model_drop_chance(gift_type, model_name):
    """Процент шанса выпадения конкретной модели (для отображения в каталоге)."""
    cfg = GIFT_CATALOG[gift_type]
    total = sum(m[1] for m in cfg["models"])
    for name, weight, tier in cfg["models"]:
        if name == model_name:
            return round(weight / total * 100, 1)
    return 0
