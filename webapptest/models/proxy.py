from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from core.database import Base
import re

class Proxy(Base):
    __tablename__ = 'proxies'

    id = Column(Integer, primary_key=True)
    type = Column(String(10), default='socks5')        # socks5, socks4, http, https
    host = Column(String(100), nullable=False)
    port = Column(Integer, nullable=False)
    username = Column(String(100), nullable=True)
    password = Column(String(100), nullable=True)
    name = Column(String(200), nullable=True)          # пользовательское название
    country = Column(String(50), nullable=True)        # страна (можно определить по GeoIP)
    description = Column(Text, nullable=True)

    # Статус и результаты проверок
    status = Column(String(20), default='unknown')     # unknown, working, dead, checking
    enabled = Column(Boolean, default=True)
    speed = Column(Integer, nullable=True)             # последняя скорость в мс
    avg_speed = Column(Float, nullable=True)           # средняя скорость
    last_check = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)

    # Статистика использования
    requests_count = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    fail_count = Column(Integer, default=0)

    created_at = Column(DateTime, server_default=func.now())

    # Связь с аккаунтами, которые используют этот прокси
    accounts = relationship('Account', back_populates='proxy')

    @staticmethod
    def parse_proxy_string(proxy_str: str) -> dict:
        """
        Парсит строку прокси в формате:
          [type://][user:pass@]host:port
        Примеры:
          socks5://user:pass@127.0.0.1:1080
          http://127.0.0.1:8080
          192.168.1.1:3128
        Возвращает словарь с полями type, host, port, username, password или None, если строка невалидна.
        """
        pattern = r'(?:(socks5|socks4|http|https)://)?(?:([^:@]+):([^:@]+)@)?([^:@]+):(\d+)'
        match = re.match(pattern, proxy_str.strip())
        if not match:
            return None
        p_type, p_user, p_pass, p_host, p_port = match.groups()
        return {
            'type': p_type or 'socks5',
            'host': p_host,
            'port': int(p_port),
            'username': p_user,
            'password': p_pass
        }

    def to_telethon_tuple(self):
        """
        Преобразует прокси в кортеж, пригодный для передачи в Telethon.
        Возвращает None, если прокси невалиден или отключён.
        """
        import socks
        if not self.enabled or self.status != 'working':
            return None
        if self.type == 'socks5':
            proxy_type = socks.SOCKS5
        elif self.type == 'socks4':
            proxy_type = socks.SOCKS4
        else:
            proxy_type = socks.HTTP
        if self.username and self.password:
            return (proxy_type, self.host, self.port, True, self.username, self.password)
        return (proxy_type, self.host, self.port, False)

    def __repr__(self):
        return f"<Proxy {self.host}:{self.port}>"