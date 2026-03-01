import datetime
from core.database import SessionLocal
from models.parse_task import ParseTask
from core.logger import log


async def parse_group_members(task_id, account_id, group_link, filters=None):
    """Parse group members using Telethon GetParticipantsRequest."""
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    from telethon.tl.functions.channels import GetParticipantsRequest
    from telethon.tl.types import ChannelParticipantsSearch
    from core.config import Config
    from models.account import Account
    from utils.encryption import decrypt_session_data

    db = SessionLocal()
    try:
        task = db.query(ParseTask).filter_by(id=task_id).first()
        if not task:
            return
        task.status = 'running'
        task.started_at = datetime.datetime.utcnow()
        db.commit()

        account = db.query(Account).filter_by(id=account_id).first()
        if not account or not account.session_data:
            task.status = 'failed'
            task.error_message = 'Account not found or no session'
            db.commit()
            return

        session_string = decrypt_session_data(account.session_data)
        client = TelegramClient(StringSession(session_string), Config.TG_API_ID, Config.TG_API_HASH)
        await client.connect()

        members = []
        offset = 0
        limit = 200
        filters = filters or {}

        try:
            entity = await client.get_entity(group_link)
            while True:
                participants = await client(GetParticipantsRequest(
                    channel=entity,
                    filter=ChannelParticipantsSearch(''),  # empty string returns all participants
                    offset=offset,
                    limit=limit,
                    hash=0,
                ))
                if not participants.users:
                    break
                for user in participants.users:
                    if user.bot:
                        continue
                    if filters.get('with_photo') and not user.photo:
                        continue
                    member_data = {
                        'user_id': user.id,
                        'username': user.username,
                        'first_name': user.first_name or '',
                        'last_name': user.last_name or '',
                        'phone': getattr(user, 'phone', None),
                        'is_bot': user.bot,
                        'premium': getattr(user, 'premium', False),
                    }
                    members.append(member_data)
                offset += len(participants.users)
                if len(participants.users) < limit:
                    break
        finally:
            await client.disconnect()

        task.status = 'completed'
        task.total_parsed = len(members)
        task.result_data = members
        task.completed_at = datetime.datetime.utcnow()
        db.commit()
        log.info(f"ParseTask {task_id}: parsed {len(members)} members from {group_link}")

    except Exception as e:
        log.error(f"parse_group_members error for task {task_id}: {e}")
        try:
            task.status = 'failed'
            task.error_message = str(e)
            task.completed_at = datetime.datetime.utcnow()
            db.commit()
        except Exception:
            pass
    finally:
        db.close()


async def parse_channel_commenters(task_id, account_id, channel_link, filters=None):
    """
    Парсит комментаторов канала (из Discussion group канала).
    
    :param task_id: ID задачи парсинга
    :param account_id: ID аккаунта
    :param channel_link: Ссылка на канал
    :param filters: Фильтры
    """
    import datetime
    from core.database import SessionLocal
    from core.config import Config
    from models.account import Account
    from utils.encryption import decrypt_session_data
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    from telethon.tl.functions.messages import GetRepliesRequest
    
    db = SessionLocal()
    try:
        task = db.query(ParseTask).filter_by(id=task_id).first()
        if not task:
            return
        task.status = 'running'
        task.started_at = datetime.datetime.utcnow()
        db.commit()
        
        account = db.query(Account).filter_by(id=account_id).first()
        if not account or not account.session_data:
            task.status = 'failed'
            task.error_message = 'Account not found or no session'
            db.commit()
            return
        
        session_string = decrypt_session_data(account.session_data)
        client = TelegramClient(StringSession(session_string), Config.TG_API_ID, Config.TG_API_HASH)
        await client.connect()
        
        commenters = {}
        filters = filters or {}
        
        try:
            entity = await client.get_entity(channel_link)
            messages = await client.get_messages(entity, limit=50)
            
            for msg in messages:
                try:
                    replies = await client(GetRepliesRequest(
                        peer=entity,
                        msg_id=msg.id,
                        offset_id=0,
                        offset_date=None,
                        add_offset=0,
                        limit=100,
                        max_id=0,
                        min_id=0,
                        hash=0,
                    ))
                    for reply in replies.messages:
                        sender = reply.sender
                        if sender and not getattr(sender, 'bot', False):
                            uid = sender.id
                            if uid not in commenters:
                                commenters[uid] = {
                                    'user_id': uid,
                                    'username': getattr(sender, 'username', None),
                                    'first_name': getattr(sender, 'first_name', '') or '',
                                    'last_name': getattr(sender, 'last_name', '') or '',
                                    'comment_count': 0,
                                }
                            commenters[uid]['comment_count'] += 1
                except Exception:
                    pass
        finally:
            await client.disconnect()
        
        result = sorted(commenters.values(), key=lambda x: x['comment_count'], reverse=True)
        task.status = 'completed'
        task.total_parsed = len(result)
        task.result_data = result
        task.completed_at = datetime.datetime.utcnow()
        db.commit()
        log.info(f"ParseTask {task_id}: parsed {len(result)} commenters from {channel_link}")
    except Exception as e:
        log.error(f"parse_channel_commenters error: {e}")
        try:
            task.status = 'failed'
            task.error_message = str(e)
            task.completed_at = datetime.datetime.utcnow()
            db.commit()
        except Exception:
            pass
    finally:
        db.close()


async def parse_geo_users(task_id, account_id, latitude: float, longitude: float, radius_km: int = 5, filters=None):
    """
    Гео-парсер: ищет пользователей рядом по координатам.
    
    :param task_id: ID задачи
    :param account_id: ID аккаунта
    :param latitude: Широта
    :param longitude: Долгота
    :param radius_km: Радиус поиска в км
    """
    import datetime
    from core.database import SessionLocal
    from core.config import Config
    from models.account import Account
    from utils.encryption import decrypt_session_data
    from telethon import TelegramClient
    from telethon.sessions import StringSession
    from telethon.tl.functions.contacts import GetLocatedRequest
    from telethon.tl.types import InputGeoPoint, GeoPointEmpty
    
    db = SessionLocal()
    try:
        task = db.query(ParseTask).filter_by(id=task_id).first()
        if not task:
            return
        task.status = 'running'
        task.started_at = datetime.datetime.utcnow()
        db.commit()
        
        account = db.query(Account).filter_by(id=account_id).first()
        if not account or not account.session_data:
            task.status = 'failed'
            task.error_message = 'Account not found or no session'
            db.commit()
            return
        
        session_string = decrypt_session_data(account.session_data)
        client = TelegramClient(StringSession(session_string), Config.TG_API_ID, Config.TG_API_HASH)
        await client.connect()
        
        users = []
        try:
            result = await client(GetLocatedRequest(
                geo_point=InputGeoPoint(lat=latitude, long=longitude),
                self_expires=None,
                background=True,
            ))
            for update in result.updates:
                if hasattr(update, 'peers'):
                    for peer_located in update.peers:
                        peer = getattr(peer_located, 'peer', None)
                        if peer and hasattr(peer, 'user_id'):
                            try:
                                user = await client.get_entity(peer.user_id)
                                dist = getattr(peer_located, 'distance', None)
                                if dist and radius_km and dist > radius_km * 1000:
                                    continue
                                users.append({
                                    'user_id': user.id,
                                    'username': getattr(user, 'username', None),
                                    'first_name': getattr(user, 'first_name', '') or '',
                                    'last_name': getattr(user, 'last_name', '') or '',
                                    'distance_m': dist,
                                })
                            except Exception:
                                pass
        finally:
            await client.disconnect()
        
        task.status = 'completed'
        task.total_parsed = len(users)
        task.result_data = users
        task.completed_at = datetime.datetime.utcnow()
        db.commit()
    except Exception as e:
        log.error(f"parse_geo_users error: {e}")
        try:
            task.status = 'failed'
            task.error_message = str(e)
            task.completed_at = datetime.datetime.utcnow()
            db.commit()
        except Exception:
            pass
    finally:
        db.close()


def apply_lookalike_filter(base_users: list, target_users: list) -> list:
    """
    Алгоритм пересечения (lookalike): находит «горячих лидов»
    как пересечение base_users и target_users по user_id.
    
    :param base_users: Базовая аудитория (список словарей с полем user_id)
    :param target_users: Целевая аудитория
    :return: Список пользователей из base, которые есть в target
    """
    target_ids = {u['user_id'] for u in target_users if u.get('user_id')}
    return [u for u in base_users if u.get('user_id') in target_ids]


def scrub_user_base(users: list, min_username: bool = False, no_bots: bool = True, has_photo: bool = False) -> list:
    """
    Очистка базы от некачественных пользователей.
    
    :param users: Список пользователей
    :param min_username: Оставить только с username
    :param no_bots: Удалить ботов
    :param has_photo: Оставить только с фото
    :return: Очищенный список
    """
    result = []
    for u in users:
        if no_bots and u.get('is_bot'):
            continue
        if min_username and not u.get('username'):
            continue
        if has_photo and not u.get('has_photo'):
            continue
        result.append(u)
    return result
