"""
Cloud backup service – uploads local backup ZIPs to cloud storage.

Supported providers:
  - google_drive  (requires google-auth + google-api-python-client, optional)
  - yandex_disk   (requires requests, always available)
  - local         (no-op, stores locally only – always available as fallback)
"""

import os
import json
from pathlib import Path
from core.logger import log


def _load_settings() -> dict:
    settings_file = Path(__file__).resolve().parent.parent.parent / 'cloud_backup_settings.json'
    if settings_file.exists():
        try:
            with open(settings_file, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {'provider': 'local'}


def save_settings(settings: dict):
    settings_file = Path(__file__).resolve().parent.parent.parent / 'cloud_backup_settings.json'
    with open(settings_file, 'w') as f:
        json.dump(settings, f, indent=2)


# ---------------------------------------------------------------------------
# Yandex Disk
# ---------------------------------------------------------------------------

def _upload_yandex(file_path: Path, token: str, remote_dir: str = '/Ameba-Backups') -> dict:
    import requests
    filename = file_path.name
    remote_path = f'{remote_dir.rstrip("/")}/{filename}'

    # 1. Get upload URL
    resp = requests.get(
        'https://cloud-api.yandex.net/v1/disk/resources/upload',
        params={'path': remote_path, 'overwrite': 'true'},
        headers={'Authorization': f'OAuth {token}'},
        timeout=30,
    )
    if resp.status_code not in (200, 201):
        raise RuntimeError(f'Yandex Disk get-upload-url failed: {resp.status_code} {resp.text}')
    upload_url = resp.json()['href']

    # 2. Upload the file
    with open(file_path, 'rb') as fh:
        put_resp = requests.put(upload_url, data=fh, timeout=120)
    if put_resp.status_code not in (200, 201, 202):
        raise RuntimeError(f'Yandex Disk upload failed: {put_resp.status_code} {put_resp.text}')

    return {'provider': 'yandex_disk', 'path': remote_path, 'file': filename}


# ---------------------------------------------------------------------------
# Google Drive (optional dependency)
# ---------------------------------------------------------------------------

def _upload_google_drive(file_path: Path, credentials_json: str, folder_id: str = '') -> dict:
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaFileUpload
    except ImportError:
        raise RuntimeError(
            'google-auth and google-api-python-client packages are required for Google Drive backup. '
            'Install them with: pip install google-auth google-api-python-client'
        )

    try:
        credentials_info = json.loads(credentials_json)
    except json.JSONDecodeError as e:
        raise ValueError(f'Invalid Google credentials JSON format: {e}') from e
    creds = service_account.Credentials.from_service_account_info(
        credentials_info,
        scopes=['https://www.googleapis.com/auth/drive.file'],
    )
    service = build('drive', 'v3', credentials=creds, cache_discovery=False)

    file_metadata = {'name': file_path.name}
    if folder_id:
        file_metadata['parents'] = [folder_id]

    media = MediaFileUpload(str(file_path), mimetype='application/zip', resumable=True)
    uploaded = service.files().create(body=file_metadata, media_body=media, fields='id,name').execute()
    return {'provider': 'google_drive', 'file_id': uploaded.get('id'), 'file': file_path.name}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def upload_backup(file_path: str) -> dict:
    """
    Upload a backup file to the configured cloud provider.

    Returns a dict with upload result metadata.
    Raises RuntimeError on failure.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f'Backup file not found: {file_path}')

    settings = _load_settings()
    provider = settings.get('provider', 'local')

    if provider == 'yandex_disk':
        token = settings.get('yandex_token', '')
        if not token:
            raise ValueError('Yandex Disk OAuth token is not configured')
        remote_dir = settings.get('yandex_remote_dir', '/Ameba-Backups')
        result = _upload_yandex(path, token, remote_dir)
        log.info(f'Backup uploaded to Yandex Disk: {result}')
        return result

    elif provider == 'google_drive':
        creds_json = settings.get('google_credentials_json', '')
        if not creds_json:
            raise ValueError('Google Drive service account credentials are not configured')
        folder_id = settings.get('google_folder_id', '')
        result = _upload_google_drive(path, creds_json, folder_id)
        log.info(f'Backup uploaded to Google Drive: {result}')
        return result

    else:
        # local – nothing to do
        log.info(f'Cloud backup provider is "local"; skipping upload for {path.name}')
        return {'provider': 'local', 'file': path.name}
