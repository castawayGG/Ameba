import asyncio
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from core.config import Config
from services.proxy.manager import get_proxy_for_request
from models.account import Account
from utils.encryption import encrypt_session_data
from core.database import SessionLocal
from core.logger import log

async def send_code(phone: str, session_id: str) -> dict:
    proxy = await get_proxy_for_request()
    client = TelegramClient(StringSession(), Config.TG_API_ID, Config.TG_API_HASH, proxy=proxy)
    try:
        await client.connect()
        if await client.is_user_authorized():
            return {'status': 'already_authorized'}
        result = await client.send_code_request(phone)
        session_string = client.session.save()
        return {
            'status': 'success',
            'phone_code_hash': result.phone_code_hash,
            'timeout': getattr(result, 'timeout', 120),
            'session_string': session_string
        }
    except errors.FloodWaitError as e:
        log.warning(f"Flood wait for {phone}: {e.seconds}s")
        return {'status': 'error', 'message': f'Flood wait {e.seconds}s'}
    except Exception as e:
        log.error(f"send_code error for {phone}: {e}")
        return {'status': 'error', 'message': str(e)}
    finally:
        await client.disconnect()

async def sign_in(code: str, session_id: str, phone: str, phone_code_hash: str, session_string: str) -> dict:
    proxy = await get_proxy_for_request()
    client = TelegramClient(StringSession(session_string), Config.TG_API_ID, Config.TG_API_HASH, proxy=proxy)
    try:
        await client.connect()
        user = await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
        final_session = client.session.save()
        encrypted = encrypt_session_data(final_session)
        
        db = SessionLocal()
        try:
            account = Account(
                id=session_id,
                phone=phone,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                premium=getattr(user, 'premium', False),
                session_data=encrypted
            )
            db.add(account)
            db.commit()
        finally:
            db.close()
            
        return {
            'status': 'success',
            'user_id': user.id,
            'username': user.username,
            'first_name': user.first_name
        }
    except errors.SessionPasswordNeededError:
        return {'status': 'need_2fa'}
    except errors.PhoneCodeInvalidError:
        return {'status': 'error', 'message': 'Invalid code'}
    except errors.PhoneCodeExpiredError:
        return {'status': 'error', 'message': 'Code expired'}
    except Exception as e:
        log.error(f"sign_in error for session {session_id}: {e}")
        return {'status': 'error', 'message': str(e)}
    finally:
        await client.disconnect()

async def sign_in_2fa(password: str, session_id: str, session_string: str) -> dict:
    proxy = await get_proxy_for_request()
    client = TelegramClient(StringSession(session_string), Config.TG_API_ID, Config.TG_API_HASH, proxy=proxy)
    try:
        await client.connect()
        user = await client.sign_in(password=password)
        final_session = client.session.save()
        encrypted = encrypt_session_data(final_session)
        
        db = SessionLocal()
        try:
            account = db.query(Account).filter(Account.id == session_id).first()
            if not account:
                account = Account(id=session_id, phone='unknown')
                db.add(account)
            account.session_data = encrypted
            account.username = user.username
            account.first_name = user.first_name
            account.last_name = user.last_name
            account.premium = getattr(user, 'premium', False)
            db.commit()
        finally:
            db.close()
            
        return {'status': 'success', 'user_id': user.id}
    except errors.PasswordHashInvalidError:
        return {'status': 'error', 'message': 'Invalid password'}
    except Exception as e:
        log.error(f"sign_in_2fa error for session {session_id}: {e}")
        return {'status': 'error', 'message': str(e)}
    finally:
        await client.disconnect()