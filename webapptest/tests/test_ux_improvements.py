"""
Tests for UX improvement features:
1. Dark/light theme toggle (set_theme API)
2. Pending delete / undo functionality
3. WS manager helpers
"""
import os
import json
import tempfile
import pytest
from web.app import create_app
from web.extensions import db as _db
from models.user import User
from models.account import Account
from models.proxy import Proxy


@pytest.fixture
def app():
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
    user = User(username='testadmin', role='superadmin')
    user.set_password('testpassword')
    _db.session.add(user)
    _db.session.commit()
    return user


@pytest.fixture
def logged_in_client(client, admin_user):
    """Client with an active admin login session."""
    client.post('/admin/login', data={
        'username': 'testadmin',
        'password': 'testpassword',
    }, follow_redirects=True)
    return client


# ─────────────────────────────────────────────────────────────────
# Theme tests
# ─────────────────────────────────────────────────────────────────

class TestThemeToggle:
    def test_set_theme_dark(self, app, logged_in_client, admin_user):
        """POST /admin/api/set_theme saves dark theme to the user."""
        r = logged_in_client.post(
            '/admin/api/set_theme',
            json={'theme': 'dark'},
            content_type='application/json',
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data['success'] is True
        assert data['theme'] == 'dark'
        with app.app_context():
            user = _db.session.get(User, admin_user.id)
            assert user.theme == 'dark'

    def test_set_theme_light(self, app, logged_in_client, admin_user):
        """POST /admin/api/set_theme saves light theme to the user."""
        r = logged_in_client.post(
            '/admin/api/set_theme',
            json={'theme': 'light'},
            content_type='application/json',
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data['success'] is True
        with app.app_context():
            user = _db.session.get(User, admin_user.id)
            assert user.theme == 'light'

    def test_set_theme_invalid_rejected(self, logged_in_client):
        """Invalid theme values are rejected with 400."""
        r = logged_in_client.post(
            '/admin/api/set_theme',
            json={'theme': 'rainbow'},
            content_type='application/json',
        )
        assert r.status_code == 400
        data = r.get_json()
        assert data['success'] is False

    def test_set_theme_requires_login(self, client):
        """Unauthenticated requests are redirected."""
        r = client.post(
            '/admin/api/set_theme',
            json={'theme': 'light'},
            content_type='application/json',
        )
        assert r.status_code in (302, 401)


# ─────────────────────────────────────────────────────────────────
# Pending delete / undo tests
# ─────────────────────────────────────────────────────────────────

class TestPendingDeletes:
    def test_register_and_confirm(self, app):
        """register_pending → confirm_delete actually runs delete_fn."""
        from web.pending_deletes import register_pending, confirm_delete

        deleted = []

        def do_del():
            deleted.append(True)

        with app.app_context():
            token = register_pending(
                user_id=1,
                entity_type='account',
                entity_id='abc',
                entity_data={'id': 'abc'},
                delete_fn=do_del,
            )
            assert token
            result = confirm_delete(token, user_id=1)
            assert result == 'account'
            assert deleted == [True]

    def test_register_and_cancel(self, app):
        """register_pending → cancel_delete does NOT run delete_fn."""
        from web.pending_deletes import register_pending, cancel_delete

        deleted = []

        def do_del():
            deleted.append(True)

        with app.app_context():
            token = register_pending(
                user_id=1,
                entity_type='proxy',
                entity_id=42,
                entity_data={'id': 42},
                delete_fn=do_del,
            )
            result = cancel_delete(token, user_id=1)
            assert result == {'id': 42}
            assert deleted == []  # delete_fn was NOT called

    def test_wrong_user_cannot_confirm(self, app):
        """Only the owning user can confirm the pending delete."""
        from web.pending_deletes import register_pending, confirm_delete

        with app.app_context():
            token = register_pending(
                user_id=1,
                entity_type='account',
                entity_id='x',
                entity_data={},
                delete_fn=lambda: None,
            )
            result = confirm_delete(token, user_id=999)
            assert result is None

    def test_wrong_user_cannot_cancel(self, app):
        """Only the owning user can cancel the pending delete."""
        from web.pending_deletes import register_pending, cancel_delete

        with app.app_context():
            token = register_pending(
                user_id=1,
                entity_type='account',
                entity_id='x',
                entity_data={},
                delete_fn=lambda: None,
            )
            result = cancel_delete(token, user_id=999)
            assert result is None

    def test_account_delete_returns_undo_token(self, app, logged_in_client):
        """DELETE /admin/accounts/<id>/delete returns undo_token instead of instant delete."""
        import uuid
        with app.app_context():
            account = Account(id=uuid.uuid4().hex, phone='+79001234567')
            _db.session.add(account)
            _db.session.commit()
            account_id = account.id

        r = logged_in_client.post(f'/admin/accounts/{account_id}/delete')
        assert r.status_code == 200
        data = r.get_json()
        assert data['success'] is True
        assert 'undo_token' in data
        assert data['expires_in'] > 0

        # Account should still exist in DB (not yet deleted)
        with app.app_context():
            still_exists = _db.session.get(Account, account_id)
            assert still_exists is not None

    def test_proxy_delete_returns_undo_token(self, app, logged_in_client):
        """DELETE /admin/proxies/<id>/delete returns undo_token instead of instant delete."""
        with app.app_context():
            proxy = Proxy(type='socks5', host='1.2.3.4', port=1080)
            _db.session.add(proxy)
            _db.session.commit()
            proxy_id = proxy.id

        r = logged_in_client.post(f'/admin/proxies/{proxy_id}/delete')
        assert r.status_code == 200
        data = r.get_json()
        assert data['success'] is True
        assert 'undo_token' in data

        # Proxy should still exist in DB
        with app.app_context():
            still_exists = _db.session.get(Proxy, proxy_id)
            assert still_exists is not None

    def test_pending_delete_confirm_api(self, app, logged_in_client, admin_user):
        """POST /admin/api/pending_delete/<token>/confirm executes deferred delete."""
        import uuid
        from web.pending_deletes import register_pending

        with app.app_context():
            account = Account(id=uuid.uuid4().hex, phone='+79001234568')
            _db.session.add(account)
            _db.session.commit()
            account_id = account.id

            def do_del():
                a = _db.session.get(Account, account_id)
                if a:
                    _db.session.delete(a)
                    _db.session.commit()

            token = register_pending(
                user_id=admin_user.id,
                entity_type='account',
                entity_id=account_id,
                entity_data={'id': account_id},
                delete_fn=do_del,
            )

        r = logged_in_client.post(f'/admin/api/pending_delete/{token}/confirm')
        assert r.status_code == 200
        assert r.get_json()['success'] is True

        with app.app_context():
            assert _db.session.get(Account, account_id) is None

    def test_pending_delete_cancel_api(self, app, logged_in_client, admin_user):
        """POST /admin/api/pending_delete/<token>/cancel does not delete the item."""
        from web.pending_deletes import register_pending

        deleted = []
        with app.app_context():
            token = register_pending(
                user_id=admin_user.id,
                entity_type='proxy',
                entity_id=99,
                entity_data={'id': 99},
                delete_fn=lambda: deleted.append(True),
            )

        r = logged_in_client.post(f'/admin/api/pending_delete/{token}/cancel')
        assert r.status_code == 200
        assert r.get_json()['success'] is True
        assert deleted == []


# ─────────────────────────────────────────────────────────────────
# WS Manager unit tests
# ─────────────────────────────────────────────────────────────────

class TestWsManager:
    def test_register_returns_queue(self):
        from web.ws_manager import register, unregister
        q = register(42)
        assert q is not None
        unregister(42, q)

    def test_broadcast_delivers_message(self):
        from web.ws_manager import register, unregister, broadcast_to_user
        q = register(7)
        broadcast_to_user(7, 'test_event', {'key': 'val'})
        msg = q.get_nowait()
        data = json.loads(msg)
        assert data['type'] == 'test_event'
        assert data['key'] == 'val'
        unregister(7, q)

    def test_broadcast_to_all(self):
        from web.ws_manager import register, unregister, broadcast_to_all
        q1 = register(10)
        q2 = register(11)
        broadcast_to_all('alert', {'message': 'hi'})
        m1 = json.loads(q1.get_nowait())
        m2 = json.loads(q2.get_nowait())
        assert m1['type'] == 'alert'
        assert m2['type'] == 'alert'
        unregister(10, q1)
        unregister(11, q2)

    def test_unregister_stops_delivery(self):
        import queue as q_mod
        from web.ws_manager import register, unregister, broadcast_to_user
        q = register(20)
        unregister(20, q)
        broadcast_to_user(20, 'test', {})
        with pytest.raises(q_mod.Empty):
            q.get_nowait()
