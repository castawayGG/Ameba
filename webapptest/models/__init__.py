# Инициализационный файл для пакета models.
# Импортируем все модели, чтобы SQLAlchemy могла их обнаружить.
from models.user import User
from models.account import Account
from models.proxy import Proxy
from models.admin_log import AdminLog
from models.campaign import Campaign
from models.stat import Stat

# Список всех моделей для удобного импорта
__all__ = [
    'User',
    'Account',
    'Proxy',
    'AdminLog',
    'Campaign',
    'Stat',
]