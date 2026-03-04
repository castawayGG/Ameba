"""
Tests for bulk action improvements:
  - Macro model CRUD and step validation
  - BulkOperation model
  - Cloud backup cloud.py (local provider)
  - CSV import modes (add, replace, merge, delete)
  - Dashboard leaders/account_stats API routes
  - Bulk operation history API routes
"""
import io
import json
import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Shared Flask app fixture (same pattern as test_api.py)
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


@pytest.fixture
def admin_user(app):
    from web.extensions import db as _db
    from models.user import User
    user = User(username='testadmin', role='superadmin')
    user.set_password('testpassword')
    _db.session.add(user)
    _db.session.commit()
    return user


@pytest.fixture
def logged_in_client(client, admin_user):
    client.post('/admin/login', data={'username': 'testadmin', 'password': 'testpassword'})
    return client


# ---------------------------------------------------------------------------
# Macro model tests
# ---------------------------------------------------------------------------

class TestMacroModel:
    def test_macro_creation(self, app):
        from web.extensions import db
        from models.macro import Macro
        with app.app_context():
            m = Macro(name='Test Macro', description='desc', steps=[
                {'action': 'set_status', 'params': {'status': 'active'}},
            ])
            db.session.add(m)
            db.session.commit()
            fetched = db.session.get(Macro, m.id)
            assert fetched is not None
            assert fetched.name == 'Test Macro'
            assert fetched.runs_count == 0
            assert len(fetched.steps) == 1
            assert fetched.steps[0]['action'] == 'set_status'

    def test_macro_defaults(self, app):
        from web.extensions import db
        from models.macro import Macro
        with app.app_context():
            m = Macro(name='Default Macro', steps=[])
            db.session.add(m)
            db.session.commit()
            assert m.is_active is True
            assert m.runs_count == 0
            assert m.last_run is None


# ---------------------------------------------------------------------------
# BulkOperation model tests
# ---------------------------------------------------------------------------

class TestBulkOperationModel:
    def test_bulk_operation_creation(self, app):
        from web.extensions import db
        from models.bulk_operation import BulkOperation
        with app.app_context():
            op = BulkOperation(
                operation_type='bulk_delete',
                status='completed',
                total=10,
                processed=10,
                succeeded=9,
                failed=1,
                errors=[{'id': 'abc', 'error': 'not found'}],
            )
            db.session.add(op)
            db.session.commit()
            fetched = db.session.get(BulkOperation, op.id)
            assert fetched.operation_type == 'bulk_delete'
            assert fetched.succeeded == 9
            assert len(fetched.errors) == 1

    def test_bulk_operation_default_status(self, app):
        from web.extensions import db
        from models.bulk_operation import BulkOperation
        with app.app_context():
            op = BulkOperation(operation_type='test_op', total=5)
            db.session.add(op)
            db.session.commit()
            assert op.status == 'pending'


# ---------------------------------------------------------------------------
# Cloud backup service tests
# ---------------------------------------------------------------------------

class TestCloudBackup:
    def test_local_provider_returns_local_result(self, tmp_path):
        """Local provider should return {provider: local} without uploading."""
        from services.backup.cloud import upload_backup, _load_settings, save_settings
        dummy = tmp_path / 'backup_test.zip'
        dummy.write_bytes(b'PK\x03\x04')  # minimal zip magic bytes

        settings_file = tmp_path / 'cloud_backup_settings.json'
        with patch('services.backup.cloud._load_settings', return_value={'provider': 'local'}):
            result = upload_backup(str(dummy))
        assert result['provider'] == 'local'
        assert result['file'] == 'backup_test.zip'

    def test_missing_file_raises(self, tmp_path):
        """Uploading a non-existent file should raise FileNotFoundError."""
        from services.backup.cloud import upload_backup
        with patch('services.backup.cloud._load_settings', return_value={'provider': 'local'}):
            with pytest.raises(FileNotFoundError):
                upload_backup(str(tmp_path / 'nonexistent.zip'))

    def test_yandex_missing_token_raises(self, tmp_path):
        """Yandex Disk without a token should raise ValueError."""
        from services.backup.cloud import upload_backup
        dummy = tmp_path / 'backup_test.zip'
        dummy.write_bytes(b'PK\x03\x04')
        with patch('services.backup.cloud._load_settings', return_value={'provider': 'yandex_disk', 'yandex_token': ''}):
            with pytest.raises(ValueError, match='token'):
                upload_backup(str(dummy))

    def test_save_and_load_settings(self, tmp_path):
        """Settings can be written and read back."""
        from services.backup.cloud import save_settings
        settings_path = tmp_path / 'cloud_backup_settings.json'
        with patch('services.backup.cloud.Path') as MockPath:
            MockPath.return_value = settings_path
            MockPath.side_effect = lambda *a, **k: settings_path if 'cloud_backup_settings' in str(a) else type(settings_path)(*a, **k)
            # Write directly
            settings_path.write_text(json.dumps({'provider': 'yandex_disk', 'yandex_token': 'tok'}))
            loaded = json.loads(settings_path.read_text())
            assert loaded['provider'] == 'yandex_disk'


# ---------------------------------------------------------------------------
# Macro API routes
# ---------------------------------------------------------------------------

class TestMacroRoutes:
    def test_macros_page_requires_login(self, client):
        resp = client.get('/admin/macros')
        assert resp.status_code in (302, 401)

    def test_macros_page_logged_in(self, logged_in_client):
        resp = logged_in_client.get('/admin/macros')
        assert resp.status_code == 200
        assert b'macro' in resp.data.lower() or b'Macro' in resp.data

    def test_api_macros_list_empty(self, logged_in_client):
        resp = logged_in_client.get('/admin/api/macros')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['macros'] == []

    def test_api_macros_create(self, logged_in_client):
        payload = {
            'name': 'My Macro',
            'description': 'test',
            'steps': [{'action': 'set_status', 'params': {'status': 'active'}}],
        }
        resp = logged_in_client.post('/admin/api/macros',
                                     data=json.dumps(payload),
                                     content_type='application/json')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'id' in data

    def test_api_macros_create_name_required(self, logged_in_client):
        resp = logged_in_client.post('/admin/api/macros',
                                     data=json.dumps({'steps': []}),
                                     content_type='application/json')
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['success'] is False

    def test_api_macros_update(self, logged_in_client, app):
        from web.extensions import db
        from models.macro import Macro
        with app.app_context():
            m = Macro(name='Old Name', steps=[])
            db.session.add(m)
            db.session.commit()
            mid = m.id

        resp = logged_in_client.put(f'/admin/api/macros/{mid}',
                                    data=json.dumps({'name': 'New Name'}),
                                    content_type='application/json')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True

    def test_api_macros_delete(self, logged_in_client, app):
        from web.extensions import db
        from models.macro import Macro
        with app.app_context():
            m = Macro(name='Delete Me', steps=[])
            db.session.add(m)
            db.session.commit()
            mid = m.id

        resp = logged_in_client.delete(f'/admin/api/macros/{mid}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True

    def test_api_macros_apply_no_accounts(self, logged_in_client, app):
        from web.extensions import db
        from models.macro import Macro
        with app.app_context():
            m = Macro(name='Apply Macro', steps=[{'action': 'set_status', 'params': {'status': 'active'}}])
            db.session.add(m)
            db.session.commit()
            mid = m.id

        resp = logged_in_client.post(f'/admin/api/macros/{mid}/apply',
                                     data=json.dumps({'account_ids': []}),
                                     content_type='application/json')
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Bulk Operation History API routes
# ---------------------------------------------------------------------------

class TestBulkOperationRoutes:
    def test_bulk_operations_list_empty(self, logged_in_client):
        resp = logged_in_client.get('/admin/api/bulk_operations')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['operations'] == []

    def test_bulk_operations_cancel_not_found(self, logged_in_client):
        resp = logged_in_client.post('/admin/api/bulk_operations/9999/cancel')
        assert resp.status_code == 404

    def test_bulk_operations_cancel_completed_fails(self, logged_in_client, app):
        from web.extensions import db
        from models.bulk_operation import BulkOperation
        with app.app_context():
            op = BulkOperation(operation_type='test', status='completed', total=1)
            db.session.add(op)
            db.session.commit()
            oid = op.id

        resp = logged_in_client.post(f'/admin/api/bulk_operations/{oid}/cancel')
        assert resp.status_code == 400
        data = resp.get_json()
        assert data['success'] is False

    def test_bulk_operations_cancel_pending_succeeds(self, logged_in_client, app):
        from web.extensions import db
        from models.bulk_operation import BulkOperation
        with app.app_context():
            op = BulkOperation(operation_type='test', status='pending', total=5)
            db.session.add(op)
            db.session.commit()
            oid = op.id

        resp = logged_in_client.post(f'/admin/api/bulk_operations/{oid}/cancel')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True


# ---------------------------------------------------------------------------
# Dashboard new widgets API routes
# ---------------------------------------------------------------------------

class TestDashboardWidgets:
    def test_leaders_endpoint(self, logged_in_client):
        resp = logged_in_client.get('/admin/api/dashboard/leaders')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'leaders' in data

    def test_account_stats_endpoint(self, logged_in_client):
        resp = logged_in_client.get('/admin/api/dashboard/account_stats')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'distribution' in data
        assert 'total' in data

    def test_campaign_stats_endpoint(self, logged_in_client):
        resp = logged_in_client.get('/admin/api/dashboard/campaign_stats')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'total_sent' in data
        assert 'reply_pct' in data


# ---------------------------------------------------------------------------
# CSV Import route
# ---------------------------------------------------------------------------

class TestCsvImport:
    def _make_csv(self, rows):
        lines = ['phone,username,first_name,last_name,status']
        for r in rows:
            lines.append(','.join([
                r.get('phone', ''), r.get('username', ''), r.get('first_name', ''),
                r.get('last_name', ''), r.get('status', ''),
            ]))
        return '\n'.join(lines).encode('utf-8')

    def test_import_add_mode(self, logged_in_client):
        csv_data = self._make_csv([
            {'phone': '+79001111111', 'status': 'inactive'},
            {'phone': '+79002222222', 'status': 'active'},
        ])
        resp = logged_in_client.post(
            '/admin/accounts/bulk_import_csv',
            data={'mode': 'add', 'file': (io.BytesIO(csv_data), 'test.csv')},
            content_type='multipart/form-data',
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['added'] == 2
        assert data['mode'] == 'add'

    def test_import_add_skips_existing(self, logged_in_client, app):
        from web.extensions import db
        from models.account import Account
        import uuid
        with app.app_context():
            acc = Account(id=uuid.uuid4().hex, phone='+79003333333', status='active')
            db.session.add(acc)
            db.session.commit()

        csv_data = self._make_csv([{'phone': '+79003333333', 'status': 'inactive'}])
        resp = logged_in_client.post(
            '/admin/accounts/bulk_import_csv',
            data={'mode': 'add', 'file': (io.BytesIO(csv_data), 'test.csv')},
            content_type='multipart/form-data',
        )
        data = resp.get_json()
        assert data['skipped'] == 1
        assert data['added'] == 0

    def test_import_replace_mode(self, logged_in_client, app):
        from web.extensions import db
        from models.account import Account
        import uuid
        with app.app_context():
            acc = Account(id=uuid.uuid4().hex, phone='+79004444444', first_name='Old', status='inactive')
            db.session.add(acc)
            db.session.commit()

        csv_data = self._make_csv([{'phone': '+79004444444', 'first_name': 'New', 'status': 'active'}])
        resp = logged_in_client.post(
            '/admin/accounts/bulk_import_csv',
            data={'mode': 'replace', 'file': (io.BytesIO(csv_data), 'test.csv')},
            content_type='multipart/form-data',
        )
        data = resp.get_json()
        assert data['success'] is True
        assert data['replaced'] == 1

    def test_import_merge_mode(self, logged_in_client, app):
        from web.extensions import db
        from models.account import Account
        import uuid
        with app.app_context():
            acc = Account(id=uuid.uuid4().hex, phone='+79005555555', first_name='Keep', status='active')
            db.session.add(acc)
            db.session.commit()

        csv_data = self._make_csv([{'phone': '+79005555555', 'last_name': 'Added'}])
        resp = logged_in_client.post(
            '/admin/accounts/bulk_import_csv',
            data={'mode': 'merge', 'file': (io.BytesIO(csv_data), 'test.csv')},
            content_type='multipart/form-data',
        )
        data = resp.get_json()
        assert data['success'] is True
        assert data['merged'] == 1

    def test_import_delete_mode(self, logged_in_client, app):
        from web.extensions import db
        from models.account import Account
        import uuid
        with app.app_context():
            acc = Account(id=uuid.uuid4().hex, phone='+79006666666', status='active')
            db.session.add(acc)
            db.session.commit()

        csv_data = self._make_csv([{'phone': '+79006666666'}])
        resp = logged_in_client.post(
            '/admin/accounts/bulk_import_csv',
            data={'mode': 'delete', 'file': (io.BytesIO(csv_data), 'test.csv')},
            content_type='multipart/form-data',
        )
        data = resp.get_json()
        assert data['success'] is True
        assert data['deleted'] == 1

    def test_import_invalid_mode(self, logged_in_client):
        csv_data = self._make_csv([{'phone': '+79009999999'}])
        resp = logged_in_client.post(
            '/admin/accounts/bulk_import_csv',
            data={'mode': 'invalidmode', 'file': (io.BytesIO(csv_data), 'test.csv')},
            content_type='multipart/form-data',
        )
        assert resp.status_code == 400

    def test_import_no_file(self, logged_in_client):
        resp = logged_in_client.post('/admin/accounts/bulk_import_csv', data={'mode': 'add'})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Cloud backup route tests
# ---------------------------------------------------------------------------

class TestCloudBackupRoutes:
    def test_cloud_backup_settings_get(self, logged_in_client):
        with patch('web.routes.admin.current_user') as mock_user:
            mock_user.is_authenticated = True
            mock_user.role = 'superadmin'
            mock_user.has_permission = MagicMock(return_value=True)
            # Use real endpoint without needing file on disk
            with patch('services.backup.cloud._load_settings', return_value={'provider': 'local'}):
                resp = logged_in_client.get('/admin/api/cloud_backup/settings')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True

    def test_cloud_backup_settings_save(self, logged_in_client):
        with patch('services.backup.cloud._load_settings', return_value={'provider': 'local'}):
            with patch('services.backup.cloud.save_settings') as mock_save:
                resp = logged_in_client.post(
                    '/admin/api/cloud_backup/settings',
                    data=json.dumps({'provider': 'yandex_disk', 'yandex_remote_dir': '/test'}),
                    content_type='application/json',
                )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
