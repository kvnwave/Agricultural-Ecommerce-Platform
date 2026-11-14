# Agricultural E-commerce Platform

A Django-based marketplace for agricultural products. Farmers upload produce listings. Buyers browse listings and open a chat with the farmer to negotiate.

## Features

- Email and Google login, with Google or uploaded profile photos
- Farmer listings with photos, price, unit, quantity, and location
- Browse, search, and filter listings; save liked listings
- Sold-out status with an optional restock note
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
# Public HTTPS origin(s), comma-separated, e.g. https://market.example.com
CSRF_TRUSTED_ORIGINS=

# Supabase Postgres
DATABASE_URL=postgres://USER:PASSWORD@HOST:6543/postgres   # transaction pooler, runtime
DIRECT_URL=postgres://USER:PASSWORD@HOST:5432/postgres     # session pooler or direct, migrations
# Set True for Supabase; empty defaults to requiring TLS outside DEBUG.
DB_SSL_REQUIRE=

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
SUPABASE_S3_REGION=ap-southeast-1
SUPABASE_BUCKET=listings
# Leave empty for a public bucket. Set True for expiring signed URLs.
SUPABASE_S3_QUERYSTRING_AUTH=
# Optional; defaults to <project>.supabase.co/storage/v1/object/public/<bucket>
SUPABASE_S3_CUSTOM_DOMAIN=
```

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Django cryptographic signing key. |
| `DEBUG` | `True` for development, `False` for production. |
| `ALLOWED_HOSTS` | Comma-separated hostnames Django will serve. |
| `CSRF_TRUSTED_ORIGINS` | Comma-separated public HTTPS origins allowed to submit forms. |
| `DATABASE_URL` | Runtime database connection (Supabase transaction pooler, port 6543). |
| `DIRECT_URL` | Connection used for `migrate` (Supabase session pooler or direct, port 5432). |
| `DB_SSL_REQUIRE` | Force TLS for remote databases. Empty defaults to `not DEBUG`. |
| `REDIS_URL` | Channel layer and Celery broker. |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | Google OAuth credentials. Both are required before the button appears. |
| `EMAIL_*`, `DEFAULT_FROM_EMAIL` | Email provider SMTP credentials. |
| `SMS_API_KEY` | SMS provider key. |
| `SUPABASE_S3_*`, `SUPABASE_S3_REGION`, `SUPABASE_BUCKET` | Media storage credentials and bucket region (Supabase dashboard, Storage, S3 connection). |
| `SUPABASE_S3_QUERYSTRING_AUTH` | Empty/False for a public bucket; `True` for expiring signed URLs on a private bucket. |
| `SUPABASE_S3_CUSTOM_DOMAIN` | Optional public URL base. Defaults to the Supabase `object/public/<bucket>` path. |

Local SQLite works for early development:

```env
DATABASE_URL=sqlite:///db.sqlite3
DIRECT_URL=sqlite:///db.sqlite3
DB_SSL_REQUIRE=
```

SQLite ignores `DB_SSL_REQUIRE`; TLS is only applied to remote database URLs.

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
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",        # required by allauth
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
    "accounts", "listings", "chat", "analytics", "notifications",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
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

The custom user model must exist before the first `migrate`. Changing `AUTH_USER_MODEL` after auth tables exist is painful. `accounts.User` keeps Django's username for admin compatibility; email is the unique login identifier.

### Database (Supabase)

```python
DATABASE_URL = os.getenv("DATABASE_URL", "")

# Empty values fall back to requiring TLS outside DEBUG.
DB_SSL_REQUIRE = os.getenv("DB_SSL_REQUIRE") or str(not DEBUG)
DB_SSL_REQUIRE = DB_SSL_REQUIRE.lower() in {"1", "true", "yes"}

DATABASES = {
    "default": dj_database_url.config(
        env="DATABASE_URL",
        conn_max_age=0,
        # SQLite rejects Postgres sslmode; only remote databases use TLS.
        ssl_require=DB_SSL_REQUIRE and not DATABASE_URL.startswith("sqlite"),
    )
}
DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True
```

- Transaction pooler (port 6543) does not support server-side cursors. Runtime uses it.
- Migrations use `DIRECT_URL`, because DDL and long transactions should not go through the transaction pooler.
- `conn_max_age=0` because the pooler already manages connections.
- `DB_SSL_REQUIRE` defaults to `not DEBUG`; set it explicitly for Supabase.
- Local SQLite stays unaffected because the TLS option is skipped for `sqlite://` URLs.

#### Supabase Data API security

Django connects straight to Postgres, so this project does not use Supabase's Data API. Supabase projects can still grant `anon` and `authenticated` roles access to new tables in `public`, which would expose `accounts_user` — including emails and password hashes — through the project's anon key.

Choose one:

- Disable the Data API in **Project Settings → API**, or
- Revoke the default `anon` / `authenticated` grants on `public`, and enable RLS with no policies for Django-owned tables.

Django's direct connection runs as the table owner and is not subject to RLS. RLS protects the Data API; it does not replace Django authentication.

Never put the Supabase `service_role` key in Django. The Postgres connection string and Storage S3 credentials are all the app needs.

### Auth (django-allauth)

Django and django-allauth are the single identity system. Supabase Auth is not used. `accounts.User` extends `AbstractUser`: username stays for Django admin compatibility, while email is unique and is the login identifier. A `post_save` signal creates `Profile` for email signups, Google signups, admin-created users, and tests.

```python
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_FORMS = {"signup": "accounts.forms.SignupForm"}
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
LOGIN_REDIRECT_URL = "/listings/"

SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True
SOCIALACCOUNT_AUTO_SIGNUP = False
SOCIALACCOUNT_FORMS = {"signup": "accounts.forms.SocialSignupForm"}

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")

SOCIALACCOUNT_PROVIDERS = {}
if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
    SOCIALACCOUNT_PROVIDERS["google"] = {
        "APP": {
            "client_id": GOOGLE_CLIENT_ID,
            "secret": GOOGLE_CLIENT_SECRET,
        },
        "SCOPE": ["profile", "email"],
    }
```

- Signup collects email and password plus the account type (buyer or farmer). Only farmer accounts can create listings; buyers can browse and save listings.
- Social signup never defaults to buyer. Provider buttons should link through `/accounts/social/<provider>/start/<role>/` so the role is chosen before the OAuth handshake. Direct provider URLs fall back to a social signup form that still requires a role.
- Verification is mandatory, so an unverified address cannot log in. Locally, allauth prints the verification email to the console; production needs SMTP configured.
- The Google block only exists when both credentials are set. Otherwise the login page shows no Google button, avoiding a dead link.
- `SOCIALACCOUNT_EMAIL_AUTHENTICATION*` links a Google login to an existing local account with the same verified email. Google verifies email ownership, so this does not create a duplicate account.
- Change the default `example.com` Site row to the real domain in **Admin → Sites**; allauth uses it in verification emails and provider setup.

`config/urls.py`:

```python
path("accounts/", accounts_views.profile_view, name="profile"),
path(
    "accounts/social/<str:provider>/start/<str:role>/",
    accounts_views.social_signup_start,
    name="social_signup_start",
),
path("accounts/", include("allauth.urls")),
```

`/accounts/` is the profile page and photo upload. allauth owns `/accounts/login/`, `/accounts/signup/`, verification, password reset, and social login because the profile route matches only the exact root path.

Google Cloud Console → OAuth client (Web application), authorized redirect URIs:

```
http://localhost:8000/accounts/google/login/callback/
http://127.0.0.1:8000/accounts/google/login/callback/
https://<production-domain>/accounts/google/login/callback/
```

Use the scopes `openid`, `email`, and `profile`. Do not enable Google under Supabase Authentication; the OAuth callback goes to Django, not Supabase.

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

### Media (avatars and listing photos)

Local development stores uploads under `media/` and Django serves them only while `DEBUG=True`:

```python
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
```

Production switches to Supabase Storage when the S3 endpoint is present. `config/storage.py` builds the options so public buckets get permanent Supabase URLs instead of authenticated S3 API URLs:

```python
from config.storage import supabase_storage_options

SUPABASE_S3_ENDPOINT = os.getenv("SUPABASE_S3_ENDPOINT", "")
SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "listings")
SUPABASE_S3_QUERYSTRING_AUTH = os.getenv(
    "SUPABASE_S3_QUERYSTRING_AUTH", ""
).lower() in {"1", "true", "yes"}

if SUPABASE_S3_ENDPOINT:
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": supabase_storage_options(
                endpoint=SUPABASE_S3_ENDPOINT,
                bucket=SUPABASE_BUCKET,
                access_key=os.getenv("SUPABASE_S3_ACCESS_KEY", ""),
                secret_key=os.getenv("SUPABASE_S3_SECRET_KEY", ""),
                region=os.getenv("SUPABASE_S3_REGION", "ap-southeast-1"),
                custom_domain=os.getenv("SUPABASE_S3_CUSTOM_DOMAIN", ""),
                querystring_auth=SUPABASE_S3_QUERYSTRING_AUTH,
            ),
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
```

- Set `SUPABASE_S3_REGION` to the region shown in **Storage → S3 connection**; a different region causes `SignatureDoesNotMatch`.
- S3 access keys live in **Project Settings → Storage → S3 Access Keys**. They are not the `anon` or `service_role` API keys.
- Supabase requires path-style URLs and SigV4 signing; the helper sets both.
- For a **public** bucket (the default), `SUPABASE_S3_QUERYSTRING_AUTH` stays empty. The helper sets `custom_domain` to `<project>.supabase.co/storage/v1/object/public/<bucket>`, which is the only URL that serves public objects without a signature.
- For a **private** bucket, set `SUPABASE_S3_QUERYSTRING_AUTH=True`. Django then returns expiring signed URLs and does not use the public custom domain.
- `file_overwrite=False` plus per-user, random filenames keeps one upload from replacing another.
- Profile photos upload at `/accounts/` with a 5 MB limit; listing photos allow up to 5 files per listing, 5 MB each. Both use the default storage and render through `.url`, never `.path`, so the same code works locally and on Supabase.
- Local tests exercise listing uploads with `InMemoryStorage` to prove no local disk is required.

Supabase bucket checklist:

1. Create the bucket named by `SUPABASE_BUCKET` (default `listings`).
2. Set it to public for permanent CDN URLs, or private with signed URLs.
3. For public buckets, add a read policy on `storage.objects` for the bucket if your project does not already allow public reads.
4. Add `SUPABASE_S3_ENDPOINT`, access key, secret, and region to the environment, then restart the app process so settings reload.

## Database Setup

Run migrations against the direct/session connection, not the transaction pooler:

```bash
DATABASE_URL="$DIRECT_URL" python manage.py migrate
python manage.py createsuperuser
```

`migrate` builds the tables. `createsuperuser` creates an account for the admin site at `/admin/`.

Listings currently use portable ORM search (`icontains` across title, description, category, and farmer names). The local development database is SQLite, so the planned Postgres `pg_trgm` indexes and full-text search are deferred until Supabase Postgres is the active database. When that happens, add a `TrigramExtension` migration and GIN indexes rather than changing the view contract.

## Data Model

| Model | Fields |
| --- | --- |
| `Profile` | One-to-one with User. Role (farmer/buyer), phone, location, notification preferences, avatar. |
| `Category` | Produce type (rice, tomato, and so on), unique name and slug. |
| `Listing` | Public UUID, farmer FK, category FK, title, condition, description, price/is_free, unit, stock, bulk order, deal methods, status, status note, sold-out timestamp, timestamps. |
| `ListingImage` | Listing FK, image, ordered position, alt text. Up to 5 per listing; first position is the cover. |
| `ListingLike` | User FK, listing FK, created timestamp. Unique on `(user, listing)`. |
| `Conversation` | Listing FK, buyer FK, farmer FK. Unique on `(listing, buyer)`. |
| `Message` | Conversation FK, sender FK, body, `created_at`, `read_at`. |
| `Notification` | User FK, type, payload, channel, `sent_at`. |
| `ListingView` | Listing FK, timestamp, anonymous hash. Append-only. |
| `PriceSnapshot` | Category, date, avg/min/max price, listing count. Filled by Celery beat. |

Indexes: `Message(conversation, created_at)` and `Listing(category, status, created_at)`.

Normalize units (kg vs sack) at write time. Averages across mixed units are meaningless.

## Listings

Public routes (all listings use `public_id`, a UUID, instead of the database PK):

| Route | Purpose |
| --- | --- |
| `/` | Redirects to `/listings/`. |
| `/listings/` | Browse active and sold-out listings. |
| `/listings/<uuid>/` | Listing detail. Draft and archived listings are owner-only. |
| `/listings/liked/` | Signed-in user's saved listings. |

Browse filters are ordinary query parameters, so they work without JavaScript:

- `q` searches title, description, category name, and farmer name.
- `category` matches a category slug.
- `condition` matches one of the five condition values.
- `pricing=free` or `pricing=paid` uses the `is_free` flag.
- `page` paginates at 24 listings per page.

Seller routes require a farmer account:

| Route | Purpose |
| --- | --- |
| `/listings/mine/` | Seller dashboard with stock, status, likes, and restock note. |
| `/listings/new/` | Create a listing with 1–5 photos. |
| `/listings/<uuid>/edit/` | Edit an owned listing, add photos, or remove photos. |
| `/listings/<uuid>/delete/` | GET shows confirmation; POST deletes. |

Rules enforced by the model and form:

- Paid listings require a price; free listings must have no price.
- A meet-up deal method requires a location.
- Stock cannot be negative.
- Photos are image files of at most 5 MB each; the first by position is the cover.
- Marking a listing sold out records `sold_out_at`; relisting clears it. `status_note` is optional and appears to buyers, for example “Back in stock Friday.”
- Likes survive sold-out changes so a future notification task can use `ListingLike` plus `sold_out_at`.

Likes use `POST /listings/<uuid>/like/` to toggle. The view redirects back to the detail page, or returns the `listings/_like_button.html` partial when HTMX sends `HX-Request: true`.

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
python manage.py test accounts   # auth, profile, avatar, and signup flows
python manage.py test listings   # models, admin, seller CRUD, browse, likes
```

Django's built-in test runner. For WebSocket consumers, override the channel layer with the in-memory backend so tests do not need Redis:

```python
@override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
```

## Build Order

Each step depends on the previous one.

1. Auth (allauth, custom user, profile) — complete
2. Listings CRUD — complete
3. Browse, search, likes, and sold-out status — complete
4. Chat
5. Notifications
6. Analytics

## Deployment

Pre-deployment checklist:

- `DEBUG=False`
- `SECRET_KEY` set to a unique value from the environment
- `ALLOWED_HOSTS` set to the production domain
- `CSRF_TRUSTED_ORIGINS` set to the public HTTPS origin
- `DATABASE_URL` pointing to the Supabase transaction pooler
- `DB_SSL_REQUIRE=True`
- `REDIS_URL` pointing to a managed Redis instance
- `SUPABASE_S3_*` and `SUPABASE_S3_REGION` configured so uploads persist
- Supabase bucket created, with public-read access or `SUPABASE_S3_QUERYSTRING_AUTH=True`
- `SUPABASE_S3_CUSTOM_DOMAIN` set if the bucket is served from a custom domain
- Site domain changed from `example.com` to the production domain
- Supabase Data API disabled, or `anon` / `authenticated` grants revoked
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
| Google button missing from login | One or both Google credentials are missing | Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`, then restart Django. |
| CSRF verification fails on a deployed form | The public origin is not trusted | Add it to `CSRF_TRUSTED_ORIGINS`, including `https://`. |
| Uploaded avatars disappear after redeploy | Files are on the disposable app filesystem | Configure `SUPABASE_S3_*` so Django uses Supabase Storage. |
| Listing photos return `AccessDenied` / `Missing signature` | `SUPABASE_S3_ENDPOINT` points at the authenticated S3 API instead of the public object URL | Keep `SUPABASE_S3_QUERYSTRING_AUTH` empty for a public bucket so `custom_domain` is used, or set it to `True` for a private bucket. |
| `SignatureDoesNotMatch` on upload | Wrong S3 access key, endpoint, or region | Use the S3 access keys and region from **Storage → S3 connection**, then restart the app. |
| Social buttons create buyers even after choosing farmer | Buttons still point directly at `/accounts/google/login/` | Link through `/accounts/social/google/start/farmer/` (or the buyer variant) instead. |
| WebSocket connects then closes immediately | Authorization check failed or origin rejected | Check the user is a conversation participant and the host is in `ALLOWED_HOSTS`. |
| `redirect_uri_mismatch` on Google login | Callback URL not registered | Add the exact `/accounts/google/login/callback/` URL in Google Cloud Console. |
