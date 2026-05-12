# АвитоКлон

Полноценный клон Авито на Python (Flask) + SQLite.

## Возможности
- Регистрация и вход в аккаунт
- Публикация объявлений с фото
- Поиск и фильтрация по категориям
- Профили пользователей
- Система личных сообщений (чат)
- Счётчик непрочитанных сообщений

## Запуск

### 1. Установи зависимости
```
pip install -r requirements.txt
```

### 2. Запусти сервер
```
python app.py
```

### 3. Открой в браузере
```
http://localhost:5000
```

## Структура
```
avito_clone/
├── app.py           # Flask-сервер, все маршруты
├── database.py      # Инициализация SQLite
├── requirements.txt
├── avito.db         # База данных (создаётся автоматически)
├── templates/       # HTML-шаблоны
│   ├── base.html
│   ├── index.html
│   ├── login.html
│   ├── register.html
│   ├── new_ad.html
│   ├── view_ad.html
│   ├── profile.html
│   ├── messages.html
│   └── chat.html
└── static/
    └── uploads/     # Загруженные фото объявлений
```
