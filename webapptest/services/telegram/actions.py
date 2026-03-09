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

        # Используем ротацию учётных данных API
        try:
            from services.telegram.credentials import get_active_credential
            cred = get_active_credential()
            api_id = cred['api_id']
            api_hash = cred['api_hash']
        except Exception:
            api_id = Config.TG_API_ID
            api_hash = Config.TG_API_HASH

        # Берём device fingerprint из AccountFingerprint; создаём запись, если её нет
        device_params = {}
        try:
            from models.account_fingerprint import AccountFingerprint
            fp = db.query(AccountFingerprint).filter_by(account_id=account_id).first()
            if not fp:
                fp = AccountFingerprint(account_id=account_id)
                db.add(fp)
                db.commit()
            if fp.device_model:
                device_params['device_model'] = fp.device_model
            if fp.app_version:
                device_params['app_version'] = fp.app_version
            # AccountFingerprint stores OS version as 'os_version'; TelegramClient param is 'system_version'
            if fp.os_version:
                device_params['system_version'] = fp.os_version
        except Exception as e:
            log.warning(f"get_telegram_client: could not load fingerprint for {account_id}: {e}")

        client = TelegramClient(StringSession(session_str), api_id, api_hash, proxy=proxy, **device_params)
        try:
            await client.connect()
            return client
        except Exception as e:
            if proxy is None:
                raise
            log.warning(f"get_telegram_client: proxy connection failed for {account_id} ({e}), retrying without proxy")
            try:
                await client.disconnect()
            except Exception as disc_err:
                log.debug(f"get_telegram_client: error disconnecting proxy client for {account_id}: {disc_err}")
            client = TelegramClient(StringSession(session_str), api_id, api_hash, **device_params)
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
        await client.edit_2fa(new_password=password, hint=hint)
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
async def update_profile(account_id: str, first_name: 'Optional[str]' = None, last_name: 'Optional[str]' = None, about: 'Optional[str]' = None) -> bool:
    """Update Telegram profile name and bio"""
    from telethon.tl.functions.account import UpdateProfileRequest
    client = await get_telegram_client(account_id)
    try:
        kwargs = {}
        if first_name is not None:
            kwargs['first_name'] = first_name
        if last_name is not None:
            kwargs['last_name'] = last_name
        if about is not None:
            kwargs['about'] = about
        await client(UpdateProfileRequest(**kwargs))
        return True
    except Exception as e:
        log.error(f"update_profile error: {e}")
        return False
    finally:
        await client.disconnect()

async def update_username(account_id: str, username: str) -> bool:
    """Update Telegram username"""
    from telethon.tl.functions.account import UpdateUsernameRequest
    client = await get_telegram_client(account_id)
    try:
        await client(UpdateUsernameRequest(username=username))
        return True
    except Exception as e:
        log.error(f"update_username error: {e}")
        return False
    finally:
        await client.disconnect()

async def update_avatar(account_id: str, photo_bytes: bytes) -> bool:
    """Upload new profile photo"""
    import io as _io
    from telethon.tl.functions.photos import UploadProfilePhotoRequest
    client = await get_telegram_client(account_id)
    try:
        file = await client.upload_file(_io.BytesIO(photo_bytes), file_name='avatar.jpg')
        await client(UploadProfilePhotoRequest(file=file))
        return True
    except Exception as e:
        log.error(f"update_avatar error: {e}")
        return False
    finally:
        await client.disconnect()

async def delete_avatar(account_id: str) -> bool:
    """Delete profile photo"""
    from telethon.tl.functions.photos import DeletePhotosRequest, GetUserPhotosRequest
    client = await get_telegram_client(account_id)
    try:
        photos = await client(GetUserPhotosRequest(user_id='me', offset=0, max_id=0, limit=1))
        if photos.photos:
            await client(DeletePhotosRequest(id=photos.photos))
        return True
    except Exception as e:
        log.error(f"delete_avatar error: {e}")
        return False
    finally:
        await client.disconnect()


async def get_dialogs(account_id: str, limit: int = 50) -> list:
    """Получить список диалогов аккаунта."""
    client = await get_telegram_client(account_id)
    try:
        dialogs = await client.get_dialogs(limit=limit)
        result = []
        for d in dialogs:
            result.append({
                'id': d.id,
                'name': d.name,
                'username': getattr(d.entity, 'username', None),
                'type': 'channel' if d.is_channel else ('group' if d.is_group else 'private'),
                'unread_count': d.unread_count,
                'last_message': d.message.text[:100] if d.message and d.message.text else '',
                'last_message_date': d.message.date.isoformat() if d.message and d.message.date else None,
                'photo': bool(getattr(d.entity, 'photo', None)),
            })
        return result
    finally:
        await client.disconnect()


async def get_chat_messages(account_id: str, chat_id: int, limit: int = 50, offset_id: int = 0) -> list:
    """Получить историю сообщений конкретного чата."""
    client = await get_telegram_client(account_id)
    try:
        entity = await client.get_entity(chat_id)
        messages = await client.get_messages(entity, limit=limit, offset_id=offset_id)
        result = []
        for m in messages:
            result.append({
                'id': m.id,
                'text': m.text or '',
                'date': m.date.isoformat() if m.date else None,
                'out': m.out,
                'sender_id': m.sender_id,
                'sender_name': getattr(m.sender, 'first_name', '') if m.sender else '',
                'media_type': type(m.media).__name__ if m.media else None,
                'reply_to': m.reply_to_msg_id if m.reply_to else None,
            })
        return result
    finally:
        await client.disconnect()


async def send_message_to_chat(account_id: str, chat_id: int, text: str, reply_to: int = None) -> dict:
    """Отправить сообщение в конкретный чат."""
    client = await get_telegram_client(account_id)
    try:
        entity = None
        try:
            entity = await client.get_entity(int(chat_id))
        except (ValueError, TypeError):
            entity = int(chat_id)
        except Exception as _ge:
            log.debug(f"get_entity fallback for chat {chat_id}: {_ge}")
            # Refresh dialog cache so Telethon learns the access_hash for user entities
            try:
                await client.get_dialogs()
                entity = await client.get_entity(int(chat_id))
            except Exception as _de:
                log.debug(f"get_dialogs fallback failed for chat {chat_id}: {_de}")
                entity = int(chat_id)
        msg = await client.send_message(entity, text, reply_to=reply_to)
        return {'success': True, 'message_id': msg.id}
    except Exception as e:
        log.error(f"send_message_to_chat error account={account_id} chat={chat_id}: {e}")
        return {'success': False, 'error': str(e)}
    finally:
        await client.disconnect()


async def mark_chat_read(account_id: str, chat_id: int) -> bool:
    """Отметить чат как прочитанный."""
    client = await get_telegram_client(account_id)
    try:
        entity = await client.get_entity(chat_id)
        await client.send_read_acknowledge(entity)
        return True
    except Exception as e:
        log.error(f"mark_chat_read error: {e}")
        return False
    finally:
        await client.disconnect()


async def get_entity_info(account_id: str, username_or_id: str) -> dict:
    """Получить информацию о пользователе/группе по username или ID."""
    client = await get_telegram_client(account_id)
    try:
        entity = await client.get_entity(username_or_id)
        return {
            'id': entity.id,
            'username': getattr(entity, 'username', None),
            'first_name': getattr(entity, 'first_name', None),
            'last_name': getattr(entity, 'last_name', None),
            'phone': getattr(entity, 'phone', None),
            'about': getattr(entity, 'about', None) if hasattr(entity, 'about') else None,
            'participants_count': getattr(entity, 'participants_count', None),
            'is_bot': getattr(entity, 'bot', False),
            'type': 'channel' if hasattr(entity, 'broadcast') else ('group' if hasattr(entity, 'megagroup') else 'user'),
        }
    except Exception as e:
        return {'error': str(e)}
    finally:
        await client.disconnect()


async def leave_chat(account_id: str, chat_id: int) -> bool:
    """Покинуть группу/канал."""
    client = await get_telegram_client(account_id)
    try:
        entity = await client.get_entity(chat_id)
        await client.delete_dialog(entity)
        return True
    except Exception as e:
        log.error(f"leave_chat error: {e}")
        return False
    finally:
        await client.disconnect()


async def search_messages(account_id: str, chat_id: int = None, query: str = '', limit: int = 30) -> list:
    """Поиск по сообщениям."""
    client = await get_telegram_client(account_id)
    try:
        entity = await client.get_entity(chat_id) if chat_id else None
        messages = await client.get_messages(entity, limit=limit, search=query)
        return [{
            'id': m.id,
            'text': m.text[:200] if m.text else '',
            'date': m.date.isoformat() if m.date else None,
            'chat_id': m.chat_id,
            'sender_id': m.sender_id,
        } for m in messages]
    finally:
        await client.disconnect()


async def get_account_groups(account_id: str) -> list:
    """Получить список групп/каналов аккаунта."""
    client = await get_telegram_client(account_id)
    try:
        dialogs = await client.get_dialogs()
        groups = []
        for d in dialogs:
            if d.is_group or d.is_channel:
                groups.append({
                    'id': d.id,
                    'name': d.name,
                    'type': 'channel' if d.is_channel else 'group',
                    'username': getattr(d.entity, 'username', None),
                    'participants_count': getattr(d.entity, 'participants_count', None),
                    'unread_count': d.unread_count,
                })
        return groups
    finally:
        await client.disconnect()



async def simulate_typing(account_id: str, chat_id: int, duration_seconds: int = 5) -> bool:
    """
    Имитирует набор текста ('typing...') в чате указанное количество секунд.
    
    :param account_id: ID аккаунта
    :param chat_id: ID чата
    :param duration_seconds: Длительность имитации набора
    :return: True при успехе
    """
    import asyncio
    from telethon.tl.functions.messages import SetTypingRequest
    from telethon.tl.types import SendMessageTypingAction, SendMessageCancelAction
    
    client = await get_telegram_client(account_id)
    try:
        entity = await client.get_entity(chat_id)
        await client(SetTypingRequest(peer=entity, action=SendMessageTypingAction()))
        await asyncio.sleep(max(1, duration_seconds))
        await client(SetTypingRequest(peer=entity, action=SendMessageCancelAction()))
        return True
    except Exception as e:
        log.error(f"simulate_typing error: {e}")
        return False
    finally:
        await client.disconnect()


async def react_to_message(account_id: str, chat_id: int, message_id: int, reaction: str = '👍') -> bool:
    """
    Ставит реакцию на сообщение/пост.
    
    :param account_id: ID аккаунта
    :param chat_id: ID чата/канала
    :param message_id: ID сообщения
    :param reaction: Эмодзи реакции
    :return: True при успехе
    """
    from telethon.tl.functions.messages import SendReactionRequest
    from telethon.tl.types import ReactionEmoji
    
    client = await get_telegram_client(account_id)
    try:
        entity = await client.get_entity(chat_id)
        await client(SendReactionRequest(
            peer=entity,
            msg_id=message_id,
            reaction=[ReactionEmoji(emoticon=reaction)],
        ))
        return True
    except Exception as e:
        log.error(f"react_to_message error: {e}")
        return False
    finally:
        await client.disconnect()


async def send_voice_message(account_id: str, chat_id: int, audio_bytes: bytes, duration: int = 5) -> bool:
    """
    Отправляет голосовое сообщение в чат.
    
    :param account_id: ID аккаунта
    :param chat_id: ID чата
    :param audio_bytes: Байты аудио-файла (OGG/OPUS)
    :param duration: Длительность в секундах
    :return: True при успехе
    """
    import io
    from telethon.tl.types import DocumentAttributeAudio
    
    client = await get_telegram_client(account_id)
    try:
        entity = await client.get_entity(chat_id)
        await client.send_file(
            entity,
            io.BytesIO(audio_bytes),
            voice_note=True,
            attributes=[DocumentAttributeAudio(duration=duration, voice=True)],
        )
        return True
    except Exception as e:
        log.error(f"send_voice_message error: {e}")
        return False
    finally:
        await client.disconnect()


async def send_video_note(account_id: str, chat_id: int, video_bytes: bytes, duration: int = 10) -> bool:
    """
    Отправляет кружок (video note) в чат.
    
    :param account_id: ID аккаунта
    :param chat_id: ID чата
    :param video_bytes: Байты видео (MP4, квадратный)
    :param duration: Длительность в секундах
    :return: True при успехе
    """
    import io
    from telethon.tl.types import DocumentAttributeVideo
    
    client = await get_telegram_client(account_id)
    try:
        entity = await client.get_entity(chat_id)
        await client.send_file(
            entity,
            io.BytesIO(video_bytes),
            video_note=True,
            attributes=[DocumentAttributeVideo(duration=duration, w=240, h=240, round_message=True)],
        )
        return True
    except Exception as e:
        log.error(f"send_video_note error: {e}")
        return False
    finally:
        await client.disconnect()


async def invite_users_to_group(account_id: str, group_id: int, user_ids: list) -> dict:
    """
    Инвайтит пользователей в группу/канал.
    
    :param account_id: ID аккаунта-инвайтера
    :param group_id: ID группы
    :param user_ids: Список ID пользователей
    :return: {'invited': int, 'failed': int, 'errors': list}
    """
    import asyncio
    from telethon.tl.functions.channels import InviteToChannelRequest
    
    client = await get_telegram_client(account_id)
    results = {'invited': 0, 'failed': 0, 'errors': []}
    try:
        entity = await client.get_entity(group_id)
        for uid in user_ids:
            try:
                user_entity = await client.get_entity(uid)
                await client(InviteToChannelRequest(channel=entity, users=[user_entity]))
                results['invited'] += 1
                await asyncio.sleep(random.uniform(3, 8))
            except Exception as e:
                results['failed'] += 1
                results['errors'].append(str(e))
    except Exception as e:
        results['errors'].append(f"Group error: {e}")
    finally:
        await client.disconnect()
    return results


async def reset_all_sessions(account_id: str) -> bool:
    """
    Сбрасывает все авторизованные сессии аккаунта, кроме текущей.
    
    :param account_id: ID аккаунта
    :return: True при успехе
    """
    from telethon.tl.functions.auth import ResetAuthorizationsRequest
    
    client = await get_telegram_client(account_id)
    try:
        await client(ResetAuthorizationsRequest())
        return True
    except Exception as e:
        log.error(f"reset_all_sessions error: {e}")
        return False
    finally:
        await client.disconnect()


async def dump_all_chats(account_id: str, limit_per_chat: int = 100) -> dict:
    """
    Дампит все чаты аккаунта в текстовый архив.
    
    :param account_id: ID аккаунта
    :param limit_per_chat: Лимит сообщений на чат
    :return: {'archive': bytes, 'chat_count': int} или {'error': str}
    """
    import io
    import zipfile
    import asyncio
    
    client = await get_telegram_client(account_id)
    try:
        dialogs = await client.get_dialogs(limit=50)
        zip_buf = io.BytesIO()
        chat_count = 0
        
        with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for dialog in dialogs:
                if not dialog.is_user and not dialog.is_group and not dialog.is_channel:
                    continue
                try:
                    messages = await client.get_messages(dialog.entity, limit=limit_per_chat)
                    lines = [f"=== {dialog.name} (ID: {dialog.id}) ===\n"]
                    for msg in reversed(messages):
                        sender = getattr(msg.sender, 'first_name', '') or ''
                        text = msg.text or '[media]'
                        date_str = msg.date.strftime('%Y-%m-%d %H:%M') if msg.date else ''
                        lines.append(f"[{date_str}] {sender}: {text}\n")
                    
                    safe_name = ''.join(c for c in dialog.name if c.isalnum() or c in ' _-')[:50]
                    filename = f"{safe_name}_{dialog.id}.txt"
                    zf.writestr(filename, ''.join(lines))
                    chat_count += 1
                    await asyncio.sleep(0.5)
                except Exception as e:
                    log.warning(f"dump_all_chats: skip chat {dialog.id}: {e}")
        
        zip_buf.seek(0)
        return {'archive': zip_buf.read(), 'chat_count': chat_count}
    except Exception as e:
        log.error(f"dump_all_chats error: {e}")
        return {'error': str(e)}
    finally:
        await client.disconnect()


async def send_message(account_id: str, recipient: str, text: str) -> dict:
    """Send a single message to a recipient by username or ID."""
    client = await get_telegram_client(account_id)
    try:
        entity = await client.get_entity(recipient)
        msg = await client.send_message(entity, text)
        return {'success': True, 'message_id': msg.id}
    except Exception as e:
        log.error(f"send_message error: {e}")
        return {'success': False, 'error': str(e)}
    finally:
        await client.disconnect()


async def get_active_sessions(account_id: str) -> list:
    """
    Возвращает список активных сессий (авторизаций) аккаунта Telegram.

    :param account_id: ID аккаунта
    :return: Список словарей с информацией о каждой сессии
    """
    from telethon.tl.functions.account import GetAuthorizationsRequest

    client = await get_telegram_client(account_id)
    try:
        result = await client(GetAuthorizationsRequest())
        sessions = []
        for auth in result.authorizations:
            sessions.append({
                'hash': auth.hash,
                'device_model': auth.device_model,
                'platform': auth.platform,
                'system_version': auth.system_version,
                'api_id': auth.api_id,
                'app_name': auth.app_name,
                'app_version': auth.app_version,
                'date_created': auth.date_created.isoformat() if auth.date_created else None,
                'date_active': auth.date_active.isoformat() if auth.date_active else None,
                'ip': auth.ip,
                'country': auth.country,
                'region': auth.region,
                'current': auth.current,
            })
        return sessions
    except Exception as e:
        log.error(f"get_active_sessions error: {e}")
        return []
    finally:
        await client.disconnect()


async def check_spambot(account_id: str) -> dict:
    """
    Проверяет статус аккаунта через @spambot.

    Отправляет /start, ждёт ответ, парсит результат и удаляет диалог.

    :param account_id: ID аккаунта
    :return: {'status': 'clean'|'limited'|'unknown'|'error', 'text': str}
    """
    client = await get_telegram_client(account_id)
    try:
        spambot = await client.get_entity('spambot')
        await client.send_message(spambot, '/start')
        await asyncio.sleep(2)
        messages = await client.get_messages(spambot, limit=5)
        status = 'unknown'
        last_text = ''
        for msg in messages:
            if not msg.out and msg.text:
                last_text = msg.text
                text_lower = msg.text.lower()
                if any(word in text_lower for word in ['no limits', 'good news', 'свободны', 'нет ограничений', 'free']):
                    status = 'clean'
                elif any(word in text_lower for word in ['limit', 'ограничен', 'spam', 'спам', 'restricted']):
                    status = 'limited'
                break
        # Удаляем диалог с @spambot
        try:
            await client.delete_dialog(spambot)
        except Exception:
            pass
        return {'status': status, 'text': last_text[:500]}
    except Exception as e:
        log.error(f"check_spambot error: {e}")
        return {'status': 'error', 'error': str(e)}
    finally:
        await client.disconnect()


async def parse_recent_contacts(account_id: str, limit: int = 100) -> list:
    """
    Парсит пользователей из последних диалогов аккаунта.

    Возвращает user_id и username людей, с которыми аккаунт переписывался.

    :param account_id: ID аккаунта
    :param limit: Максимальное число диалогов для проверки
    :return: Список словарей {'user_id', 'username', 'first_name', 'last_name', 'phone'}
    """
    client = await get_telegram_client(account_id)
    try:
        dialogs = await client.get_dialogs(limit=limit)
        contacts = []
        seen: set = set()
        for d in dialogs:
            if d.is_user and not getattr(d.entity, 'bot', False):
                user_id = d.entity.id
                if user_id in seen:
                    continue
                seen.add(user_id)
                contacts.append({
                    'user_id': user_id,
                    'username': getattr(d.entity, 'username', None),
                    'first_name': getattr(d.entity, 'first_name', None),
                    'last_name': getattr(d.entity, 'last_name', None),
                    'phone': getattr(d.entity, 'phone', None),
                })
        return contacts
    except Exception as e:
        log.error(f"parse_recent_contacts error: {e}")
        return []
    finally:
        await client.disconnect()
