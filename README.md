# Agricultural E-commerce Platform

A Django marketplace for agricultural products. Farmers post produce listings. Buyers browse and save them.

> **Frontend handoff:** the marketplace templates were removed so the frontend
> can be rebuilt separately. The Tailwind/htmx assets and the account pages are
> unchanged. See
> [docs/frontend-instructions.md](docs/frontend-instructions.md) for every
> route, URL name, context variable, and form field the views expose.

## Status

| Feature | State |
| --- | --- |
| Email and Google login, buyer/farmer roles, profile photo | Done |
| Farmer listings (create, edit, delete, up to 5 photos) | Done |
| Browse, search, filter, like listings | Done |
| Sold-out status with restock note | Done |
| Marketplace frontend templates | Removed for handoff |
| Buyer/farmer chat | Planned |
| Notifications (email, SMS) | Planned |

`chat` and `notifications` are placeholder apps for now. Their
views still exist, but their templates were removed with the rest of the
marketplace frontend.

## Stack

- Django 6.1, django-allauth (email + Google login)
- SQLite for local development, Supabase Postgres for production
- Supabase Storage (S3 protocol, via django-storages) for uploaded photos
- Tailwind CSS v4 (npm CLI) and htmx for the server-rendered pages
- Django templates: the marketplace pages are being rebuilt separately; the
  authentication pages still render through Django

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
python manage.py createcachetable
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

Open `http://127.0.0.1:8000/`. Admin is at `/control-panel/` by default; change it with `DJANGO_ADMIN_PATH`.

Build CSS once without watching: `npm run build`.

### Development auto-login

With `DEBUG=True`, anonymous visitors are signed in automatically as a local
`dev@example.com` account (farmer + staff, created on first use, unusable
password), so the login-protected pages can be reviewed without registering.
The middleware does nothing when `DEBUG=False`, so deployment still requires
allauth login.

Authentication pages render under `/accounts/` (for example,
`/accounts/login/`). Marketplace routes return
`TemplateDoesNotExist` until the frontend templates are restored; the required
template paths and context variables are listed in
[docs/frontend-instructions.md](docs/frontend-instructions.md).

## Environment Variables

Copy `.env.example` to `.env`. Never commit `.env`. The example ships with
production-safe defaults (`DEBUG=False`), so local development must set
`DEBUG=True`; without it Django serves static files through WhiteNoise from
`staticfiles/` after `collectstatic`, and expects a real mail server.

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
| `DIRECT_URL` | Direct or session Supabase connection (port 5432), used by `config.settings_direct` for `migrate` and `createcachetable`. |
| `DB_SSL_REQUIRE` | Force TLS for remote databases. |
| `CSRF_TRUSTED_ORIGINS` | Public HTTPS origins, needed in production. |
| `DJANGO_ADMIN_PATH` | Admin URL path. Defaults to `control-panel/`. |
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
chat/            Placeholder view
notifications/   Placeholder view
docs/            Frontend handoff instructions
templates/       Base shell, auth pages, and the profile pages
assets/          Tailwind source
static/          Built CSS and vendored JavaScript
```

The marketplace and placeholder templates were removed; the Tailwind source,
built CSS, htmx, and npm files stay in place. The remaining
`templates/base.html`, `templates/account/`, `templates/socialaccount/`, and
`templates/accounts/` files keep login, signup, email verification, password
reset, and the profile pages working. New marketplace templates should live
under `templates/` and extend `base.html`.

`requirements-future.txt` pins infrastructure packages (Celery, Channels,
Daphne) that the app does not import yet, so they stay out of the deployed
environment until a feature needs them.

## Frontend Handoff

The frontend teammate has a complete contract in
[docs/frontend-instructions.md](docs/frontend-instructions.md):

- Removed and kept template paths.
- Every route, URL name, HTTP method, and permission rule.
- The exact context variables each view passes, including pagination,
  search/filter values, forms, and listing/profile model fields.
- Form fields, file-upload limits, CSRF requirements, and redirect targets.

The short version: put a template at the path listed for each view, extend
`base.html`, use `{% url %}` with the documented names, and include
`{% csrf_token %}` in every POST form. The views already supply the variables;
no Python changes are needed to reconnect the pages.

## Tests

```bash
python manage.py test --settings=config.settings_test
```

Template-dependent tests will fail until the marketplace templates are
restored. They are intentionally left in place so they show exactly what the
frontend needs to satisfy. Tests for models, forms, permissions, and search
still run normally.

CI runs that suite, checks for missing migrations, runs `check --deploy` with a production-like environment, verifies `collectstatic`, and audits `requirements.txt` with `pip-audit`. Dependabot and CodeQL are configured in `.github/`.

Demo listings, when present, belong to the `demo-farmer@example.com` account.
Remove them, their photos, and that account with
`python manage.py delete_demo_listings`; `--dry-run` reports the counts first.
Removal is permanent, including the stored photos.

## Deployment

1. Set `DEBUG=False`, a unique `SECRET_KEY`, `ALLOWED_HOSTS`, and `CSRF_TRUSTED_ORIGINS`. If the app sits behind a proxy that terminates TLS, set `TRUST_X_FORWARDED_PROTO=True` and make the proxy **replace** `X-Forwarded-Proto` with its own scheme; a forwarded client value would let plain HTTP bypass the HTTPS redirect. Leave it off when the app is exposed directly.
2. Configure `EMAIL_HOST`, `DEFAULT_FROM_EMAIL`, and credentials. allauth sends verification links, so signup fails without working SMTP.
3. Point `DATABASE_URL` at the Supabase transaction pooler (port 6543) and `DIRECT_URL` at the direct or session connection (port 5432). The web process only ever uses `DATABASE_URL`.
4. Run migrations on the direct connection: `python manage.py migrate --settings=config.settings_direct`.
5. Create the shared cache table on the direct connection: `python manage.py createcachetable --settings=config.settings_direct`. allauth's login throttles use it.
6. Configure `SUPABASE_S3_*` so uploads persist. The app filesystem is disposable.
7. Change the default `example.com` row in **Admin → Sites** to your domain.
8. Run `python manage.py collectstatic --noinput`. WhiteNoise serves the collected admin static files from `staticfiles/`.
9. Run `python manage.py check --deploy`. `W005` and `W021` are expected until every subdomain is HTTPS-only; enabling HSTS subdomains or preload early can make HTTP-only subdomains unreachable and is slow to undo.
10. Set the proxy request body limit to at least 30 MB (nginx: `client_max_body_size 30m;`). Django spools oversized bodies to disk before form validation, so the proxy should reject them first.
11. CSP starts in report-only mode (`SECURE_CSP_REPORT_ONLY`). Review reports from the marketplace, admin, and allauth pages, then copy the policy into `SECURE_CSP` to enforce it. Allauth’s email-management templates use inline JSON and style attributes, so verify those pages before enforcing.
12. Set `DJANGO_ADMIN_PATH` to a deployment-specific value and restrict that path at the proxy (IP allowlist or VPN). Django’s admin login is outside allauth’s rate limits, so the proxy is the throttle.

## Supabase Notes

- Supabase's direct connection (port 5432) is IPv6-only. On an IPv4-only network, use the **Session pooler** string for `DIRECT_URL`; it runs migrations fine.
- Passwords with reserved characters (`[`, `]`, `#`, `/`, `:`, `?`, `@`, spaces) are percent-encoded by `config/database.py` before parsing, so a password copied verbatim from the dashboard still works. A literal `%` is escaped as well, while an existing `%XX` escape is left intact.
- Django connects directly to Postgres. Disable the Supabase Data API, or revoke the `anon` and `authenticated` grants on `public`, so `accounts_user` is not exposed.
- Never put the Supabase `service_role` key in Django.
- Set `SUPABASE_S3_REGION` to the region shown in **Storage → S3 connection**. A wrong region causes `SignatureDoesNotMatch`.
- Public bucket: leave `SUPABASE_S3_QUERYSTRING_AUTH` empty. Private bucket: set it to `True`.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `No DATABASE_URL environment variable set` | Add `DATABASE_URL` to `.env`. |
| `TemplateDoesNotExist` on a marketplace route | Expected during the handoff. Create the template listed in `docs/frontend-instructions.md`. |
| Google button missing | Set both Google credentials and restart. |
| `redirect_uri_mismatch` | Register the exact callback URL in Google Cloud Console. |
| CSRF failure on deployed forms | Add the `https://` origin to `CSRF_TRUSTED_ORIGINS`. |
| Cursor errors on Supabase | Run schema commands with `--settings=config.settings_direct` so they use `DIRECT_URL`, not the transaction pooler. |
| `nodename nor servname provided` for the direct host | Supabase's direct connection is IPv6-only. Copy the **Session pooler** string (port 5432) into `DIRECT_URL` instead. |
| `password authentication failed` on the pooler | Check the password is not still wrapped in the `[ ]` from the connection-string placeholder, then reset it in **Database settings** and re-copy both strings. |
| `does not appear to be an IPv4 or IPv6 address` | A password contains `[` or `]`. `config/database.py` percent-encodes reserved password characters, so update the app if this still appears. |
| Uploaded photos missing after redeploy | Configure `SUPABASE_S3_*`. |
| `zsh: no matches found` on a pip install with brackets | Quote the package name, e.g. `"psycopg[binary]"`. |