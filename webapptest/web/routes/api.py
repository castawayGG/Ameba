from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from web.middlewares.auth import admin_required
from web.extensions import db
from models.account import Account
from models.proxy import Proxy
from models.campaign import Campaign
from models.stat import Stat
from models.task import Task
from models.chat_tag import ChatTag, DialogTag
from services.telegram.actions import send_bulk_messages, join_group, change_account_password, enable_2fa
from tasks.celery_app import celery_app
from celery.result import AsyncResult
import json
import datetime

api_bp = Blueprint('api', __name__)

# -------------------- Task Center (Celery) --------------------

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


@api_bp.route('/tasks/active', methods=['GET'])
@login_required
@admin_required
def tasks_active():
    """
    Список активных и недавно выполненных Celery-задач.
    Возвращает задачи из таблицы Task с прогрессом.
    """
    tasks = (
        db.session.query(Task)
        .filter(Task.status.in_(['PENDING', 'STARTED', 'RECEIVED', 'RETRY',
                                  'pending', 'running']))
        .order_by(Task.created_at.desc())
        .limit(50)
        .all()
    )
    result = []
    for t in tasks:
        celery_result = AsyncResult(t.task_id, app=celery_app) if t.task_id else None
        result.append({
            'id': t.id,
            'task_id': t.task_id,
            'name': t.name,
            'status': celery_result.status if celery_result else t.status,
            'progress': None,
            'created_at': t.created_at.isoformat() if t.created_at else None,
        })
    return jsonify(result)


@api_bp.route('/tasks/<task_id>/revoke', methods=['POST'])
@login_required
@admin_required
def task_revoke(task_id):
    """Отзыв (отмена) фоновой Celery-задачи."""
    terminate = (request.get_json() or {}).get('terminate', False)
    celery_app.control.revoke(task_id, terminate=terminate)
    # Обновляем статус в БД, если задача есть
    db_task = db.session.query(Task).filter_by(task_id=task_id).first()
    if db_task:
        db_task.status = 'REVOKED'
        db.session.commit()
    return jsonify({'success': True, 'task_id': task_id})


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
    ids = (request.get_json() or {}).get('ids', [])
    from tasks.proxy_checker import bulk_check_proxies
    task = bulk_check_proxies.delay(ids)
    return jsonify({'success': True, 'task_id': task.id})

# -------------------- Кампании --------------------
@api_bp.route('/campaigns/<int:campaign_id>/start', methods=['POST'])
@login_required
@admin_required
def start_campaign_api(campaign_id):
    """Запуск кампании (асинхронно)."""
    campaign = db.session.get(Campaign, campaign_id)
    if not campaign:
        return jsonify({'success': False, 'error': 'Кампания не найдена'}), 404
    if campaign.status not in ('draft', 'paused'):
        return jsonify({'success': False, 'error': f'Нельзя запустить кампанию со статусом {campaign.status}'}), 400
    campaign.status = 'running'
    db.session.commit()
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


# -------------------- CRM: теги диалогов (Inbox) --------------------

@api_bp.route('/chat-tags', methods=['GET'])
@login_required
@admin_required
def list_chat_tags():
    """Список всех доступных тегов для диалогов."""
    tags = db.session.query(ChatTag).order_by(ChatTag.name).all()
    return jsonify([{'id': t.id, 'name': t.name, 'color': t.color} for t in tags])


@api_bp.route('/chat-tags', methods=['POST'])
@login_required
@admin_required
def create_chat_tag():
    """Создание нового тега."""
    data = request.get_json() or {}
    name = (data.get('name') or '').strip()
    if not name:
        return jsonify({'success': False, 'error': 'name обязателен'}), 400
    if db.session.query(ChatTag).filter_by(name=name).first():
        return jsonify({'success': False, 'error': 'Тег с таким именем уже существует'}), 409
    tag = ChatTag(name=name, color=data.get('color', '#6B7280'))
    db.session.add(tag)
    db.session.commit()
    return jsonify({'success': True, 'id': tag.id, 'name': tag.name, 'color': tag.color}), 201


@api_bp.route('/chat-tags/<int:tag_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_chat_tag(tag_id):
    """Удаление тега (и всех его привязок к диалогам)."""
    tag = db.session.get(ChatTag, tag_id)
    if not tag:
        return jsonify({'success': False, 'error': 'Тег не найден'}), 404
    db.session.delete(tag)
    db.session.commit()
    return jsonify({'success': True})


@api_bp.route('/dialog-tags', methods=['GET'])
@login_required
@admin_required
def get_dialog_tags():
    """Получить теги конкретного диалога (account_id + peer_id)."""
    account_id = request.args.get('account_id')
    peer_id = request.args.get('peer_id')
    if not account_id or not peer_id:
        return jsonify({'success': False, 'error': 'account_id и peer_id обязательны'}), 400
    rows = (
        db.session.query(DialogTag, ChatTag)
        .join(ChatTag, DialogTag.tag_id == ChatTag.id)
        .filter(DialogTag.account_id == account_id, DialogTag.peer_id == peer_id)
        .all()
    )
    return jsonify([{'id': dt.id, 'tag_id': ct.id, 'name': ct.name, 'color': ct.color} for dt, ct in rows])


@api_bp.route('/dialog-tags', methods=['POST'])
@login_required
@admin_required
def add_dialog_tag():
    """Добавить тег к диалогу."""
    data = request.get_json() or {}
    account_id = data.get('account_id')
    peer_id = data.get('peer_id')
    tag_id = data.get('tag_id')
    if not account_id or not peer_id or not tag_id:
        return jsonify({'success': False, 'error': 'account_id, peer_id и tag_id обязательны'}), 400
    # Проверяем, что тег существует
    tag = db.session.get(ChatTag, tag_id)
    if not tag:
        return jsonify({'success': False, 'error': 'Тег не найден'}), 404
    # Избегаем дублирования
    existing = db.session.query(DialogTag).filter_by(
        account_id=account_id, peer_id=str(peer_id), tag_id=tag_id
    ).first()
    if existing:
        return jsonify({'success': True, 'id': existing.id})
    dt = DialogTag(
        account_id=account_id,
        peer_id=str(peer_id),
        tag_id=tag_id,
        created_by=current_user.username if current_user.is_authenticated else None,
    )
    db.session.add(dt)
    db.session.commit()
    return jsonify({'success': True, 'id': dt.id}), 201


@api_bp.route('/dialog-tags/<int:dt_id>', methods=['DELETE'])
@login_required
@admin_required
def remove_dialog_tag(dt_id):
    """Убрать тег с диалога."""
    dt = db.session.get(DialogTag, dt_id)
    if not dt:
        return jsonify({'success': False, 'error': 'Привязка не найдена'}), 404
    db.session.delete(dt)
    db.session.commit()
    return jsonify({'success': True})