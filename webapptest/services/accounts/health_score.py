"""Health score calculator for Telegram accounts."""
from datetime import datetime, timezone, timedelta


def calculate_health_score(account) -> int:
    """
    Calculate a 0-100 health score for an account based on multiple factors.
    Returns an integer score.
    """
    score = 50  # base score

    now = datetime.now(timezone.utc)

    # Session age: older sessions are more trusted (+up to 15 points)
    if account.created_at:
        created = account.created_at if account.created_at.tzinfo else account.created_at.replace(tzinfo=timezone.utc)
        age_days = (now - created).days
        if age_days > 180:
            score += 15
        elif age_days > 30:
            score += 10
        elif age_days > 7:
            score += 5

    # Flood wait: penalize accounts currently in flood wait (-20)
    if account.flood_wait_until:
        fw = account.flood_wait_until
        if fw.tzinfo is None:
            fw = fw.replace(tzinfo=timezone.utc)
        if fw > now:
            score -= 20

    # Status: banned/dead accounts get heavy penalty
    if account.status == 'banned':
        score -= 40
    elif account.status == 'dead':
        score -= 30
    elif account.status == 'inactive':
        score -= 10
    elif account.status == 'active':
        score += 5

    # Profile completeness (+up to 15 points)
    completeness = 0
    if account.first_name:
        completeness += 5
    if account.username:
        completeness += 5
    if account.session_data or account.session_file:
        completeness += 5
    score += completeness

    # Premium accounts are more trusted (+5)
    if account.premium:
        score += 5

    # Recent activity: accounts active in the last 24h get a boost
    if account.last_active:
        la = account.last_active
        if la.tzinfo is None:
            la = la.replace(tzinfo=timezone.utc)
        hours_since = (now - la).total_seconds() / 3600
        if hours_since < 24:
            score += 10
        elif hours_since < 168:  # 7 days
            score += 5

    # Warming status
    if account.warming_status == 'warmed':
        score += 10
    elif account.warming_status == 'warming':
        score += 3

    return max(0, min(100, score))


def get_health_color(score: int) -> str:
    """Return a color class based on health score."""
    if score >= 80:
        return 'green'
    elif score >= 50:
        return 'yellow'
    elif score >= 20:
        return 'orange'
    else:
        return 'red'


def get_health_emoji(score: int) -> str:
    """Return an emoji based on health score."""
    if score >= 80:
        return '🟢'
    elif score >= 50:
        return '🟡'
    elif score >= 20:
        return '🟠'
    else:
        return '🔴'
