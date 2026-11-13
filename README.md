# Agricultural E-commerce Platform

A Django-based marketplace for agricultural products. Farmers upload produce listings. Buyers browse listings and open a chat with the farmer to negotiate.

## Features

- Email and Google login
- Farmer listings with photos, price, unit, quantity, and location
- Browse and search listings
- Real-time buyer/farmer chat, one thread per buyer per listing
- Individual analytics (listing views, inquiries, price vs market)
- Site-wide analytics (average asking price per produce type over time)
- Email and SMS notifications

## Stack

| Layer | Choice | Reason |
| --- | --- | --- |
| Backend | Django + Django Channels | Channels adds WebSocket support to Django. |
| Database | Supabase Postgres | Managed Postgres only. Django owns the schema through migrations. |
| Auth | django-allauth | Google OAuth and email login in one package. |
| Realtime chat | Channels + Redis | Messages persist in Postgres. Redis routes live traffic. |
| Background jobs | Celery + Redis | Email/SMS sending must never block a request. |
| Email | Resend, Brevo, or Amazon SES | Transactional email over API. |
| SMS (PH) | Semaphore or Twilio | Local providers cost less for PH numbers. |
| Frontend | Tailwind + HTMX + Alpine.js | No separate SPA. |
| Media | Supabase Storage via django-storages (S3 protocol) | Listing photos stay off the app server. |
| Search | Postgres full-text + `pg_trgm` | Sufficient for listings. |
| Charts | Chart.js | Renders analytics from JSON endpoints. |
| Hosting | Render, Railway, or Fly.io | Must support long-lived ASGI processes. Serverless breaks WebSockets. |

Decisions:

- Supabase Auth is not used. Django auth is the single identity system.
- Supabase Realtime is not used. It authorizes against Supabase JWTs, while users hold Django sessions.
- PostGIS (farms within X km) is deferred. It needs GDAL locally and `django.contrib.gis`.

## Prerequisites

- Python 3.14 or a compatible version supported by the pinned Django release
- `pip` and `venv` (bundled with Python)
- Git
- A Supabase project (Postgres database and Storage bucket)
- Redis (local: `docker run -p 6379:6379 redis` or `brew install redis`)

## Installation

1. Clone the repository.

   ```bash
   git clone <repository-url>
   cd Agricultural-Ecommerce-Platform
   ```

2. Create and activate a virtual environment.

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate        # macOS / Linux
   .venv\Scripts\activate           # Windows
   ```

3. Install dependencies.

   ```bash
   pip install -r requirements.txt
   ```

4. Create the environment file (see [Environment Variables](#environment-variables)).

### First-time project bootstrap

Skip this if the repository already has `requirements.txt` and the apps below.

```bash
pip install django "channels[daphne]" channels-redis django-allauth \
  dj-database-url "psycopg[binary]" celery redis django-storages boto3 \
  python-dotenv pillow whitenoise
pip freeze > requirements.txt

django-admin startproject config .
python manage.py startapp accounts
python manage.py startapp listings
python manage.py startapp chat
python manage.py startapp analytics
python manage.py startapp notifications
```

Quote `"psycopg[binary]"` and `"channels[daphne]"`. zsh reads square brackets as a glob pattern and aborts with `no matches found`.

One app per feature. Each app is tested and reasoned about on its own.

## Environment Variables

Configuration is read from environment variables. Create a `.env` file in the project root. Never commit it.

```env
SECRET_KEY=
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Supabase Postgres
DATABASE_URL=postgres://USER:PASSWORD@HOST:6543/postgres   # transaction pooler, runtime
DIRECT_URL=postgres://USER:PASSWORD@HOST:5432/postgres     # session pooler or direct, migrations

# Redis (Channels + Celery)
REDIS_URL=redis://127.0.0.1:6379/0

# Google OAuth
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

# Email
EMAIL_HOST=
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
DEFAULT_FROM_EMAIL=

# SMS
SMS_API_KEY=

# Supabase Storage (S3 protocol)
SUPABASE_S3_ENDPOINT=https://<project-ref>.supabase.co/storage/v1/s3
SUPABASE_S3_ACCESS_KEY=
SUPABASE_S3_SECRET_KEY=
SUPABASE_BUCKET=listings
```

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Django cryptographic signing key. |
| `DEBUG` | `True` for development, `False` for production. |
| `ALLOWED_HOSTS` | Comma-separated hostnames Django will serve. |
| `DATABASE_URL` | Runtime database connection (Supabase transaction pooler, port 6543). |
| `DIRECT_URL` | Connection used for `migrate` (Supabase session pooler or direct, port 5432). |
| `REDIS_URL` | Channel layer and Celery broker. |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google OAuth credentials. |
| `EMAIL_*`, `DEFAULT_FROM_EMAIL` | Email provider SMTP credentials. |
| `SMS_API_KEY` | SMS provider key. |
| `SUPABASE_S3_*`, `SUPABASE_BUCKET` | Media storage credentials (Supabase dashboard, Storage, S3 connection). |

Local SQLite works for early development:

```env
DATABASE_URL=sqlite:///db.sqlite3
```

If `DATABASE_URL` is missing, the app logs `No DATABASE_URL environment variable set, and so no databases setup` and database commands fail. Set it before running `migrate`.

Generate a secret key:

```bash
python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
```

## Settings Overview

Relevant parts of `config/settings.py`.

```python
import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = os.environ["SECRET_KEY"]
DEBUG = os.getenv("DEBUG", "False") == "True"
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "").split(",")

INSTALLED_APPS = [
    "daphne",                      # must be first: makes runserver ASGI-aware
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",        # required by allauth
    "django.contrib.postgres",     # trigram search
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "accounts", "listings", "chat", "analytics", "notifications",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

AUTH_USER_MODEL = "accounts.User"   # define before the first migration
SITE_ID = 1
```

Custom user model: define `class User(AbstractUser): pass` in `accounts/models.py` before the first `migrate`. Changing `AUTH_USER_MODEL` after tables exist is painful.

### Database (Supabase)

```python
DATABASES = {
    "default": dj_database_url.config(env="DATABASE_URL", conn_max_age=0, ssl_require=not DEBUG)
}
DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True  # required for the transaction pooler
```

- Transaction pooler (port 6543) does not support server-side cursors. Runtime uses it.
- Migrations use `DIRECT_URL`.
- `conn_max_age=0` because the pooler already manages connections.
- If `DATABASE_URL` is SQLite, `ssl_require` must stay off. The `not DEBUG` guard covers local development, so use SQLite only with `DEBUG=True`.

### Auth (django-allauth)

```python
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
LOGIN_REDIRECT_URL = "/"

SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "APP": {
            "client_id": os.getenv("GOOGLE_CLIENT_ID"),
            "secret": os.getenv("GOOGLE_CLIENT_SECRET"),
        },
        "SCOPE": ["profile", "email"],
    }
}
```

`config/urls.py`:

```python
path("accounts/", include("allauth.urls")),
```

Google Cloud Console, OAuth client, authorized redirect URIs:

```
http://127.0.0.1:8000/accounts/google/login/callback/
https://<production-domain>/accounts/google/login/callback/
```

### Channels and Redis

```python
ASGI_APPLICATION = "config.asgi.application"

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")]},
    }
}
```

`config/asgi.py`:

```python
import os
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django_asgi = get_asgi_application()   # must run before importing routing

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.security.websocket import AllowedHostsOriginValidator
import chat.routing

application = ProtocolTypeRouter({
    "http": django_asgi,
    "websocket": AllowedHostsOriginValidator(
        AuthMiddlewareStack(URLRouter(chat.routing.websocket_urlpatterns))
    ),
})
```

### Celery

`config/celery.py`:

```python
import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
```

`config/__init__.py`:

```python
from .celery import app as celery_app
__all__ = ("celery_app",)
```

`settings.py`:

```python
CELERY_BROKER_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
```

### Media (Supabase Storage)

```python
STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": os.getenv("SUPABASE_BUCKET"),
            "endpoint_url": os.getenv("SUPABASE_S3_ENDPOINT"),
            "access_key": os.getenv("SUPABASE_S3_ACCESS_KEY"),
            "secret_key": os.getenv("SUPABASE_S3_SECRET_KEY"),
            "region_name": "ap-southeast-1",   # match your Supabase project region
        },
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}
```

## Database Setup

Run migrations against the direct/session connection, not the transaction pooler:

```bash
DATABASE_URL="$DIRECT_URL" python manage.py migrate
python manage.py createsuperuser
```

`migrate` builds the tables. `createsuperuser` creates an account for the admin site at `/admin/`.

Enable trigram search in the first `listings` migration:

```python
from django.contrib.postgres.operations import TrigramExtension

class Migration(migrations.Migration):
    operations = [TrigramExtension(), ...]
```

## Data Model

| Model | Fields |
| --- | --- |
| `Profile` | One-to-one with User. Role (farmer/buyer), phone, location, notification preferences. |
| `Category` | Produce type (rice, tomato, and so on). |
| `Listing` | Farmer FK, category FK, price per unit, unit (kg/sack), quantity, location, status, timestamps. |
| `Conversation` | Listing FK, buyer FK, farmer FK. Unique on `(listing, buyer)`. |
| `Message` | Conversation FK, sender FK, body, `created_at`, `read_at`. |
| `Notification` | User FK, type, payload, channel, `sent_at`. |
| `ListingView` | Listing FK, timestamp, anonymous hash. Append-only. |
| `PriceSnapshot` | Category, date, avg/min/max price, listing count. Filled by Celery beat. |

Indexes: `Message(conversation, created_at)` and `Listing(category, status, created_at)`.

Normalize units (kg vs sack) at write time. Averages across mixed units are meaningless.

## Chat Architecture

Django views are a post office: one letter in, one reply out. Channels is a switchboard: connections stay open, and Redis is the exchange wiring callers into the same room.

Flow:

1. Browser opens `ws://<host>/ws/chat/<conversation_id>/`.
2. Consumer checks the user is the buyer or farmer of that conversation. Reject otherwise. This is the authorization boundary.
3. Consumer joins group `chat_<id>`.
4. On receive: save the `Message` to Postgres first, then broadcast to the group.
5. If the recipient has no active socket, enqueue a Celery notification task.

Server-side requirements: cap message length, rate-limit per user, paginate history by `created_at` cursor.

## Analytics

- Individual (farmer dashboard): listing views, inquiries started, response time, price vs market average.
- Site-wide: ORM aggregates grouped by category and time bucket, precomputed into `PriceSnapshot` and cached.
- Listing prices are asking prices, not transaction prices. Label them as such in the UI.

## Notifications

Never send inside the request cycle.

1. Event occurs.
2. Create a `Notification` row.
3. Enqueue a Celery task.
4. Task dispatches to email and/or SMS per user preferences.

Debounce chat notifications (one per conversation per N minutes). SMS is opt-in and reserved for high-value events, since each send costs money.

## Running the Project

Three processes. Run each in its own terminal.

```bash
# 1. Redis
docker run -p 6379:6379 redis

# 2. Web (ASGI, WebSockets included)
python manage.py runserver

# 3. Background worker
celery -A config worker -l info
```

Open `http://127.0.0.1:8000/`.

Validate configuration at any time without starting the server:

```bash
python manage.py check
```

## Static Files

Relevant settings in `settings.py`:

```python
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
```

- `STATICFILES_DIRS` is the input: folders Django reads source files from.
- `STATIC_ROOT` is the output: the folder `collectstatic` writes to for deployment.
- The two must be different folders. Using the same folder raises `staticfiles.E002`.

Collect files for deployment:

```bash
python manage.py collectstatic
```

Reference static files in templates:

```django-html
{% load static %}
<link href="{% static 'css/style.css' %}" rel="stylesheet">
```

`{% load static %}` is required in every template that uses `{% static %}`.

## Templates

All pages extend a shared layout at `templates/base.html`.

Parent (`templates/base.html`):

```django-html
{% load static %}
<!doctype html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{% block title %}Agricultural Ecommerce Platform{% endblock %}</title>
  <link href="{% static 'css/style.css' %}" rel="stylesheet">
  {% block extra_head %}{% endblock %}
</head>
<body>
  {% block content %}{% endblock %}
  {% block extra_js %}{% endblock %}
</body>
</html>
```

Child page:

```django-html
{% extends "base.html" %}

{% block title %}Products{% endblock %}

{% block content %}
  <h1>Products</h1>
{% endblock %}
```

Rules:

- `{% extends %}` must be the first tag in the child template.
- Content outside blocks in a child template is discarded.
- Add `BASE_DIR / "templates"` to `TEMPLATES[0]["DIRS"]` in `settings.py` so Django finds the shared folder.

## Testing

```bash
python manage.py test
```

Django's built-in test runner. For WebSocket consumers, override the channel layer with the in-memory backend so tests do not need Redis:

```python
@override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
```

## Build Order

Each step depends on the previous one.

1. Auth (allauth, custom user, profile)
2. Listings CRUD
3. Browse and search
4. Chat
5. Notifications
6. Analytics

## Deployment

Pre-deployment checklist:

- `DEBUG=False`
- `SECRET_KEY` set to a unique value from the environment
- `ALLOWED_HOSTS` set to the production domain
- `DATABASE_URL` pointing to the Supabase transaction pooler
- `REDIS_URL` pointing to a managed Redis instance
- `python manage.py collectstatic` executed
- `DATABASE_URL="$DIRECT_URL" python manage.py migrate` executed
- HTTPS enabled (required for secure WebSockets, `wss://`)
- `python manage.py check --deploy` reports no critical issues

Hosting: Render, Railway, or Fly.io. Deploy two processes from the same codebase:

```bash
daphne -b 0.0.0.0 -p $PORT config.asgi:application   # web
celery -A config worker -l info                      # worker
```

Run ASGI (Daphne or Uvicorn) in production. WSGI-only servers (plain gunicorn) cannot serve WebSockets. Vercel and other serverless platforms break long-lived connections.

Static files in production are served by [WhiteNoise](https://whitenoise.readthedocs.io/).

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `zsh: no matches found: psycopg[binary]` | zsh glob expansion of `[...]` | Quote the package: `"psycopg[binary]"`. |
| `No DATABASE_URL environment variable set` | Variable missing from the environment | Add it to `.env` and confirm `settings.py` calls `load_dotenv`. |
| `staticfiles.E002` | `STATIC_ROOT` equals or sits inside a `STATICFILES_DIRS` entry | Point `STATIC_ROOT` to a separate folder such as `staticfiles/`. |
| `ModuleNotFoundError: No module named '<app>'` | App listed in `INSTALLED_APPS` but the folder does not exist | Create the app or remove the entry. |
| Page renders without styles | Wrong stylesheet path or missing file | Use `{% static %}` and confirm the file exists under `static/`. |
| `TemplateDoesNotExist: base.html` | Templates folder not registered | Add it to `TEMPLATES[0]["DIRS"]`. |
| `InvalidCursorName` or cursor errors on Supabase | Server-side cursors through the transaction pooler | Set `DISABLE_SERVER_SIDE_CURSORS = True`. |
| Migration hangs or fails on Supabase | Running `migrate` through the transaction pooler | Use `DIRECT_URL` for migrations. |
| WebSocket connects then closes immediately | Authorization check failed or origin rejected | Check the user is a conversation participant and the host is in `ALLOWED_HOSTS`. |
| `redirect_uri_mismatch` on Google login | Callback URL not registered | Add the exact `/accounts/google/login/callback/` URL in Google Cloud Console. |