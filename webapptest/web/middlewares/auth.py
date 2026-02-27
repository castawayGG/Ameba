from functools import wraps
from flask import abort, redirect, url_for, flash
from flask_login import current_user
from models.user import User

# Иерархия ролей: superadmin > admin > editor > viewer
ROLE_HIERARCHY = {
    'superadmin': 4,
    'admin': 3,
    'editor': 2,
    'viewer': 1,
}


def load_user(user_id):
    """
    Функция загрузки пользователя для Flask-Login.
    """
    from web.extensions import db
    return db.session.get(User, int(user_id))


def _has_role(min_role: str) -> bool:
    """Проверяет, что текущий пользователь имеет роль не ниже min_role."""
    if not current_user.is_authenticated or not current_user.is_active:
        return False
    user_level = ROLE_HIERARCHY.get(current_user.role, 0)
    required_level = ROLE_HIERARCHY.get(min_role, 0)
    return user_level >= required_level


def admin_required(func):
    """
    Декоратор для маршрутов, требующих прав администратора (admin или выше).
    """
    @wraps(func)
    def decorated_view(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Необходимо войти в систему', 'warning')
            return redirect(url_for('admin.login'))
        if not current_user.is_active:
            abort(403, description='Аккаунт деактивирован')
        if not _has_role('admin'):
            abort(403, description='Недостаточно прав (требуется admin)')
        return func(*args, **kwargs)
    return decorated_view


def editor_required(func):
    """
    Декоратор для маршрутов, требующих прав редактора (editor или выше).
    """
    @wraps(func)
    def decorated_view(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Необходимо войти в систему', 'warning')
            return redirect(url_for('admin.login'))
        if not current_user.is_active:
            abort(403, description='Аккаунт деактивирован')
        if not _has_role('editor'):
            abort(403, description='Недостаточно прав (требуется editor)')
        return func(*args, **kwargs)
    return decorated_view


def viewer_required(func):
    """
    Декоратор для маршрутов, доступных любому аутентифицированному пользователю (viewer или выше).
    """
    @wraps(func)
    def decorated_view(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Необходимо войти в систему', 'warning')
            return redirect(url_for('admin.login'))
        if not current_user.is_active:
            abort(403, description='Аккаунт деактивирован')
        if not _has_role('viewer'):
            abort(403, description='Недостаточно прав (требуется viewer)')
        return func(*args, **kwargs)
    return decorated_view


def superadmin_required(func):
    """
    Декоратор для маршрутов, требующих прав суперадминистратора.
    """
    @wraps(func)
    def decorated_view(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Необходимо войти в систему', 'warning')
            return redirect(url_for('admin.login'))
        if not current_user.is_active:
            abort(403, description='Аккаунт деактивирован')
        if current_user.role != 'superadmin':
            abort(403, description='Недостаточно прав')
        return func(*args, **kwargs)
    return decorated_view