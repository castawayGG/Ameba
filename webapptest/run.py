#!/usr/bin/env python3
"""
Точка входа для запуска приложения в режиме разработки.
Используйте `python run.py` для запуска Flask-сервера.
"""
from web.app import create_app

app = create_app()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)