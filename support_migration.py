"""
Миграция базы данных для системы техподдержки TradeIt.
Запусти: python support_migration.py
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tradeit.db")

def migrate():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Создаём новую таблицу тикетов (заменяет старую support_tickets)
    c.executescript("""
    -- Тикеты поддержки (основная таблица)
    CREATE TABLE IF NOT EXISTS support_tickets_v2 (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id     INTEGER NOT NULL,
        title       TEXT NOT NULL DEFAULT 'Обращение',
        category    TEXT NOT NULL DEFAULT 'other',
        priority    TEXT NOT NULL DEFAULT 'normal',
        status      TEXT NOT NULL DEFAULT 'open',
        created_at  INTEGER NOT NULL,
        updated_at  INTEGER NOT NULL,
        closed_at   INTEGER,
        FOREIGN KEY(user_id) REFERENCES users(id)
    );

    -- Сообщения внутри тикета
    CREATE TABLE IF NOT EXISTS support_messages (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        ticket_id   INTEGER NOT NULL,
        user_id     INTEGER NOT NULL,
        is_admin    INTEGER NOT NULL DEFAULT 0,
        message     TEXT NOT NULL,
        created_at  INTEGER NOT NULL,
        FOREIGN KEY(ticket_id) REFERENCES support_tickets_v2(id),
        FOREIGN KEY(user_id)   REFERENCES users(id)
    );

    -- Рейтинги поддержки
    CREATE TABLE IF NOT EXISTS support_ratings (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        ticket_id   INTEGER NOT NULL UNIQUE,
        rating      INTEGER NOT NULL,
        comment     TEXT,
        created_at  INTEGER NOT NULL,
        FOREIGN KEY(ticket_id) REFERENCES support_tickets_v2(id)
    );

    CREATE INDEX IF NOT EXISTS idx_st_user   ON support_tickets_v2(user_id);
    CREATE INDEX IF NOT EXISTS idx_st_status ON support_tickets_v2(status);
    CREATE INDEX IF NOT EXISTS idx_sm_ticket ON support_messages(ticket_id);
    """)

    conn.commit()
    conn.close()
    print("✅ Миграция выполнена успешно!")

if __name__ == "__main__":
    migrate()
