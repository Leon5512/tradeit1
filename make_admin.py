import sqlite3
db = sqlite3.connect('avito.db')
db.execute("UPDATE users SET is_admin=1 WHERE username='leon5512'")
db.commit()
print('Готово!')
db.close()