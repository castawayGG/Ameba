"""
Tests for Telegram-related utilities: encryption, proxy parsing,
and the User model's authentication helpers.
"""
import pytest
from unittest.mock import patch, MagicMock
from models.user import User
from models.proxy import Proxy
from utils.helpers import (
    generate_random_id,
    truncate_text,
    format_bytes,
    sanitize_phone,
    utcnow,
)


# ---------------------------------------------------------------------------
# User model tests
# ---------------------------------------------------------------------------

class TestUserModel:
    def test_set_and_check_password(self):
        user = User(username='alice')
        user.set_password('secret123')
        assert user.check_password('secret123') is True
        assert user.check_password('wrongpass') is False

    def test_check_password_empty_hash(self):
        user = User(username='bob', password_hash='')
        assert user.check_password('anything') is False

    def test_verify_otp_no_secret_returns_true(self):
        """When 2FA is not configured, verify_otp should return True."""
        user = User(username='charlie', otp_secret=None)
        assert user.verify_otp('123456') is True

    def test_verify_otp_wrong_token(self):
        import pyotp
        secret = pyotp.random_base32()
        user = User(username='dave', otp_secret=secret)
        assert user.verify_otp('000000') is False

    def test_verify_otp_correct_token(self):
        import pyotp
        secret = pyotp.random_base32()
        user = User(username='eve', otp_secret=secret)
        token = pyotp.TOTP(secret).now()
        assert user.verify_otp(token) is True

    def test_is_locked_when_locked_until_in_future(self):
        from datetime import datetime, timedelta, timezone
        user = User(username='frank')
        user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=10)
        assert user.is_locked() is True

    def test_is_not_locked_when_locked_until_in_past(self):
        from datetime import datetime, timedelta, timezone
        user = User(username='grace')
        user.locked_until = datetime.now(timezone.utc) - timedelta(minutes=1)
        assert user.is_locked() is False

    def test_is_not_locked_when_no_locked_until(self):
        user = User(username='henry', locked_until=None)
        assert user.is_locked() is False

    def test_get_id_returns_string(self):
        user = User(username='iris')
        user.id = 42
        assert user.get_id() == '42'

    def test_is_anonymous_false(self):
        user = User(username='jack')
        assert user.is_anonymous is False

    def test_is_authenticated_true(self):
        user = User(username='kate')
        assert user.is_authenticated is True


# ---------------------------------------------------------------------------
# Proxy model tests
# ---------------------------------------------------------------------------

class TestProxyParsing:
    def test_full_socks5_string(self):
        result = Proxy.parse_proxy_string('socks5://user:pass@192.168.1.1:1080')
        assert result is not None
        assert result['type'] == 'socks5'
        assert result['host'] == '192.168.1.1'
        assert result['port'] == 1080
        assert result['username'] == 'user'
        assert result['password'] == 'pass'

    def test_http_no_credentials(self):
        result = Proxy.parse_proxy_string('http://10.0.0.1:8080')
        assert result is not None
        assert result['type'] == 'http'
        assert result['host'] == '10.0.0.1'
        assert result['port'] == 8080
        assert result['username'] is None
        assert result['password'] is None

    def test_bare_host_port_defaults_to_socks5(self):
        result = Proxy.parse_proxy_string('1.2.3.4:3128')
        assert result is not None
        assert result['type'] == 'socks5'
        assert result['host'] == '1.2.3.4'
        assert result['port'] == 3128

    def test_invalid_string_returns_none(self):
        assert Proxy.parse_proxy_string('not_a_proxy') is None
        assert Proxy.parse_proxy_string('') is None


# ---------------------------------------------------------------------------
# Helper function tests
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_generate_random_id_length(self):
        assert len(generate_random_id(16)) == 16
        assert len(generate_random_id(32)) == 32

    def test_generate_random_id_alphanumeric(self):
        id_ = generate_random_id(50)
        assert id_.isalnum()

    def test_truncate_text_short_string(self):
        assert truncate_text('hi', 10) == 'hi'

    def test_truncate_text_long_string(self):
        result = truncate_text('a' * 110, 100)
        assert len(result) == 100
        assert result.endswith('...')

    def test_truncate_text_none(self):
        assert truncate_text(None, 10) is None

    def test_format_bytes_bytes(self):
        assert format_bytes(500) == '500.0 B'

    def test_format_bytes_kilobytes(self):
        assert format_bytes(2048) == '2.0 KB'

    def test_format_bytes_megabytes(self):
        assert '1.0 MB' == format_bytes(1024 * 1024)

    def test_sanitize_phone(self):
        assert sanitize_phone('+380 (99) 123-45-67') == '380991234567'

    def test_utcnow_is_timezone_aware(self):
        from datetime import timezone
        dt = utcnow()
        assert dt.tzinfo is not None
        assert dt.tzinfo == timezone.utc


# ---------------------------------------------------------------------------
# Encryption utility tests
# ---------------------------------------------------------------------------

class TestEncryption:
    def test_encrypt_decrypt_roundtrip(self):
        from cryptography.fernet import Fernet
        key = Fernet.generate_key()
        with patch('utils.encryption.Config') as mock_cfg:
            mock_cfg.SESSION_ENCRYPTION_KEY = key
            from utils.encryption import encrypt_session_data, decrypt_session_data
            original = 'test_session_data_123'
            encrypted = encrypt_session_data(original)
            assert isinstance(encrypted, bytes)
            assert encrypt_session_data(original) != original.encode()
            decrypted = decrypt_session_data(encrypted)
            assert decrypted == original

# ---------------------------------------------------------------------------
# New Telethon action functions tests
# ---------------------------------------------------------------------------

class TestTelegramActions:
    """Unit tests for new functions added to services/telegram/actions.py."""

    def test_check_spambot_returns_dict(self):
        """check_spambot result must include 'status' key."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_client = MagicMock()
        mock_client.get_entity = AsyncMock(return_value=MagicMock())
        mock_client.send_message = AsyncMock()
        mock_client.delete_dialog = AsyncMock()
        mock_client.disconnect = AsyncMock()

        # Simulate a "clean" spambot response
        msg = MagicMock()
        msg.out = False
        msg.text = "Good news, no limits for this account!"
        mock_client.get_messages = AsyncMock(return_value=[msg])

        with patch('services.telegram.actions.get_telegram_client', AsyncMock(return_value=mock_client)):
            import services.telegram.actions as actions
            result = asyncio.run(actions.check_spambot('test_account'))

        assert 'status' in result
        assert result['status'] == 'clean'
        assert 'text' in result

    def test_check_spambot_limited_status(self):
        """check_spambot should return 'limited' for spam-restricted accounts."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_client = MagicMock()
        mock_client.get_entity = AsyncMock(return_value=MagicMock())
        mock_client.send_message = AsyncMock()
        mock_client.delete_dialog = AsyncMock()
        mock_client.disconnect = AsyncMock()

        msg = MagicMock()
        msg.out = False
        msg.text = "Unfortunately, your account has spam limits."
        mock_client.get_messages = AsyncMock(return_value=[msg])

        with patch('services.telegram.actions.get_telegram_client', AsyncMock(return_value=mock_client)):
            import services.telegram.actions as actions
            result = asyncio.run(actions.check_spambot('test_account'))

        assert result['status'] == 'limited'

    def test_parse_recent_contacts_returns_list(self):
        """parse_recent_contacts should return a list of user dicts."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_client = MagicMock()
        mock_client.disconnect = AsyncMock()

        user_entity = MagicMock()
        user_entity.id = 123456
        user_entity.username = 'testuser'
        user_entity.first_name = 'Test'
        user_entity.last_name = 'User'
        user_entity.phone = '+1234567890'
        user_entity.bot = False

        dialog = MagicMock()
        dialog.is_user = True
        dialog.entity = user_entity

        mock_client.get_dialogs = AsyncMock(return_value=[dialog])

        with patch('services.telegram.actions.get_telegram_client', AsyncMock(return_value=mock_client)):
            import services.telegram.actions as actions
            result = asyncio.run(actions.parse_recent_contacts('test_account'))

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]['user_id'] == 123456
        assert result[0]['username'] == 'testuser'

    def test_parse_recent_contacts_excludes_bots(self):
        """parse_recent_contacts should exclude bot accounts."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch

        mock_client = MagicMock()
        mock_client.disconnect = AsyncMock()

        bot_entity = MagicMock()
        bot_entity.id = 999
        bot_entity.bot = True

        dialog = MagicMock()
        dialog.is_user = True
        dialog.entity = bot_entity

        mock_client.get_dialogs = AsyncMock(return_value=[dialog])

        with patch('services.telegram.actions.get_telegram_client', AsyncMock(return_value=mock_client)):
            import services.telegram.actions as actions
            result = asyncio.run(actions.parse_recent_contacts('test_account'))

        assert result == []
