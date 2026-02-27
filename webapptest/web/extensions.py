from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from core.database import Base
import os

# Pass the existing declarative Base so that db.create_all() / db.drop_all()
# operate on the same metadata as the application models.
db = SQLAlchemy(model_class=Base)
login_manager = LoginManager()
migrate = Migrate()
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=os.getenv('REDIS_URL', None),
)