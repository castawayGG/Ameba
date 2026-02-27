from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from web.extensions import limiter

# уже инициализирован в extensions.py, здесь можно добавить дополнительные правила
def rate_limit_middleware():
    pass  # используется через декораторы