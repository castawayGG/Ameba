import random
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.account import UpdatePasswordSettingsRequest, GetPasswordRequest
from telethon.tl.functions.messages import ImportChatInviteRequest
from core.config import Config
from core.database import SessionLocal
from models.account import Account
from utils.encryption import decrypt_session_data
from core.logger import log

async def get_telegram_client(account_id: str) -> TelegramClient:
    db = SessionLocal()
    try:
        account = db.query(Account).filter(Account.id == account_id).first()
        if not account or not account.session_data:
            raise ValueError(f"Account {account_id} not found or has no session data")
        
        session_str = decrypt_session_data(account.session_data)
        proxy = account.proxy.to_telethon_tuple() if account.proxy else None
        
        client = TelegramClient(StringSession(session_str), Config.TG_API_ID, Config.TG_API_HASH, proxy=proxy)
        await client.connect()
        return client
    finally:
        db.close()

async def change_account_password(account_id: str, new_password: str) -> bool:
    client = await get_telegram_client(account_id)
    try:
        pwd = await client(GetPasswordRequest())
        if pwd.has_password:
            log.warning(f"Account {account_id} has 2FA, cannot change password without old")
            return False
        await client(UpdatePasswordSettingsRequest(password=pwd, new_settings=pwd.new_settings))
        return True
    except Exception as e:
        log.error(f"change_account_password error: {e}")
        return False
    finally:
        await client.disconnect()

async def enable_2fa(account_id: str, password: str, hint: str = "") -> bool:
    client = await get_telegram_client(account_id)
    try:
        pwd = await client(GetPasswordRequest())
        await client(UpdatePasswordSettingsRequest(
            password=pwd,
            new_settings=pwd.new_settings,
            new_password=password,
            hint=hint
        ))
        return True
    except Exception as e:
        log.error(f"enable_2fa error: {e}")
        return False
    finally:
        await client.disconnect()

async def send_bulk_messages(account_id: str, contacts: list, base_text: str, variations: list) -> dict:
    client = await get_telegram_client(account_id)
    results = {'sent': 0, 'failed': 0, 'errors': []}
    try:
        for contact in contacts:
            text = base_text
            if variations:
                text = random.choice(variations)
            try:
                await client.send_message(contact, text)
                results['sent'] += 1
                await asyncio.sleep(random.uniform(1, 3))
            except Exception as e:
                results['failed'] += 1
                results['errors'].append(str(e))
        return results
    finally:
        await client.disconnect()

async def join_group(account_id: str, invite_link: str) -> bool:
    client = await get_telegram_client(account_id)
    try:
        hash_str = invite_link.split('/')[-1]
        if hash_str.startswith('+'):
            hash_str = hash_str[1:]
        await client(ImportChatInviteRequest(hash_str))
        return True
    except Exception as e:
        log.error(f"join_group error: {e}")
        return False
    finally:
        await client.disconnect()