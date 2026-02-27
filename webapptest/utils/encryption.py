from cryptography.fernet import Fernet
from core.config import Config
import base64

def get_cipher() -> Fernet:
    """
    Возвращает объект Fernet для шифрования/дешифрования.
    Ключ берётся из конфигурации (SESSION_ENCRYPTION_KEY) и должен быть в формате base64.
    """
    key = Config.SESSION_ENCRYPTION_KEY
    if not key:
        raise ValueError("SESSION_ENCRYPTION_KEY не установлен в .env")
    # Убедимся, что ключ в байтах
    if isinstance(key, str):
        key = key.encode('utf-8')
    return Fernet(key)

def encrypt_session_data(data: str) -> bytes:
    """
    Шифрует строку с данными сессии Telethon.
    Возвращает зашифрованные байты.
    """
    cipher = get_cipher()
    return cipher.encrypt(data.encode('utf-8'))

def decrypt_session_data(encrypted: bytes) -> str:
    """
    Дешифрует данные сессии.
    Возвращает исходную строку.
    """
    cipher = get_cipher()
    return cipher.decrypt(encrypted).decode('utf-8')