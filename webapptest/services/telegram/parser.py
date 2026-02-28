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
                    filter=ChannelParticipantsSearch(''),
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
