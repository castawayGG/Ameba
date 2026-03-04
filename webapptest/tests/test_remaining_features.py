"""
Tests for remaining unimplemented features:
  - Account ownership filtering (team isolation)
  - Auto-API import connector (number_import service and routes)
"""
import io
import json
import os
import tempfile
import uuid
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Shared Flask app fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def app():
    from web.app import create_app
    from web.extensions import db as _db
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


def _make_user(db, username, role='admin', password='secret'):
    from models.user import User
    u = User(username=username, role=role)
    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    return u


def _login(client, username, password='secret'):
    client.post('/admin/login', data={'username': username, 'password': password})


def _make_account(db, phone, owner_id=None):
    from models.account import Account
    a = Account(id=uuid.uuid4().hex, phone=phone, status='inactive', owner_id=owner_id)
    db.session.add(a)
    db.session.commit()
    return a


# ---------------------------------------------------------------------------
# Account ownership filtering (team isolation)
# ---------------------------------------------------------------------------

class TestAccountOwnershipFiltering:
    """
    Non-superadmin users should only see / export / delete their own accounts.
    Superadmins always see everything.
    """

    def test_superadmin_sees_all_accounts(self, app, client):
        from web.extensions import db
        with app.app_context():
            su = _make_user(db, 'superadmin', role='superadmin')
            a1 = _make_account(db, '+70001110001', owner_id=su.id)
            a2 = _make_account(db, '+70002220002', owner_id=None)
        _login(client, 'superadmin')
        resp = client.get('/admin/accounts')
        assert resp.status_code == 200
        data = resp.data.decode()
        assert '+70001110001' in data
        assert '+70002220002' in data

    def test_regular_admin_sees_only_own_accounts(self, app, client):
        from web.extensions import db
        with app.app_context():
            admin = _make_user(db, 'admin1', role='admin')
            other = _make_user(db, 'admin2', role='admin')
            _make_account(db, '+71110000001', owner_id=admin.id)
            _make_account(db, '+72220000002', owner_id=other.id)
        _login(client, 'admin1')
        resp = client.get('/admin/accounts')
        assert resp.status_code == 200
        data = resp.data.decode()
        assert '+71110000001' in data
        assert '+72220000002' not in data

    def test_regular_admin_cannot_bulk_delete_other_owners_account(self, app, client):
        from web.extensions import db
        with app.app_context():
            admin = _make_user(db, 'admin1', role='admin')
            other = _make_user(db, 'admin2', role='admin')
            a_own = _make_account(db, '+71110000001', owner_id=admin.id)
            a_other = _make_account(db, '+72220000002', owner_id=other.id)
            own_id = a_own.id
            other_id = a_other.id
        _login(client, 'admin1')
        resp = client.post(
            '/admin/accounts/bulk_delete',
            json={'ids': [own_id, other_id]},
        )
        assert resp.status_code == 200
        d = resp.get_json()
        assert d['success'] is True
        assert d['deleted'] == 1  # only own account deleted

    def test_superadmin_can_bulk_delete_any_account(self, app, client):
        from web.extensions import db
        with app.app_context():
            su = _make_user(db, 'superadmin', role='superadmin')
            other = _make_user(db, 'admin2', role='admin')
            a1 = _make_account(db, '+71110000001', owner_id=su.id)
            a2 = _make_account(db, '+72220000002', owner_id=other.id)
            id1, id2 = a1.id, a2.id
        _login(client, 'superadmin')
        resp = client.post(
            '/admin/accounts/bulk_delete',
            json={'ids': [id1, id2]},
        )
        assert resp.status_code == 200
        d = resp.get_json()
        assert d['deleted'] == 2

    def test_csv_export_respects_ownership(self, app, client):
        from web.extensions import db
        with app.app_context():
            admin = _make_user(db, 'admin1', role='admin')
            other = _make_user(db, 'admin2', role='admin')
            _make_account(db, '+71110000001', owner_id=admin.id)
            _make_account(db, '+72220000002', owner_id=other.id)
        _login(client, 'admin1')
        resp = client.get('/admin/export/accounts/csv')
        assert resp.status_code == 200
        data = resp.data.decode()
        assert '+71110000001' in data
        assert '+72220000002' not in data

    def test_txt_export_respects_ownership(self, app, client):
        from web.extensions import db
        with app.app_context():
            admin = _make_user(db, 'admin1', role='admin')
            other = _make_user(db, 'admin2', role='admin')
            _make_account(db, '+71110000001', owner_id=admin.id)
            _make_account(db, '+72220000002', owner_id=other.id)
        _login(client, 'admin1')
        resp = client.get('/admin/export/accounts/txt')
        assert resp.status_code == 200
        data = resp.data.decode()
        assert '+71110000001' in data
        assert '+72220000002' not in data


# ---------------------------------------------------------------------------
# Auto-API import connector — number_import service
# ---------------------------------------------------------------------------

class TestNumberImportService:
    """Unit tests for services/accounts/number_import.py"""

    def test_fetch_numbers_json_flat_array(self):
        """Simple JSON array of phone strings."""
        from services.accounts.number_import import fetch_numbers
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {'Content-Type': 'application/json'}
        mock_resp.json.return_value = ['+79001234567', '+79001234568']
        mock_resp.raise_for_status = lambda: None

        with patch('services.accounts.number_import.requests.get', return_value=mock_resp):
            numbers, error = fetch_numbers('https://example.com/numbers')
        assert error is None
        assert '+79001234567' in numbers
        assert '+79001234568' in numbers

    def test_fetch_numbers_json_nested_path(self):
        """JSON object with nested phones extracted via json_path."""
        from services.accounts.number_import import fetch_numbers
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {'Content-Type': 'application/json'}
        mock_resp.json.return_value = {'data': {'phones': ['+79000000001', '+79000000002']}}
        mock_resp.raise_for_status = lambda: None

        with patch('services.accounts.number_import.requests.get', return_value=mock_resp):
            numbers, error = fetch_numbers(
                'https://example.com/api', json_path='data.phones'
            )
        assert error is None
        assert len(numbers) == 2

    def test_fetch_numbers_json_objects_with_phone_field(self):
        """JSON array of objects with 'phone' field."""
        from services.accounts.number_import import fetch_numbers
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {'Content-Type': 'application/json'}
        mock_resp.json.return_value = [
            {'phone': '+79000000001', 'name': 'Alice'},
            {'phone': '+79000000002', 'name': 'Bob'},
        ]
        mock_resp.raise_for_status = lambda: None

        with patch('services.accounts.number_import.requests.get', return_value=mock_resp):
            numbers, error = fetch_numbers('https://example.com/api')
        assert error is None
        assert '+79000000001' in numbers
        assert '+79000000002' in numbers

    def test_fetch_numbers_csv_url(self):
        """CSV / TXT URL with one phone per line."""
        from services.accounts.number_import import fetch_numbers
        csv_body = '+79000000001\n+79000000002\n+79000000003\n'
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {'Content-Type': 'text/plain'}
        mock_resp.text = csv_body
        mock_resp.raise_for_status = lambda: None

        with patch('services.accounts.number_import.requests.get', return_value=mock_resp):
            numbers, error = fetch_numbers(
                'https://example.com/phones.txt', source_type='csv_url'
            )
        assert error is None
        assert len(numbers) == 3

    def test_fetch_numbers_deduplicates(self):
        """Duplicate numbers in source are returned only once."""
        from services.accounts.number_import import fetch_numbers
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {'Content-Type': 'application/json'}
        mock_resp.json.return_value = ['+79000000001', '+79000000001', '+79000000002']
        mock_resp.raise_for_status = lambda: None

        with patch('services.accounts.number_import.requests.get', return_value=mock_resp):
            numbers, error = fetch_numbers('https://example.com/api')
        assert error is None
        assert numbers.count('+79000000001') == 1

    def test_fetch_numbers_timeout_error(self):
        """Timeout returns an error message instead of raising."""
        import requests as req
        from services.accounts.number_import import fetch_numbers

        with patch('services.accounts.number_import.requests.get',
                   side_effect=req.exceptions.Timeout()):
            numbers, error = fetch_numbers('https://example.com/api')
        assert numbers == []
        assert error is not None
        assert 'время' in error.lower()

    def test_fetch_numbers_http_error(self):
        """HTTP 403 returns an error message."""
        import requests as req
        from services.accounts.number_import import fetch_numbers
        err_resp = MagicMock()
        err_resp.status_code = 403
        exc = req.exceptions.HTTPError(response=err_resp)

        def _raise_for_status():
            raise exc

        mock_resp = MagicMock()
        mock_resp.raise_for_status = _raise_for_status

        with patch('services.accounts.number_import.requests.get', return_value=mock_resp):
            numbers, error = fetch_numbers('https://example.com/api')
        assert numbers == []
        assert '403' in (error or '')

    def test_fetch_numbers_invalid_json(self):
        """Non-JSON content-type response returns an error."""
        from services.accounts.number_import import fetch_numbers
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {'Content-Type': 'application/json'}
        mock_resp.json.side_effect = ValueError('not json')
        mock_resp.raise_for_status = lambda: None

        with patch('services.accounts.number_import.requests.get', return_value=mock_resp):
            numbers, error = fetch_numbers('https://example.com/api')
        assert numbers == []
        assert error is not None

    def test_fetch_numbers_unknown_source_type(self):
        """Unknown source_type returns an error."""
        from services.accounts.number_import import fetch_numbers
        mock_resp = MagicMock()
        mock_resp.raise_for_status = lambda: None
        mock_resp.headers = {'Content-Type': 'text/plain'}
        mock_resp.text = '+79000000001'

        with patch('services.accounts.number_import.requests.get', return_value=mock_resp):
            numbers, error = fetch_numbers('https://example.com', source_type='unknown')
        assert numbers == []
        assert error is not None

    def test_fetch_numbers_ssrf_private_ip_blocked(self):
        """Requests to private IP ranges must be blocked."""
        from services.accounts.number_import import fetch_numbers
        for private_url in [
            'http://127.0.0.1/api',
            'http://192.168.1.1/numbers',
            'http://10.0.0.1/phones',
            'http://172.16.0.1/data',
        ]:
            numbers, error = fetch_numbers(private_url)
            assert numbers == [], f'Expected block for {private_url}'
            assert error is not None, f'Expected error for {private_url}'
            assert 'SSRF' in error or 'внутренний' in error.lower()

    def test_fetch_numbers_non_http_scheme_blocked(self):
        """Non-HTTP(S) schemes must be rejected."""
        from services.accounts.number_import import fetch_numbers
        numbers, error = fetch_numbers('ftp://example.com/numbers.txt')
        assert numbers == []
        assert error is not None


# ---------------------------------------------------------------------------
# Auto-API import connector — routes
# ---------------------------------------------------------------------------

class TestNumberImportRoutes:
    """Integration tests for the /admin/number_import* endpoints."""

    @pytest.fixture(autouse=True)
    def _setup(self, app, client):
        from web.extensions import db
        with app.app_context():
            self._admin = _make_user(db, 'admin1', role='admin')
        _login(client, 'admin1')
        self._client = client

    def test_number_import_page_loads(self):
        resp = self._client.get('/admin/number_import')
        assert resp.status_code == 200
        assert 'Авто-импорт' in resp.data.decode()

    def test_save_and_get_settings(self):
        payload = {
            'number_import_url': 'https://example.com/api',
            'number_import_type': 'custom_json',
            'number_import_auth': 'Bearer token123',
            'number_import_json_path': 'data',
        }
        r = self._client.post(
            '/admin/api/number_import/settings',
            json=payload,
        )
        assert r.status_code == 200
        assert r.get_json()['success'] is True

        r2 = self._client.get('/admin/api/number_import/settings')
        assert r2.status_code == 200
        d = r2.get_json()
        assert d['settings']['number_import_url'] == 'https://example.com/api'
        assert d['settings']['number_import_json_path'] == 'data'

    def test_run_import_no_url_returns_400(self):
        resp = self._client.post('/admin/api/number_import/run', json={})
        assert resp.status_code == 400
        assert resp.get_json()['success'] is False

    def test_run_import_creates_accounts(self, app):
        def _mock_fetch(url, source_type, auth_header, json_path, **kw):
            return ['+79000000001', '+79000000002'], None

        with patch('services.accounts.number_import.fetch_numbers', _mock_fetch):
            resp = self._client.post(
                '/admin/api/number_import/run',
                json={'url': 'https://example.com/numbers'},
            )
        assert resp.status_code == 200
        d = resp.get_json()
        assert d['success'] is True
        assert d['added'] == 2
        assert d['skipped'] == 0

        # Verify the accounts are in DB with correct owner
        with app.app_context():
            from web.extensions import db
            from models.account import Account
            accs = db.session.query(Account).filter(
                Account.phone.in_(['+79000000001', '+79000000002'])
            ).all()
            assert len(accs) == 2
            # Owner should be the logged-in user
            owner_ids = {a.owner_id for a in accs}
            assert len(owner_ids) == 1  # all owned by the same user

    def test_run_import_skips_existing_phones(self, app):
        # Pre-create one of the phones
        from web.extensions import db
        with app.app_context():
            from models.account import Account
            db.session.add(Account(id=uuid.uuid4().hex, phone='+79000000001', status='inactive'))
            db.session.commit()

        def _mock_fetch(url, source_type, auth_header, json_path, **kw):
            return ['+79000000001', '+79000000003'], None

        with patch('services.accounts.number_import.fetch_numbers', _mock_fetch):
            resp = self._client.post(
                '/admin/api/number_import/run',
                json={'url': 'https://example.com/numbers'},
            )
        d = resp.get_json()
        assert d['success'] is True
        assert d['added'] == 1
        assert d['skipped'] == 1

    def test_run_import_service_error_returns_502(self):
        def _mock_fetch(url, source_type, auth_header, json_path, **kw):
            return [], 'Ошибка соединения с сервером'

        with patch('services.accounts.number_import.fetch_numbers', _mock_fetch):
            resp = self._client.post(
                '/admin/api/number_import/run',
                json={'url': 'https://example.com/numbers'},
            )
        assert resp.status_code == 502
        assert resp.get_json()['success'] is False

    def test_run_import_unknown_source_type_returns_400(self):
        resp = self._client.post(
            '/admin/api/number_import/run',
            json={'url': 'https://example.com/api', 'source_type': 'invalid_type'},
        )
        assert resp.status_code == 400
