from functools import wraps
from flask import abort, redirect, url_for, flash
from flask_login import current_user
from models.user import User

def load_user(user_id):
    """
    Функция загрузки пользователя для Flask-Login.
    """
    from web.extensions import db
    return db.session.get(User, int(user_id))

def admin_required(func):
    """
    Декоратор для маршрутов, требующих прав администратора или выше.
    Роли с правом записи: admin, superadmin, editor.
    Роль viewer имеет доступ только к чтению.
    """
    @wraps(func)
    def decorated_view(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Необходимо войти в систему', 'warning')
            return redirect(url_for('admin.login'))
        if not current_user.is_active:
            abort(403, description='Аккаунт деактивирован')
        # viewer имеет права только на чтение – запрещаем мутирующие действия
        if current_user.role == 'viewer':
            abort(403, description='Недостаточно прав: роль viewer доступна только для просмотра')
        return func(*args, **kwargs)
    return decorated_view


def editor_required(func):
    """
    Декоратор для маршрутов, доступных editor/admin/superadmin, но не viewer.
    Псевдоним admin_required – оставлен для семантической ясности.
    """
    return admin_required(func)

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