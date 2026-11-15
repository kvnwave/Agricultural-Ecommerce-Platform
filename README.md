# Agricultural E-commerce Platform

A Django marketplace for agricultural products. Farmers post produce listings. Buyers browse and save them.

## Status

| Feature | State |
| --- | --- |
| Email and Google login, buyer/farmer roles, profile photo | Done |
| Farmer listings (create, edit, delete, up to 5 photos) | Done |
| Browse, search, filter, like listings | Done |
| Sold-out status with restock note | Done |
| Buyer/farmer chat | Planned |
| Notifications (email, SMS) | Planned |
| Analytics | Planned |

`chat`, `analytics`, and `notifications` are placeholder apps for now.

## Stack

- Django 6.1, django-allauth (email + Google login)
- SQLite for local development, Supabase Postgres for production
- Supabase Storage (S3 protocol, via django-storages) for uploaded photos
- Tailwind CSS v4 (npm CLI)

## Requirements

- Python 3.14
- Node.js and npm
- Git

## Setup

```bash
git clone https://github.com/kvnwave/Agricultural-Ecommerce-Platform.git
cd Agricultural-Ecommerce-Platform

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
npm install

cp .env.example .env             # then set SECRET_KEY and DEBUG=True
python manage.py migrate
python manage.py createsuperuser
```

Generate a secret key:

```bash
python -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
```

## Run

Use two terminals.

```bash
# 1. Tailwind (rebuilds CSS on change)
npm run watch

# 2. Django
python manage.py runserver
```

Open `http://127.0.0.1:8000/`. Admin is at `/admin/`.

Build CSS once without watching: `npm run build`.

## Environment Variables

Copy `.env.example` to `.env`. Never commit `.env`. The example ships with
production-safe defaults (`DEBUG=False`), so local development must set
`DEBUG=True`; without it Django will not serve static files through
`runserver` and will expect a real mail server.

Required for local development:

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Django signing key. |
| `DEBUG` | `True` locally, `False` in production. |
| `ALLOWED_HOSTS` | Comma-separated hostnames. |
| `DATABASE_URL` | Defaults to `sqlite:///db.sqlite3`. |

Optional:

| Variable | Purpose |
| --- | --- |
| `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Google login. The button only appears when both are set. |
| `DIRECT_URL` | Direct Supabase connection, used for `migrate`. |
| `DB_SSL_REQUIRE` | Force TLS for remote databases. |
| `CSRF_TRUSTED_ORIGINS` | Public HTTPS origins, needed in production. |
| `TRUST_X_FORWARDED_PROTO` | Trust the proxy's `X-Forwarded-Proto`. Enable only when the proxy overwrites it. |
| `SUPABASE_S3_*`, `SUPABASE_BUCKET` | Supabase Storage. Without these, uploads go to `media/`. |

### Email

Local development prints email to the console. Production requires:

| Variable | Purpose |
| --- | --- |
| `EMAIL_HOST` | SMTP hostname. |
| `DEFAULT_FROM_EMAIL` | Sender address accepted by the provider. |
| `EMAIL_PORT` | Defaults to `587`. |
| `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | SMTP credentials, if required. |
| `EMAIL_USE_TLS`, `EMAIL_USE_SSL` | STARTTLS (default) or implicit TLS. Set only one. |

## Google Login

In Google Cloud Console, create a Web OAuth client and add these redirect URIs:

```
http://localhost:8000/accounts/google/login/callback/
http://127.0.0.1:8000/accounts/google/login/callback/
https://<your-domain>/accounts/google/login/callback/
```

Social signup goes through `/accounts/social/<provider>/start/<role>/` so the user picks buyer or farmer first.

## Main Routes

| Route | Purpose |
| --- | --- |
| `/listings/` | Browse and search listings |
| `/listings/<uuid>/` | Listing detail |
| `/listings/liked/` | Saved listings |
| `/listings/mine/` | Farmer dashboard |
| `/listings/new/` | Create a listing (farmers only) |
| `/accounts/` | Profile and photo upload |

Browse filters: `q`, `category`, `condition`, `pricing` (`free` or `paid`), `page`.

## Project Structure

```
config/          Settings, URLs, storage helper
accounts/        Custom user, profile, signup
listings/        Categories, listings, images, likes
chat/            Placeholder
analytics/       Placeholder
notifications/   Placeholder
templates/       HTML templates
static/          Tailwind input and built CSS
```

## Tests

```bash
python manage.py test
```

## Deployment

1. Set `DEBUG=False`, a unique `SECRET_KEY`, `ALLOWED_HOSTS`, and `CSRF_TRUSTED_ORIGINS`. If the app sits behind a proxy that terminates TLS, set `TRUST_X_FORWARDED_PROTO=True` and make the proxy **replace** `X-Forwarded-Proto` with its own scheme; a forwarded client value would let plain HTTP bypass the HTTPS redirect. Leave it off when the app is exposed directly.
2. Configure `EMAIL_HOST`, `DEFAULT_FROM_EMAIL`, and credentials. allauth sends verification links, so signup fails without working SMTP.
3. Point `DATABASE_URL` at the Supabase transaction pooler (port 6543) and `DIRECT_URL` at the direct or session connection (port 5432).
4. Run migrations on the direct connection: `DATABASE_URL="$DIRECT_URL" python manage.py migrate`.
5. Configure `SUPABASE_S3_*` so uploads persist. The app filesystem is disposable.
6. Change the default `example.com` row in **Admin → Sites** to your domain.
7. Run `npm run build` and `python manage.py collectstatic`.
8. Run `python manage.py check --deploy`. `W005` and `W021` are expected until every subdomain is HTTPS-only; enabling HSTS subdomains or preload early can make HTTP-only subdomains unreachable and is slow to undo.
9. Set the proxy request body limit to at least 30 MB (nginx: `client_max_body_size 30m;`). Django spools oversized bodies to disk before form validation, so the proxy should reject them first.
10. CSP starts in report-only mode (`SECURE_CSP_REPORT_ONLY`). Review reports from the marketplace, admin, and allauth pages, then copy the policy into `SECURE_CSP` to enforce it. Allauth’s email-management templates use inline JSON and style attributes, so verify those pages before enforcing.

## Supabase Notes

- Django connects directly to Postgres. Disable the Supabase Data API, or revoke the `anon` and `authenticated` grants on `public`, so `accounts_user` is not exposed.
- Never put the Supabase `service_role` key in Django.
- Set `SUPABASE_S3_REGION` to the region shown in **Storage → S3 connection**. A wrong region causes `SignatureDoesNotMatch`.
- Public bucket: leave `SUPABASE_S3_QUERYSTRING_AUTH` empty. Private bucket: set it to `True`.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `No DATABASE_URL environment variable set` | Add `DATABASE_URL` to `.env`. |
| Page has no styles | Run `npm run build`. |
| Google button missing | Set both Google credentials and restart. |
| `redirect_uri_mismatch` | Register the exact callback URL in Google Cloud Console. |
| CSRF failure on deployed forms | Add the `https://` origin to `CSRF_TRUSTED_ORIGINS`. |
| Cursor errors on Supabase | Run `migrate` through `DIRECT_URL`, not the transaction pooler. |
| Uploaded photos missing after redeploy | Configure `SUPABASE_S3_*`. |
| `zsh: no matches found` on a pip install with brackets | Quote the package name, e.g. `"psycopg[binary]"`. |