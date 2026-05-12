 Добавь эти две строки в CREATE TABLE users в database.py
 (или запусти ALTER TABLE если БД уже существует)

 ── В CREATE TABLE users добавь после последнего поля: ──────────
   is_verified  INTEGER DEFAULT 0,
   verify_token TEXT    DEFAULT ''

# ── Если БД уже существует — запусти это один раз в Bash на PythonAnywhere: ──
 cd /home/tradeit && python3 - <<'EOF'
 import sqlite3
 db = sqlite3.connect('tradeit.db')   # или как называется твоя БД
 try:
     db.execute("ALTER TABLE users ADD COLUMN is_verified INTEGER DEFAULT 0")
     print("is_verified добавлен")
 except: print("is_verified уже есть")
 try:
     db.execute("ALTER TABLE users ADD COLUMN verify_token TEXT DEFAULT ''")
     print("verify_token добавлен")
 except: print("verify_token уже есть")
 db.commit(); db.close(); print("Готово!")
 EOF
