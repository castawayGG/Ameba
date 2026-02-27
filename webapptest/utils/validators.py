import re
import ipaddress

def is_valid_ip(ip: str) -> bool:
    """Проверяет, является ли строка валидным IP-адресом."""
    try:
        ipaddress.ip_address(ip)
        return True
    except ValueError:
        return False

def is_valid_proxy_string(proxy_str: str) -> bool:
    """
    Проверяет, соответствует ли строка формату прокси:
    [type://][user:pass@]host:port
    """
    pattern = r'^(?:(socks5|socks4|http|https)://)?(?:([^:@]+):([^:@]+)@)?([^:@]+):(\d+)$'
    return re.match(pattern, proxy_str) is not None