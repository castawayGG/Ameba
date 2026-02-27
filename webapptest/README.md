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
| `TG_API_ID` / `TG_API_HASH` | From https://my.telegram.org/apps |
| `ADMIN_USERNAME` | Initial admin login |
| `ADMIN_PASSWORD_HASH` | bcrypt hash (see below) |
| `SESSION_ENCRYPTION_KEY` | Fernet key (see below) |

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
│   ├── middlewares/   # Auth, IP whitelist, rate limit
│   └── templates/     # Jinja2 templates
├── models/            # SQLAlchemy models
├── services/          # Business logic (telegram, proxy, backup, export)
├── tasks/             # Celery tasks
├── core/              # Config, database, logger, exceptions
├── utils/             # Encryption, helpers, validators
├── alembic/           # Database migrations
├── nginx/             # Nginx config
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

## Security Notes

- Admin panel is protected by Flask-Login + rate limiting + optional IP whitelist.
- Set `IP_WHITELIST` in `.env` to restrict admin access by IP.
- All Telegram session data is encrypted using Fernet symmetric encryption.
- Nginx passes real client IPs via `X-Real-IP` / `X-Forwarded-For`; the app uses `ProxyFix` to read them correctly.
- Never commit `.env` or any file with real secrets.
