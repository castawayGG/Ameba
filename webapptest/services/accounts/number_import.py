"""
Auto-API Import Connector.

Imports phone numbers / account records from external HTTP sources:
  - Custom JSON API (arbitrary endpoint returning a JSON array or object)
  - Remote CSV/TXT URL (newline-separated phone numbers or CSV)

The connector fetches data, normalises it to a list of phone number strings,
and returns them to the caller.  Creating actual Account rows in the database
is handled by the route layer so that the current_user can be set as owner.
"""

import csv
import io
import re
from typing import Optional

import requests

# ── helpers ──────────────────────────────────────────────────────────────────

_PHONE_RE = re.compile(r'\+?\d[\d\s\-().]{6,19}\d')


def _normalise_phone(raw: str) -> str:
    """Strip non-digit characters except the leading '+', return E.164-ish."""
    cleaned = re.sub(r'[\s\-().]+', '', raw.strip())
    if not cleaned.startswith('+'):
        cleaned = '+' + cleaned.lstrip('+')
    return cleaned


def _extract_phones_from_value(value) -> list[str]:
    """Recursively pull phone-like strings from a JSON value."""
    phones: list[str] = []
    if isinstance(value, str):
        if _PHONE_RE.fullmatch(value.strip()):
            phones.append(_normalise_phone(value))
    elif isinstance(value, (int, float)):
        candidate = str(value)
        if len(candidate) >= 7:
            phones.append(_normalise_phone(candidate))
    elif isinstance(value, dict):
        for field in ('phone', 'phone_number', 'number', 'tel', 'mobile', 'msisdn'):
            if field in value:
                phones.extend(_extract_phones_from_value(value[field]))
                break
    elif isinstance(value, list):
        for item in value:
            phones.extend(_extract_phones_from_value(item))
    return phones


def _navigate_json_path(data, path: str):
    """Walk dot-separated path inside a JSON structure."""
    if not path:
        return data
    for key in path.split('.'):
        if isinstance(data, dict):
            data = data.get(key, [])
        elif isinstance(data, list):
            try:
                data = data[int(key)]
            except (ValueError, IndexError):
                return []
        else:
            return []
    return data


# ── public API ────────────────────────────────────────────────────────────────

SUPPORTED_SOURCE_TYPES = {
    'custom_json': 'Custom JSON API',
    'csv_url': 'Remote CSV / TXT URL',
}


def fetch_numbers(
    url: str,
    source_type: str = 'custom_json',
    auth_header: Optional[str] = None,
    json_path: str = '',
    timeout: int = 30,
) -> tuple[list[str], Optional[str]]:
    """
    Fetch phone numbers from an external source.

    Returns ``(numbers, error_message)``.  On success ``error_message`` is
    ``None``; on failure ``numbers`` is an empty list.

    Parameters
    ----------
    url:
        HTTP(S) URL to fetch.
    source_type:
        One of ``'custom_json'`` or ``'csv_url'``.
    auth_header:
        Value for the ``Authorization`` HTTP header (e.g. ``'Bearer TOKEN'``).
    json_path:
        Dot-separated path to drill into the JSON response before extracting
        phone numbers (e.g. ``'data.items'``).
    timeout:
        Request timeout in seconds.
    """
    headers: dict[str, str] = {}
    if auth_header:
        headers['Authorization'] = auth_header

    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        resp.raise_for_status()
    except requests.exceptions.Timeout:
        return [], 'Превышено время ожидания ответа'
    except requests.exceptions.ConnectionError:
        return [], 'Ошибка соединения с сервером'
    except requests.exceptions.HTTPError as exc:
        return [], f'HTTP ошибка: {exc.response.status_code}'
    except Exception as exc:  # pragma: no cover
        return [], f'Ошибка запроса: {exc}'

    if source_type == 'custom_json':
        try:
            data = resp.json()
        except ValueError:
            return [], 'Ответ сервера не является валидным JSON'
        data = _navigate_json_path(data, json_path)
        phones = _extract_phones_from_value(data)

    elif source_type == 'csv_url':
        text = resp.text
        phones: list[str] = []
        reader = csv.reader(io.StringIO(text))
        for row in reader:
            if not row:
                continue
            candidate = row[0].strip()
            if candidate and _PHONE_RE.fullmatch(candidate):
                phones.append(_normalise_phone(candidate))

    else:
        return [], f'Неизвестный тип источника: {source_type}'

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for p in phones:
        if p not in seen:
            seen.add(p)
            unique.append(p)

    return unique, None
