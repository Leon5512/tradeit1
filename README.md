# 🎧 Система техподдержки для TradeIt

## Что входит в систему

- **Тикеты** с заголовком, категорией и приоритетом
- **Чат внутри тикета** — пользователь ↔ поддержка
- **AI-автоответы** через OpenRouter (уже подключён в вашем app.py)
- **Оценка поддержки** (1–5 звёзд) после закрытия
- **Adminка**: список всех тикетов, статистика, фильтры, смена статуса
- **Статусы**: Открыт → В работе → Решён → Закрыт
- **Приоритеты**: Низкий / Обычный / Высокий
- **Polling** — новые сообщения появляются без перезагрузки страницы

---

## Установка (пошагово)

### 1. Выполни миграцию базы данных

```bash
python support_migration.py
```

Это создаст 3 новые таблицы:
- `support_tickets_v2`
- `support_messages`
- `support_ratings`

### 2. Скопируй HTML-шаблоны

```bash
cp support.html         templates/support.html
cp support_new.html     templates/support_new.html
cp support_chat.html    templates/support_chat.html
cp admin_support.html   templates/admin_support.html
```

### 3. Обнови app.py

**А) Замени старый блок техподдержки:**

Найди в `app.py` строки:
```python
# ── Техподдержка ──────────────────────────────────────
@app.route("/support", methods=["GET", "POST"])
def support():
    ...

@app.route("/api/support/send", methods=["POST"])
def api_support_send():
    ...
```
и **удали их** (оба маршрута).

**Б) Вставь содержимое `support_routes.py`** в `app.py`
на то же место (после блока кошелька, перед избранным).

### 4. Добавь ссылку в адмнике

В файле `templates/admin.html` в навигации или в нужном месте добавь:

```html
<a href="{{ url_for('admin_support') }}" class="admin-btn">🎧 Тикеты поддержки</a>
```

### 5. Готово! Проверь маршруты

| URL | Описание |
|-----|----------|
| `/support` | Список тикетов пользователя |
| `/support/new` | Создание нового тикета |
| `/support/<id>` | Чат внутри тикета |
| `/admin/support` | Панель тикетов (только для админа) |
| `/admin/support/<id>/status` | Смена статуса тикета (POST) |

---

## Структура БД (справка)

```sql
support_tickets_v2
  id, user_id, title, category, priority, status,
  created_at, updated_at, closed_at

support_messages
  id, ticket_id, user_id, is_admin, message, created_at

support_ratings
  id, ticket_id, rating, comment, created_at
```

---

## Категории и приоритеты

**Категории:**
- `payment` — Оплата и кошелёк
- `ad` — Объявления
- `account` — Аккаунт
- `message` — Сообщения
- `bug` — Ошибка на сайте
- `other` — Другое

**Приоритеты:**
- `low` — 🟢 Низкий
- `normal` — 🟡 Обычный
- `high` — 🔴 Высокий
