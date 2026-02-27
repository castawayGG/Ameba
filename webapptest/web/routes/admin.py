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
    if phone_filter:
        stmt = stmt.filter(Account.phone.contains(phone_filter))
    if status_filter:
        stmt = stmt.filter(Account.status == status_filter)

    accounts_paginated = db.paginate(stmt, page=page, per_page=per_page)
    proxies = db.session.execute(select(Proxy).filter_by(enabled=True)).scalars().all()
    return render_template('admin/accounts.html',
                           accounts=accounts_paginated,
                           proxies=proxies,
                           phone_filter=phone_filter,
                           status_filter=status_filter)

@admin_bp.route('/proxies')
@login_required
def proxies():
    proxies_list = db.session.execute(select(Proxy).order_by(desc(Proxy.id))).scalars().all()
    return render_template('admin/proxies.html', proxies=proxies_list)

@admin_bp.route('/campaigns')
@login_required
def campaigns():
    campaigns_list = db.session.execute(select(Campaign).order_by(desc(Campaign.created_at))).scalars().all()
    return render_template('admin/campaigns.html', campaigns=campaigns_list)

@admin_bp.route('/users')
@login_required
@admin_required
def users():
    users_list = db.session.execute(select(User)).scalars().all()
    return render_template('admin/users.html', users=users_list)

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
    return render_template('admin/settings.html', backups=backups, api_settings=api_settings, rate_limits=rate_limits)


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


# ==========================================
# 9. ЭКСПОРТ ДАННЫХ
# ==========================================
@admin_bp.route('/export/accounts')
@login_required
def export_accounts():
    from services.export.excel import ExcelExporter
    accounts = db.session.execute(select(Account)).scalars().all()
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
