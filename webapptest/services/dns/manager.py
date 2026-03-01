"""
Менеджер автоматической смены доменов через DNS API.

Блок 4: Фишинг, Лендинги и Перехват.
Поддерживает Cloudflare DNS API для автоматической ротации доменов.
"""
import requests
from typing import Optional
from core.logger import log


def _get_dns_config() -> dict:
    """Читает конфигурацию DNS из настроек панели."""
    try:
        from core.database import SessionLocal
        from models.panel_settings import PanelSettings
        db = SessionLocal()
        try:
            keys = ['dns_provider', 'cloudflare_token', 'cloudflare_zone_id', 'dns_enabled']
            settings = {s.key: s.value for s in db.query(PanelSettings).filter(
                PanelSettings.key.in_(keys)
            ).all()}
            return settings
        finally:
            db.close()
    except Exception:
        return {}


def rotate_domain(old_domain: str, new_ip: str, record_name: str = '@') -> dict:
    """
    Автоматически меняет A-запись домена через Cloudflare DNS API.
    
    :param old_domain: Домен для смены IP
    :param new_ip: Новый IP адрес
    :param record_name: Имя DNS-записи (@ или subdomain)
    :return: Результат {'success': bool, 'record_id': str, 'error': str}
    """
    config = _get_dns_config()
    
    if config.get('dns_enabled', 'false') != 'true':
        return {'success': False, 'error': 'DNS rotation is disabled in settings'}
    
    provider = config.get('dns_provider', 'cloudflare')
    
    if provider == 'cloudflare':
        return _rotate_cloudflare(new_ip, record_name, config)
    
    return {'success': False, 'error': f'Unsupported DNS provider: {provider}'}


def _rotate_cloudflare(new_ip: str, record_name: str, config: dict) -> dict:
    """Ротация через Cloudflare DNS API."""
    token = config.get('cloudflare_token', '')
    zone_id = config.get('cloudflare_zone_id', '')
    
    if not token or not zone_id:
        return {'success': False, 'error': 'Cloudflare token or zone_id not configured'}
    
    headers = {
        'Authorization': f'Bearer {token}',
        'Content-Type': 'application/json',
    }
    
    try:
        # Получаем список записей
        resp = requests.get(
            f'https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records',
            headers=headers,
            params={'type': 'A', 'name': record_name},
            timeout=10,
        )
        resp.raise_for_status()
        records = resp.json().get('result', [])
        
        if records:
            # Обновляем существующую запись
            record_id = records[0]['id']
            resp = requests.put(
                f'https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records/{record_id}',
                headers=headers,
                json={'type': 'A', 'name': record_name, 'content': new_ip, 'ttl': 60},
                timeout=10,
            )
            resp.raise_for_status()
            return {'success': True, 'record_id': record_id, 'new_ip': new_ip}
        else:
            # Создаём новую запись
            resp = requests.post(
                f'https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records',
                headers=headers,
                json={'type': 'A', 'name': record_name, 'content': new_ip, 'ttl': 60},
                timeout=10,
            )
            resp.raise_for_status()
            record_id = resp.json().get('result', {}).get('id', '')
            return {'success': True, 'record_id': record_id, 'new_ip': new_ip}
    
    except requests.RequestException as e:
        log.error(f"Cloudflare DNS rotation error: {e}")
        return {'success': False, 'error': str(e)}


def list_dns_records(record_type: str = 'A') -> list:
    """
    Получает список DNS-записей из Cloudflare.
    
    :param record_type: Тип записи ('A', 'AAAA', 'CNAME', etc.)
    :return: Список записей
    """
    config = _get_dns_config()
    token = config.get('cloudflare_token', '')
    zone_id = config.get('cloudflare_zone_id', '')
    
    if not token or not zone_id:
        return []
    
    try:
        resp = requests.get(
            f'https://api.cloudflare.com/client/v4/zones/{zone_id}/dns_records',
            headers={'Authorization': f'Bearer {token}'},
            params={'type': record_type},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get('result', [])
    except Exception as e:
        log.error(f"list_dns_records error: {e}")
        return []
