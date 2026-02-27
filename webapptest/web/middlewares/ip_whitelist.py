from flask import request, abort, current_app
from core.config import Config

def whitelist_middleware():
    """
    Middleware для проверки IP-адреса при доступе к админ-панели.
    Если задан список IP_WHITELIST и IP клиента не входит в него,
    доступ запрещается (403).
    """
    # Проверяем только для путей, начинающихся с /admin
    if request.path.startswith('/admin'):
        client_ip = request.remote_addr
        # Если белый список задан и не пуст
        if Config.IP_WHITELIST and client_ip not in Config.IP_WHITELIST:
            current_app.logger.warning(f"Blocked access from {client_ip} to admin panel")
            abort(403, description="Access denied: IP not in whitelist")