from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix
from core.config import Config
from core.logger import log
from web.extensions import db, login_manager, limiter, migrate
from web.middlewares.auth import load_user
from web.middlewares.ip_whitelist import whitelist_middleware

# Импорт всех моделей обязателен до db.create_all()
from models.user import User
from models.account import Account
from models.proxy import Proxy
from models.campaign import Campaign
from models.stat import Stat
from models.admin_log import AdminLog
from models.task import Task


def create_app(test_config=None):
    app = Flask(__name__,
                template_folder='templates',
                static_folder='static',
                static_url_path='/static')

    app.config.from_object(Config)

    if test_config is not None:
        app.config.from_mapping(test_config)

    if not app.config.get('SECRET_KEY') or app.config['SECRET_KEY'] == 'dev-key-123':
        if not app.config.get('TESTING'):
            log.warning("SECRET_KEY is not set or uses insecure default. Set SECRET_KEY env variable in production.")

    # Trust the X-Forwarded-For header from Nginx (1 proxy in front)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    limiter.init_app(app)

    login_manager.login_view = 'admin.login'
    login_manager.login_message = 'Пожалуйста, войдите для доступа к этой странице.'
    login_manager.user_loader(load_user)

    app.before_request(whitelist_middleware)

    # Регистрация фильтра
    @app.template_filter('timestamp_to_date')
    def timestamp_to_date_filter(dt):
        if not dt:
            return '—'
        return dt.strftime('%d.%m.%Y %H:%M')

    from web.routes.public import public_bp
    from web.routes.admin import admin_bp
    from web.routes.api import api_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(api_bp, url_prefix='/api')

    with app.app_context():
        # Use Flask-SQLAlchemy's engine so the correct DB is always targeted
        db.create_all()

        _maybe_create_initial_admin(app)

    log.info("Flask application created successfully")
    return app


def _maybe_create_initial_admin(app):
    """Create the initial superadmin if no users exist yet (race-safe)."""
    from sqlalchemy.exc import IntegrityError
    admin_username = app.config.get('ADMIN_USERNAME') or Config.ADMIN_USERNAME
    admin_hash = app.config.get('ADMIN_PASSWORD_HASH') or Config.ADMIN_PASSWORD_HASH
    if not admin_username or not admin_hash:
        return
    try:
        if db.session.query(User).first():
            return
        admin = User(username=admin_username, role='superadmin')
        admin.password_hash = admin_hash
        db.session.add(admin)
        db.session.commit()
        log.info(f"Initial admin created: {admin_username}")
    except IntegrityError:
        db.session.rollback()
        log.info("Initial admin already exists (concurrent creation)")
    except Exception as e:
        db.session.rollback()
        log.error(f"Failed to create initial admin: {e}")


app = create_app()
