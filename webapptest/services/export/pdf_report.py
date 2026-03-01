"""
Генерация PDF-отчётов о состоянии системы.

Блок 7: Интеграции и уведомления.
Создаёт PDF/HTML-отчёты по аккаунтам, кампаниям, парсингу.
"""
import io
import html as _html_mod
import datetime
from typing import Optional
from core.logger import log


def generate_summary_report(stats: dict) -> bytes:
    """
    Генерирует HTML-отчёт о состоянии системы.
    Возвращает HTML-байты (можно конвертировать в PDF через браузер).
    
    :param stats: Словарь со статистикой системы
    :return: Байты HTML-документа
    """
    now = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    
    accounts = stats.get('accounts', {})
    campaigns = stats.get('campaigns', {})
    proxies = stats.get('proxies', {})
    
    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<title>Ameba — Отчёт системы {now}</title>
<style>
  body {{ font-family: Arial, sans-serif; margin: 40px; color: #333; }}
  h1 {{ color: #1a73e8; }}
  h2 {{ color: #444; border-bottom: 1px solid #ddd; padding-bottom: 4px; }}
  table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }}
  th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: left; }}
  th {{ background: #1a73e8; color: #fff; }}
  tr:nth-child(even) {{ background: #f5f5f5; }}
  .metric {{ display: inline-block; margin: 8px 16px 8px 0; padding: 10px 20px;
             background: #e8f0fe; border-radius: 8px; }}
  .metric span {{ font-size: 24px; font-weight: bold; color: #1a73e8; display: block; }}
  footer {{ margin-top: 40px; color: #888; font-size: 12px; }}
</style>
</head>
<body>
<h1>📊 Отчёт системы Ameba</h1>
<p>Дата генерации: <strong>{now}</strong></p>

<h2>Аккаунты</h2>
<div>
  <div class="metric">Всего<span>{accounts.get('total', 0)}</span></div>
  <div class="metric">Активных<span>{accounts.get('active', 0)}</span></div>
  <div class="metric">Заблокированных<span>{accounts.get('banned', 0)}</span></div>
  <div class="metric">Flood wait<span>{accounts.get('flood_wait', 0)}</span></div>
</div>

<h2>Кампании</h2>
<div>
  <div class="metric">Всего<span>{campaigns.get('total', 0)}</span></div>
  <div class="metric">Активных<span>{campaigns.get('active', 0)}</span></div>
  <div class="metric">Завершённых<span>{campaigns.get('done', 0)}</span></div>
</div>

<h2>Прокси</h2>
<div>
  <div class="metric">Всего<span>{proxies.get('total', 0)}</span></div>
  <div class="metric">Рабочих<span>{proxies.get('working', 0)}</span></div>
  <div class="metric">Недоступных<span>{proxies.get('dead', 0)}</span></div>
</div>
"""
    
    # Детализация аккаунтов
    account_rows = stats.get('account_rows', [])
    if account_rows:
        html += """
<h2>Детализация аккаунтов (топ 50)</h2>
<table>
<tr><th>Phone</th><th>Username</th><th>Status</th><th>Last Active</th></tr>
"""
        for a in account_rows[:50]:
            html += (
                f"<tr>"
                f"<td>{_html_mod.escape(a.get('phone',''))}</td>"
                f"<td>{_html_mod.escape(a.get('username',''))}</td>"
                f"<td>{_html_mod.escape(a.get('status',''))}</td>"
                f"<td>{_html_mod.escape(a.get('last_active',''))}</td>"
                f"</tr>\n"
            )
        html += "</table>\n"
    
    html += f"""
<footer>Сгенерировано системой Ameba | {now}</footer>
</body>
</html>"""
    
    return html.encode('utf-8')


def collect_report_stats() -> dict:
    """
    Собирает статистику для отчёта из базы данных.
    
    :return: Словарь со статистикой
    """
    try:
        from core.database import SessionLocal
        from models.account import Account
        from models.campaign import Campaign
        from models.proxy import Proxy
        from sqlalchemy import func
        
        db = SessionLocal()
        try:
            # Аккаунты
            acc_counts = {}
            for status in ['active', 'banned', 'flood_wait', 'inactive']:
                acc_counts[status] = db.query(func.count(Account.id)).filter(Account.status == status).scalar() or 0
            acc_counts['total'] = db.query(func.count(Account.id)).scalar() or 0
            
            # Кампании
            camp_counts = {
                'total': db.query(func.count(Campaign.id)).scalar() or 0,
                'active': db.query(func.count(Campaign.id)).filter(Campaign.status == 'active').scalar() or 0,
                'done': db.query(func.count(Campaign.id)).filter(Campaign.status == 'done').scalar() or 0,
            }
            
            # Прокси
            proxy_counts = {
                'total': db.query(func.count(Proxy.id)).scalar() or 0,
                'working': db.query(func.count(Proxy.id)).filter(Proxy.status == 'working').scalar() or 0,
                'dead': db.query(func.count(Proxy.id)).filter(Proxy.status == 'dead').scalar() or 0,
            }
            
            # Топ аккаунты
            accounts = db.query(Account).order_by(Account.created_at.desc()).limit(50).all()
            account_rows = [{
                'phone': a.phone,
                'username': a.username or '',
                'status': a.status,
                'last_active': a.last_active.strftime('%Y-%m-%d') if a.last_active else '',
            } for a in accounts]
            
            return {
                'accounts': acc_counts,
                'campaigns': camp_counts,
                'proxies': proxy_counts,
                'account_rows': account_rows,
            }
        finally:
            db.close()
    except Exception as e:
        log.error(f"collect_report_stats error: {e}")
        return {'accounts': {}, 'campaigns': {}, 'proxies': {}}
