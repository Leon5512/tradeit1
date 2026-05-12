# Этот файл нужен для PythonAnywhere
# Путь: /var/www/ТВОЙ_ЛОГИН_pythonanywhere_com_wsgi.py
# Замени ВАШ_ЛОГИН на свой логин PythonAnywhere

import sys
import os

# Путь к папке с проектом
project_home = '/home/tradeit'

if project_home not in sys.path:
    sys.path.insert(0, project_home)

os.chdir(project_home)

from app import app as application
