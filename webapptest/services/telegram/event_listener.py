import asyncio
import json
from core.logger import log
from core.database import SessionLocal
from models.account import Account
from models.telegram_event import TelegramEvent
from models.incoming_message import IncomingMessage
from models.alert_rule import AlertRule
from models.campaign import Campaign
from models.notification import Notification

try:
    from telethon import events
    from telethon.errors import FloodWaitError, UserDeactivatedBanError
    HAS_TELETHON = True
except ImportError:
    HAS_TELETHON = False

_clients = {}
_running = False

_REDIS_STATUS_KEY = 'listener:status'


def _get_redis():
    """Return a Redis client or None if Redis is unavailable."""
    try:
        import redis as _redis
        from core.config import Config
        return _redis.from_url(Config.REDIS_URL, decode_responses=True, socket_connect_timeout=2)
    except Exception:
        return None


def _publish_status():
    """Write current listener status to Redis so Flask can read it."""
    r = _get_redis()
    if not r:
        return
    try:
        payload = json.dumps({'connected': len(_clients), 'running': _running})
        r.set(_REDIS_STATUS_KEY, payload, ex=300)  # expire after 5 minutes
    except Exception:
        pass


def get_listener_status() -> dict:
    db = SessionLocal()
    try:
        total = db.query(Account).filter(
            Account.status == 'active',
            Account.session_data.isnot(None)
        ).count()
    except Exception:
        total = 0
    finally:
        db.close()

    # Try to read live status from Redis (written by the Celery worker process)
    try:
        r = _get_redis()
        if r:
            raw = r.get(_REDIS_STATUS_KEY)
            if raw:
                data = json.loads(raw)
                return {
                    'connected': data.get('connected', 0),
                    'total_active': total,
                    'running': data.get('running', False),
                }
    except Exception:
        pass

    return {
        'connected': len(_clients),
        'total_active': total,
        'running': _running,
    }


async def _save_event(account_id: str, event_type: str, **kwargs):
    db = SessionLocal()
    try:
        ev = TelegramEvent(account_id=account_id, event_type=event_type, **kwargs)
        db.add(ev)
        db.commit()
    except Exception as e:
        db.rollback()
        log.error(f"_save_event error: {e}")
    finally:
        db.close()


async def _process_alert_rules(account_id: str, event_type: str, event_data: dict, client=None):
    db = SessionLocal()
    try:
        rules = db.query(AlertRule).filter(
            AlertRule.is_active == True,
            AlertRule.event_type.in_([event_type, 'any'])
        ).all()
        for rule in rules:
            try:
                # Check condition
                cond = rule.condition or {}
                if cond.get('account_id') and cond['account_id'] != account_id:
                    continue
                if cond.get('keyword') and event_data.get('text'):
                    if cond['keyword'].lower() not in event_data['text'].lower():
                        continue
                if cond.get('sender') and event_data.get('sender_username'):
                    sender = cond['sender'].lstrip('@')
                    if sender.lower() != event_data.get('sender_username', '').lower():
                        continue

                # Execute action
                if rule.action == 'notify_panel':
                    notif = Notification(
                        title=f'Alert: {rule.name}',
                        message=f'Event {event_type} on account {account_id}: {event_data.get("text_preview", "")}',
                        type='warning',
                        category='alert_rule',
                    )
                    db.add(notif)
                    db.commit()
                elif rule.action == 'auto_reply' and client:
                    params = rule.action_params or {}
                    reply_text = params.get('reply_text', '')
                    reply_buttons = params.get('reply_buttons', [])
                    chat_id = event_data.get('chat_id')
                    try:
                        delay = int(params.get('delay', 0))
                    except (ValueError, TypeError):
                        delay = 0
                    if reply_text and chat_id:
                        try:
                            if delay > 0:
                                await asyncio.sleep(delay)
                            # Build formatted button text if buttons are configured
                            # (user-accounts cannot send inline keyboards, so we format as text)
                            if reply_buttons:
                                btn_lines = []
                                for btn in reply_buttons:
                                    label = btn.get('label', '')
                                    url = btn.get('url', '')
                                    if url:
                                        btn_lines.append(f"▶ {label}: {url}")
                                    else:
                                        btn_lines.append(f"[ {label} ]")
                                full_text = reply_text + '\n\n' + '\n'.join(btn_lines)
                            else:
                                full_text = reply_text
                            await client.send_message(int(chat_id), full_text)
                        except Exception as e:
                            log.error(f"auto_reply error: {e}")
                elif rule.action == 'pause_campaigns':
                    db.query(Campaign).filter(
                        Campaign.status == 'running'
                    ).update({'status': 'paused'}, synchronize_session=False)
                    db.commit()
                elif rule.action == 'notify_telegram':
                    try:
                        from services.notification.telegram_bot import send_notification
                        params = rule.action_params or {}
                        msg = params.get('message', f'Alert: {rule.name}\nEvent: {event_type}\nAccount: {account_id}')
                        send_notification(msg)
                    except Exception as e:
                        log.error(f"notify_telegram error: {e}")
            except Exception as e:
                log.error(f"alert rule {rule.id} error: {e}")
    except Exception as e:
        log.error(f"_process_alert_rules error: {e}")
    finally:
        db.close()


def _make_new_message_handler(account_id: str, client):
    async def handler(event):
        db = SessionLocal()
        try:
            sender = await event.get_sender()
            chat = await event.get_chat()
            sender_tg_id = str(getattr(sender, 'id', '')) if sender else ''
            sender_username = getattr(sender, 'username', None) if sender else None
            sender_name = ' '.join(filter(None, [
                getattr(sender, 'first_name', None),
                getattr(sender, 'last_name', None)
            ])) if sender else None
            chat_id = str(getattr(chat, 'id', event.chat_id)) if chat else str(event.chat_id)
            chat_title = getattr(chat, 'title', None) or sender_name
            text = event.message.text or ''
            text_preview = text[:500] if text else None
            media_type = type(event.message.media).__name__ if event.message.media else None

            msg = IncomingMessage(
                account_id=account_id,
                tg_message_id=event.message.id,
                sender_tg_id=sender_tg_id,
                sender_username=sender_username,
                sender_name=sender_name,
                chat_id=chat_id,
                chat_title=chat_title,
                text=text,
                media_type=media_type,
                is_outgoing=event.message.out,
                reply_to_msg_id=event.message.reply_to_msg_id,
            )
            db.add(msg)

            ev = TelegramEvent(
                account_id=account_id,
                event_type='new_message',
                sender_tg_id=sender_tg_id,
                sender_username=sender_username,
                sender_name=sender_name,
                chat_id=chat_id,
                chat_title=chat_title,
                text_preview=text_preview,
                media_type=media_type,
            )
            db.add(ev)

            # Create panel notification for new incoming messages
            if not event.message.out:
                sender_label = sender_name or sender_username or sender_tg_id or 'Unknown'
                notif = Notification(
                    title=f'Новое сообщение ({account_id})',
                    message=f'От {sender_label}: {(text[:120] if text else "[медиа]")}',
                    type='info',
                    category='new_message',
                    related_url='/admin/inbox',
                )
                db.add(notif)

                # Send Telegram lead alert to subscribed users
                try:
                    from services.notification.telegram_bot import send_alert, ALERT_INCOMING_LEAD
                    acc = db.query(Account).filter(Account.id == account_id).first()
                    acc_label = (acc.phone if acc else account_id) or account_id
                    send_alert(
                        ALERT_INCOMING_LEAD,
                        f"📩 <b>Новый входящий лид</b>\n"
                        f"📱 Аккаунт: <code>{acc_label}</code>\n"
                        f"👤 От: {sender_label}\n"
                        f"💬 {(text[:200] if text else '[медиа]')}",
                        db=db,
                    )
                except Exception as _ae:
                    log.debug(f"Lead alert skipped: {_ae}")

            db.commit()

            event_data = {
                'text': text,
                'text_preview': text_preview,
                'chat_id': chat_id,
                'sender_username': sender_username,
            }
            await _process_alert_rules(account_id, 'new_message', event_data, client)
        except Exception as e:
            db.rollback()
            log.error(f"new_message handler error for {account_id}: {e}")
        finally:
            db.close()
    return handler


def _make_message_read_handler(account_id: str):
    async def handler(event):
        await _save_event(account_id, 'message_read')
    return handler


def _make_user_update_handler(account_id: str):
    async def handler(event):
        await _save_event(account_id, 'user_online')
    return handler


def _make_chat_action_handler(account_id: str):
    async def handler(event):
        await _save_event(account_id, 'chat_action')
    return handler


async def _connect_account(account_id: str) -> bool:
    if not HAS_TELETHON:
        return False
    try:
        from services.telegram.actions import get_telegram_client
        client = await get_telegram_client(account_id)
        _clients[account_id] = client

        client.add_event_handler(_make_new_message_handler(account_id, client), events.NewMessage())
        client.add_event_handler(_make_message_read_handler(account_id), events.MessageRead())
        client.add_event_handler(_make_user_update_handler(account_id), events.UserUpdate())
        client.add_event_handler(_make_chat_action_handler(account_id), events.ChatAction())
        _publish_status()
        return True
    except Exception as e:
        log.error(f"_connect_account {account_id} error: {e}")
        return False


async def start_listener():
    global _running
    _running = True
    _publish_status()
    log.info("Event listener starting...")

    db = SessionLocal()
    try:
        accounts = db.query(Account).filter(
            Account.status == 'active',
            Account.session_data.isnot(None)
        ).all()
        account_ids = [a.id for a in accounts]
    finally:
        db.close()

    for acc_id in account_ids:
        await _connect_account(acc_id)

    log.info(f"Event listener connected to {len(_clients)} accounts")
    _publish_status()

    reconnect_counter = 0
    while _running:
        await asyncio.sleep(5)
        reconnect_counter += 1

        if reconnect_counter >= 12:  # ~60 seconds
            reconnect_counter = 0
            db = SessionLocal()
            try:
                current_ids = set(
                    row[0] for row in db.query(Account.id).filter(
                        Account.status == 'active',
                        Account.session_data.isnot(None)
                    ).all()
                )
            finally:
                db.close()

            disconnected = set(_clients.keys()) - current_ids
            for acc_id in disconnected:
                try:
                    await _clients[acc_id].disconnect()
                except Exception:
                    pass
                del _clients[acc_id]

            for acc_id in current_ids:
                if acc_id not in _clients:
                    await _connect_account(acc_id)
                else:
                    try:
                        if not _clients[acc_id].is_connected():
                            await _connect_account(acc_id)
                    except Exception:
                        await _connect_account(acc_id)

            _publish_status()


async def stop_listener():
    global _running
    _running = False
    for acc_id, client in list(_clients.items()):
        try:
            await client.disconnect()
        except Exception:
            pass
    _clients.clear()
    _publish_status()
    log.info("Event listener stopped")
