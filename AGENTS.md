# Agent instructions

This is the operating manual for AI agents working on the Agricultural
E-commerce Platform. It replaces the deleted `docs/frontend-instructions.md`;
the previous version of that document remains in git history.

## Read this first

- **You are taking over the marketplace frontend.** The Django views, URLs,
  models, forms, permissions, and authentication flow are the contract. The
  markup is not.
- **The current templates are the baseline, not a blank slate.** They render,
  and all 233 tests pass. Improve them; do not delete them to start over.
- **Do not rename URL names, context variables, form field names, template
  paths, or the strings the tests assert.** Those are the interface between the
  frontend and backend.
- **Run the checks before calling a change done:** the test suite, the CSS
  build, and the migration check. See [Verification](#verification).
- **Ask before changing product behavior.** Pricing, roles, permissions,
  search semantics, listing limits, status rules, and authentication are
  product decisions, not styling choices.

### Source-of-truth order

1. Running code and the test suite.
2. This file for the route/context/form contract and working rules.
3. `README.md` for setup, environment, and deployment.
4. Commit history for earlier variants.

If two sources disagree, stop and reconcile them. Do not silently pick one.

## Project snapshot

A Django marketplace for agricultural products. Farmers post produce listings;
buyers browse and save them.

| Area | State |
| --- | --- |
| Email and Google login, buyer/farmer roles, profile photo | Done |
| Farmer listings: create, edit, delete, up to 5 photos | Done |
| Browse, search, filter, like/save listings | Done |
| Sold-out status with restock note | Done |
| Marketplace frontend templates | Present and passing |
| Buyer/farmer chat | Placeholder |
| Notifications (email, SMS) | Placeholder |

### Stack

- Django 6.1.3, Python 3.14, django-allauth 65.22
- SQLite for local development; Supabase Postgres for production
- Supabase Storage (S3 protocol, via django-storages) for uploaded photos
- Tailwind CSS v4 through the npm CLI; htmx 2.0.11 vendored in `static/js/`
- Server-rendered Django templates. There is no REST API, SPA, or separate
  frontend build.
- WhiteNoise serves collected static files in production.

### Deliberately absent

Do not add these without an explicit product decision:

- Analytics. The `analytics` app was removed; do not resurrect it.
- A REST or GraphQL API.
- A JavaScript framework or client-side router.
- Celery, Channels, Redis, or Daphne. They are pinned in
  `requirements-future.txt` but not installed; move a package into
  `requirements.txt` only when code starts importing it.

## Verification

### Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
npm install
cp .env.example .env      # then set SECRET_KEY and DEBUG=True
python manage.py migrate
python manage.py createcachetable
python manage.py createsuperuser
```

### Run

Use two terminals:

```bash
# Terminal 1: rebuild Tailwind CSS on change
npm run watch

# Terminal 2: Django
python manage.py runserver
```

Open `http://127.0.0.1:8000/`. Admin is at `/control-panel/` by default; the
path is configurable with `DJANGO_ADMIN_PATH`.

### Test and check

```bash
python manage.py test --settings=config.settings_test
python manage.py makemigrations --check --dry-run
npm run build
git diff --exit-code -- static/css_output/output.css
python manage.py check --deploy
python manage.py collectstatic --noinput
```

`config.settings_test` deliberately pins the database to local SQLite even if
`.env` points at Supabase. Do not remove that isolation.

`check --deploy` expects production-like environment variables. CI sets them;
run it locally only with a production-like `.env`.

### Development auto-login

With `DEBUG=True`, a middleware signs anonymous visitors in as a local
`dev@example.com` farmer/staff account. It does nothing when `DEBUG=False`.
This makes protected pages easy to review, but it hides real login redirects
and 403/404 responses. Set `DEBUG=False` when testing permissions.

### Database and storage

- Local development uses `sqlite:///db.sqlite3`.
- Production uses Supabase's transaction pooler (port 6543) for the web
  process. Schema commands use `config.settings_direct` and `DIRECT_URL`
  (direct or session connection, port 5432):

  ```bash
  python manage.py migrate --settings=config.settings_direct
  python manage.py createcachetable --settings=config.settings_direct
  ```

- Uploads go to `media/` locally and Supabase Storage when `SUPABASE_S3_*` is
  configured. The app filesystem is disposable in production.
- Never put the Supabase `service_role` key in Django.
- Never commit `.env`, `db.sqlite3`, `media/`, `staticfiles/`, or
  `node_modules/`.

## Architecture map

| Path | Responsibility |
| --- | --- |
| `config/` | Settings, root URLs, database URL handling, storage options |
| `accounts/` | Custom user, profile, signup, username policy, allauth adapters, dev auto-login |
| `listings/` | Categories, listings, images, likes, views, forms, admin, demo-data command |
| `chat/` | Login-gated placeholder view |
| `notifications/` | Login-gated placeholder view |
| `templates/` | Base shell, marketplace pages, account pages, allauth shells |
| `assets/css/input.css` | Tailwind source and theme tokens |
| `static/css_output/output.css` | Built CSS; committed and CI-checked |
| `static/js/htmx.min.js` | Vendored htmx |
| `.github/workflows/` | CI, CodeQL |
| `requirements-future.txt` | Infrastructure packages not imported yet |

### Template inventory

All of these are present and tracked unless noted. New marketplace templates
must live under `templates/` and extend `base.html`.

| Template | Used by | Notes |
| --- | --- | --- |
| `base.html` | Every page | Header, navigation, messages, blocks |
| `listings/listings.html` | `listings_view` | Browse and filters |
| `listings/_listing_card.html` | Included by browse and saved pages | Expects `listing` |
| `listings/listing_detail.html` | `listing_detail` | Detail, photos, like button |
| `listings/_like_button.html` | htmx response from `listing_like_toggle` | Expects `listing`, `is_liked` |
| `listings/liked_listings.html` | `liked_listings` | Saved grid |
| `listings/my_listings.html` | `my_listings` | Farmer dashboard |
| `listings/listing_form.html` | `listing_create`, `listing_update` | Create/edit form |
| `listings/listing_confirm_delete.html` | `listing_delete` | Delete confirmation |
| `partials/pagination.html` | Browse, saved, dashboard | Expects `page_obj` |
| `partials/avatar.html` | Profile and seller displays | Expects `avatar_user` or current `user` |
| `accounts/accounts.html` | `profile_view` | Profile and avatar upload |
| `accounts/username_change.html` | `username_change` | Username form and cooldown |
| `account/base_entrance.html`, `account/base_manage.html` | allauth shells | Extend `base.html` |
| `account/login.html`, `account/signup.html` | allauth login/signup | Add Google buttons |
| `socialaccount/base_entrance.html`, `socialaccount/base_manage.html` | allauth social shells | Extend `base.html` |
| `chat/chat.html` | `chat_view` | Placeholder |
| `notifications/notifications.html` | `notifications_view` | Placeholder |
| `home.html`, `bare.html` | Temporary menu | Not final design |

## Non-negotiable product decisions

### Accounts and roles

- Email is the login identifier. Usernames are internal handles.
- Email verification is mandatory. An unverified account cannot log in.
- Google login is optional. Buttons appear only when both
  `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are set.
- Every user has one profile, created by a `post_save` signal on `User`.
- Roles are `buyer` and `farmer`, chosen at signup.
- Farmers can create and manage listings. Buyers can browse and save.
- `user.profile.avatar_url` prefers an uploaded avatar, then the Google
  picture, then an empty string. It is cached per profile instance.

### Usernames

- 3–30 characters.
- Letters, numbers, underscores, and hyphens only.
- Must start and end with a letter or number.
- Stored lowercase; uniqueness is case-insensitive.
- Reserved names such as `admin`, `support`, `farmer`, and `buyer` are
  rejected.
- The first change is immediate. Later changes have a 7-day cooldown.
- Staff bypass the cooldown.
- Every change is recorded in `UsernameHistory`.

### Listings

- URLs use `listing.public_id` (UUID), never the numeric `id`.
- Statuses: `draft`, `active`, `sold_out`, `archived`.
- Public browse and detail show only `active` and `sold_out`.
- Owners can preview their own `draft` and `archived` listings; everyone else
  gets 404.
- `active` requires stock greater than zero.
- `sold_out` clears stock to zero and sets `sold_out_at`; leaving `sold_out`
  clears `sold_out_at`.
- Free and paid are mutually exclusive: `is_free=True` requires `price=None`;
  `is_free=False` requires a price of at least `0.01`. A database constraint
  enforces this.
- Prices are in Philippine pesos (PHP) per `unit`.
- At most 25 open listings per farmer (archived listings do not count).
- At most 10 listings created per rolling 24 hours.
- At most 5 photos per listing. Each photo is at most 5 MB and 25 megapixels.
- JPEG, PNG, and WebP only. Uploads are re-encoded to strip EXIF, GPS, and
  other metadata.
- The lowest `position` is the cover. New photos append after the highest
  existing position.
- Photos are stored under `listings/<public_id>/<uuid>.<ext>`.

### Likes and saved listings

- A user can like a listing once. The like endpoint toggles it.
- `active` and `sold_out` listings can be liked.
- `likes_total` is annotated by the browse, detail, saved, and farmer dashboard
  views. It does not exist on listings fetched any other way.
- Saved listings include `sold_out` listings, newest save first.

### Search, filters, and pagination

- `q` is trimmed to 100 characters and matched as one case-insensitive
  substring across title, description, category name, farmer first name,
  farmer last name, and farmer username. It is not split into words, and there
  is no fuzzy matching.
- `category` is an exact `Category.slug` match. An unknown slug returns an
  empty list.
- `condition` must be one of `fresh`, `ripe`, `blemished`, `overripe`,
  `processing`; unknown values are ignored.
- `pricing` is `free` or `paid`; other values are ignored.
- `page` is an integer. A non-integer falls back to page 1; an out-of-range
  number falls back to the last page.
- Pagination is 24 items per page on browse, saved, and farmer dashboard.
- Ordering is newest first with `-id` as a tiebreaker so pagination stays
  stable.

### Currency and time

- Prices display as `₱{{ price|floatformat:2 }}`; show `Free` when
  `listing.is_free`.
- Timezone is `Asia/Manila`.

## Frontend contract

### Base template and blocks

`base.html` owns the header, main navigation, logout form, and messages. It
exposes these blocks:

- `title`
- `extra_head`
- `content`
- `extra_body`

Do not add a second header, navigation, or logout form. The navigation shows:

- Browse for everyone.
- Saved, Profile, and Log out for signed-in users.
- My listings and "Sell produce" only for signed-in farmers.
- Log in and Sign up for anonymous visitors.

### Route summary

| Path | URL name | Methods | Access | Template |
| --- | --- | --- | --- | --- |
| `/` | `home` | GET | Public | `home.html` (temporary menu) |
| `/listings/` | `listings` | any (use GET) | Public | `listings/listings.html` |
| `/listings/<uuid>/` | `listing_detail` | any (use GET) | Public; owner can preview non-public | `listings/listing_detail.html` |
| `/listings/<uuid>/like/` | `listing_like_toggle` | POST | Signed in | `listings/_like_button.html` for htmx, otherwise redirect |
| `/listings/liked/` | `liked_listings` | any (use GET) | Signed in | `listings/liked_listings.html` |
| `/listings/mine/` | `my_listings` | any (use GET) | Farmer | `listings/my_listings.html` |
| `/listings/new/` | `listing_create` | GET, POST | Farmer | `listings/listing_form.html` |
| `/listings/<uuid>/edit/` | `listing_update` | GET, POST | Owner | `listings/listing_form.html` |
| `/listings/<uuid>/delete/` | `listing_delete` | GET, POST | Owner | `listings/listing_confirm_delete.html` |
| `/accounts/` | `profile` | GET, POST | Signed in | `accounts/accounts.html` |
| `/accounts/username/` | `username_change` | GET, POST | Signed in | `accounts/username_change.html` |
| `/accounts/social/<provider>/start/<role>/` | `social_signup_start` | GET | Public | Redirects to provider |
| `/chat/` | `chat` | GET | Signed in | `chat/chat.html` |
| `/notifications/` | `notifications` | GET | Signed in | `notifications/notifications.html` |
| `/control-panel/` | `admin:index` | GET | Staff | Django admin; path configurable |

allauth owns login, signup, logout, email verification, password reset, email
management, and social login under `/accounts/`.

### Access behavior

- "Signed in" uses `@login_required`; anonymous requests redirect to
  `/accounts/login/?next=<original path>`.
- "Farmer" adds a role check; a signed-in buyer gets 403.
- "Owner" filters by `farmer=request.user`; any other signed-in user,
  including a buyer, gets 404. Edit and delete check ownership only, not the
  farmer role.

### Browse — `/listings/`

Context:

| Variable | Type | Notes |
| --- | --- | --- |
| `page_obj` | Django `Page` | Paginated listings |
| `listings` | list | Current page; each has `likes_total`, `category`, `farmer`, and prefetched `images` |
| `categories` | QuerySet | All categories, ordered by name |
| `conditions` | list of `(value, label)` | `Listing.Condition.choices` |
| `pricing_options` | tuple | `(("free", "Free"), ("paid", "Paid"))` |
| `query` | string | Trimmed/truncated `q` |
| `selected_category` | string | Submitted category slug |
| `selected_condition` | string | Submitted condition value |
| `selected_pricing` | string | Submitted pricing value |

Use `{% url 'listing_detail' listing.public_id %}` for cards,
`{% url 'liked_listings' %}` for saved, and `{% url 'my_listings' %}` for the
dashboard.

### Listing detail — `/listings/<uuid>/`

Context:

| Variable | Type | Notes |
| --- | --- | --- |
| `listing` | `Listing` | Includes `likes_total` and prefetched `images` |
| `is_owner` | boolean | Signed-in user is `listing.farmer` |
| `can_like` | boolean | Status is `active` or `sold_out` |
| `is_liked` | boolean | Signed-in user saved this listing; false for anonymous |

Useful values:

```django
{{ listing.title }}
{{ listing.category.name }}
{{ listing.get_condition_display }}
{{ listing.get_status_display }}
{{ listing.get_unit_display }}
₱{{ listing.price|floatformat:2 }}   {# show "Free" when listing.is_free #}
{{ listing.stock_quantity|floatformat:"-2" }}
{{ listing.bulk_order }}
{{ listing.status_note }}
{{ listing.description|linebreaks }}
{{ listing.meetup }} / {{ listing.meetup_location }} / {{ listing.meetup_notes }}
{{ listing.direct_to_market }} / {{ listing.delivery }}
{{ listing.farmer.get_full_name|default:listing.farmer.username }}
{{ listing.likes_total }}
```

Photos:

```django
{% with cover=listing.cover_image %}
  {% if cover %}
    <img src="{{ cover.image.url }}" alt="{{ cover.alt_text|default:listing.title }}">
  {% endif %}
{% endwith %}

{% for image in listing.images.all %}
  <img src="{{ image.image.url }}" alt="{{ image.alt_text|default:listing.title }}">
  {# image.position is the stored order; the lowest position is the cover #}
{% endfor %}
```

Anonymous login link:

```django
<a href="{% url 'account_login' %}?next={{ request.path|urlencode }}">
  Log in to save this listing
</a>
```

### Like toggle — `/listings/<uuid>/like/`

- `POST` only. An authenticated `GET` returns 405.
- Anonymous requests redirect to login with `next` set to the like URL.
- Only `active` and `sold_out` listings can be liked; otherwise 404.
- Creates the `ListingLike` if missing; deletes it if present.
- With `HX-Request: true`, renders `listings/_like_button.html` with `listing`
  (fresh `likes_total`) and `is_liked`.
- Otherwise redirects to a safe `next`, then a same-origin `Referer`, then the
  listing detail. External or malformed destinations are ignored.

Form:

```django
<form method="post" action="{% url 'listing_like_toggle' listing.public_id %}">
  {% csrf_token %}
  <input type="hidden" name="next" value="{{ request.path }}">
  <button type="submit" aria-pressed="{{ is_liked|yesno:'true,false' }}">
    {% if is_liked %}♥ Saved{% else %}♡ Save{% endif %}
    <span>{{ listing.likes_total }}</span>
  </button>
</form>
```

For htmx, keep `hx-post`, `hx-target="this"`, and `hx-swap="outerHTML"`. The
normal form POST must still work without JavaScript.

### Saved listings — `/listings/liked/`

Context: `page_obj`, `listings`. Listings include `category` and `farmer`
select-related and `images` prefetched. Only `active` and `sold_out` are
included, newest save first.

### Farmer dashboard — `/listings/mine/`

Context: `page_obj`, `listings`. Includes every status, newest first. Each
listing has `likes_total`; `category` is select-related.

### Create listing — `/listings/new/`

Context: `form` (`ListingForm`), `is_edit` (always `False`).

Limits are checked before the form is shown and again atomically on POST:

- At most 25 open listings (archived do not count).
- At most 10 creations in a rolling 24-hour window.

When a limit is hit, the view adds an error message and redirects to
`my_listings`; it does not render the form. A valid POST sets the farmer, saves
the listing and photos, adds "Your listing has been created.", and redirects to
`my_listings`. An invalid POST re-renders the form with status 200.

The form must use:

```django
<form method="post" enctype="multipart/form-data">
  {% csrf_token %}
  {{ form.as_p }}
  <button type="submit">List now</button>
  <a href="{% url 'my_listings' %}">Cancel</a>
</form>
```

`{{ form.as_p }}` renders non-field errors. If you render fields manually,
also render `form.non_field_errors`. The current template renders the fields
manually: `condition` as radio pills, `is_free` as a For Sale / For Free
segmented toggle, and `bulk_order`, `meetup`, `direct_to_market`, and
`delivery` as on/off switches styled in CSS. It renders `non_field_errors` and
per-field errors, a `Clear details` reset button, and the `remove_images`
checkboxes as trash buttons overlaid on the existing photo thumbnails. The
card is full-width (no `max-w` cap). The Status section (`status`,
`status_note`) is hidden on create and shown only when editing; the fields
stay in the DOM so the POST contract is unchanged and `status` keeps its
`active` default. The meet-up location input has a client-side Nominatim
(OpenStreetMap) autocomplete limited to the Philippines. Toggling
`direct_to_market` reveals nearby public markets via browser geolocation and
the Overpass API, with a graceful note and retry when location is denied;
toggling `delivery` reveals an explanatory note. Both reveals are CSS-only,
matching the meet-up reveal. Selects use an on-theme custom chevron
(`appearance: none` plus a mute SVG arrow in `input.css`) instead of native
browser chrome.

`ListingForm` fields, in display order:

| Field | Widget / values | Rules |
| --- | --- | --- |
| `title` | text | Required, max 120 characters |
| `category` | select of `Category` | Required |
| `condition` | radio pills (`RadioSelect`); `fresh`, `ripe`, `blemished`, `overripe`, `processing` | Required, defaults to `fresh` |
| `description` | textarea | Required |
| `price` | decimal | At least `0.01`; required when `is_free` is unchecked; must be empty when `is_free` is checked. Rendered with a ₱ prefix and hidden (still in the DOM) while `is_free` is checked; its errors render outside the hidden wrapper |
| `is_free` | checkbox, rendered as a For Sale / For Free toggle | Default unchecked |
| `unit` | `kg`, `g`, `sack`, `piece`, `bunch`, `crate`, `tray`, `box`, `liter`, `dozen` | Required, defaults to `kg` |
| `stock_quantity` | decimal | At least `0`, defaults to `1`; `active` needs stock greater than 0; `sold_out` clears it to 0 |
| `bulk_order` | checkbox | Accept larger orders than listed stock |
| `meetup` | checkbox | Requires `meetup_location` when checked |
| `meetup_location` | text | Max 255 characters; required when `meetup` is checked; browser autocompletes real PH places via Nominatim |
| `meetup_notes` | textarea | Optional; rendered at 2 rows |
| `direct_to_market` | checkbox | Optional |
| `delivery` | checkbox | Optional |
| `status` | `draft`, `active`, `sold_out`, `archived` | Required, defaults to `active` |
| `status_note` | text | Max 255 characters; restock note |
| `images` | multiple file input (`accept="image/*"`) | At least one photo in total |
| `remove_images` | multiple checkbox | Only present when editing |

Validation messages:

- `Add at least one photo.`
- `Add at most 5 photos.`
- `Each photo must be smaller than 5 MB.`
- `Free listings cannot have a price.`
- `Set a price or mark the listing as free.`
- `Add the meet-up location.`

Photo rules:

- At most 5 photos per listing, counting remaining existing photos plus new
  ones.
- Each photo at most 5 MiB.
- JPEG, PNG, and WebP only; re-encoded to strip metadata.
- Above 25 megapixels is rejected before re-encoding.
- At most 10 uploaded files per request.
- The lowest `position` is the cover; new photos append after the highest
  existing position. Removing a photo does not renumber the rest.
- `alt_text` has no form field; it is set in the admin and falls back to the
  listing title in templates.

### Edit listing — `/listings/<uuid>/edit/`

Context: `form` (`ListingForm` with `remove_images`), `listing`, `is_edit`
(always `True`). The view locks the listing row inside a transaction before
validating. Show existing photos and let the user tick `remove_images`. At
least one photo must remain; the 5-photo limit counts remaining plus new. On
success: "Your listing has been updated." and redirect to `my_listings`.

After an invalid POST, `listing` holds the submitted values in memory; the
view restores the stored row so the page heading shows the saved title. The
bound form keeps the user's input.

### Delete listing — `/listings/<uuid>/delete/`

Context: `listing`. `GET` shows confirmation; `POST` deletes. Other methods
return 405. On success: "Your listing has been deleted." and redirect to
`my_listings`. Photo files are removed after the transaction commits.

```django
<form method="post">
  {% csrf_token %}
  <p>Delete “{{ listing.title }}”? This cannot be undone.</p>
  <button type="submit">Delete listing</button>
  <a href="{% url 'my_listings' %}">Cancel</a>
</form>
```

### Profile — `/accounts/`

Context: `form` (`ProfileForm`), `cooldown_ends` (datetime or `None`; always
`None` for staff).

`ProfileForm` contains only `avatar`. Use `enctype="multipart/form-data"` and
`{% csrf_token %}`. Success: "Your profile photo was updated." and redirect to
`profile`. A non-image renders Django's "Upload a valid image..." error with
status 200. An avatar larger than 5 MiB renders "Choose an image smaller than
5 MB." Replacing an avatar deletes the old file after the new one commits.

Useful values:

```django
{{ user.get_full_name|default:user.email }}
{{ user.email }}
{{ user.profile.get_role_display }}
{{ user.profile.phone }}
{{ user.profile.location }}
{{ user.profile.avatar_url }}
{{ user.profile.email_notifications }}
{{ user.profile.sms_notifications }}
{% if cooldown_ends %}{{ cooldown_ends|date:"M j, Y" }}{% endif %}
```

Role, phone, location, and notification flags are not editable through any
frontend form yet.

Avatar include:

```django
{% include 'partials/avatar.html' with avatar_user=user %}
```

### Change username — `/accounts/username/`

Context: `form` (`UsernameChangeForm`), `cooldown_ends`.

If `cooldown_ends` is set, hide the form and show the date; the view ignores a
POST during cooldown. On success redirect to `profile` with a success message.
Validation failures render the form with errors.

### Social signup start — `/accounts/social/<provider>/start/<role>/`

- `GET` only; public; no template.
- `<role>` must be `buyer` or `farmer`.
- `<provider>` must be an installed allauth provider with a `<provider>_login`
  URL; `google` is the only one installed.
- A provider that is installed but has no credentials returns 404.
- The view stores the role in the session and redirects to the provider login
  URL. `SOCIALACCOUNT_LOGIN_ON_GET` is on, so the redirect reaches Google
  directly instead of allauth's intermediate "Continue" page.
- Google buttons appear only when both credentials are set.

Use this link when the visitor must choose a role before Google signup:

```django
<a href="{% url 'social_signup_start' 'google' 'farmer' %}">
  Sign up with Google as a farmer
</a>
```

`templates/account/signup.html` renders one link per role.
`templates/account/login.html` renders a plain "Sign in with Google" link for
returning users.

### Placeholder pages — `/chat/`, `/notifications/`

Context: none. Both are `GET` only and login-gated. They are static
placeholders with no models or logic yet. Keep them login-gated so adding real
data later cannot expose it to anonymous visitors.

### Authentication pages

allauth owns these routes under `/accounts/`:

| URL name | Purpose |
| --- | --- |
| `account_login` | Email/password login |
| `account_signup` | Signup with role choice |
| `account_logout` | Logout |
| `account_reset_password` | Password reset request |
| `account_email` | Email management |
| `account_email_verification_sent` | Verification instructions |
| `google_login` | Start Google login |

Login is by email only; email verification is mandatory. An unverified account
is redirected to `account_email_verification_sent`. `LOGIN_REDIRECT_URL` is
`/listings/`. Development uses the console email backend; production requires
SMTP.

Signup form (`accounts.forms.SignupForm`):

| Field | Values | Notes |
| --- | --- | --- |
| `role` | `buyer`, `farmer` | Radio buttons, "Account type", defaults to buyer, required |
| `username` | text | Optional; "Username (optional)"; 3–30 characters; generated when blank |
| `email` | email | Required and unique; login identifier |
| `password1`, `password2` | password | Standard Django validation |

Field order: `role`, `username`, `email`, `password1`, `password2`.

Social signup form (`accounts.forms.SocialSignupForm`): `role`, `username`,
`email`, in that order; `username` is required here. It appears because
`SOCIALACCOUNT_AUTO_SIGNUP` is off. The role chosen at `social_signup_start` is
preloaded from the session. A Google account whose email matches an existing
local account is linked automatically and skips this form.

## Pagination

Browse, saved, and farmer dashboard provide `page_obj` with 24 items per page.

| Attribute | Meaning |
| --- | --- |
| `page_obj.number` | Current page |
| `page_obj.paginator.num_pages` | Total pages |
| `page_obj.has_previous` | Whether a previous page exists |
| `page_obj.previous_page_number` | Previous page number |
| `page_obj.has_next` | Whether a next page exists |
| `page_obj.next_page_number` | Next page number |

Django 6.1's `{% querystring %}` preserves current filters while replacing
`page`:

```django
{% if page_obj.has_previous %}
  <a href="{% querystring page=page_obj.previous_page_number %}">Previous</a>
{% endif %}
<span>Page {{ page_obj.number }} of {{ page_obj.paginator.num_pages }}</span>
{% if page_obj.has_next %}
  <a href="{% querystring page=page_obj.next_page_number %}">Next</a>
{% endif %}
```

## Model reference

### Listing

| Field | Type / choices | Notes |
| --- | --- | --- |
| `public_id` | UUID | Use in URLs, not numeric `id` |
| `farmer` | FK `User` | `listing.farmer` |
| `category` | FK `Category` | `listing.category.name`, `.slug`; protected from deletion while listings use it |
| `title` | char(120) | |
| `condition` | `fresh`, `ripe`, `blemished`, `overripe`, `processing` | Use `get_condition_display` |
| `description` | text | |
| `price` | decimal(10,2), nullable | `None` for free; minimum `0.01` |
| `is_free` | boolean | Must agree with `price is null` |
| `unit` | `kg`, `g`, `sack`, `piece`, `bunch`, `crate`, `tray`, `box`, `liter`, `dozen` | Use `get_unit_display` |
| `stock_quantity` | decimal(10,2) | Never negative; default `1`; active requires stock, sold-out clears it |
| `bulk_order` | boolean | |
| `meetup` | boolean | |
| `meetup_location` | char(255) | Required when `meetup` is true |
| `meetup_notes` | text | |
| `direct_to_market` | boolean | |
| `delivery` | boolean | |
| `status` | `draft`, `active`, `sold_out`, `archived` | Use `get_status_display` |
| `status_note` | char(255) | Restock note |
| `sold_out_at` | datetime, nullable | Set when entering sold-out, cleared when leaving; not in `ListingForm` |
| `created_at`, `updated_at` | datetime | |

Helpers:

- `listing.cover_image` returns the first `ListingImage` by `position`, using
  the prefetch cache.
- `listing.images.all` returns all photos ordered by `position`, then `id`.
- `listing.likes_total` exists only on annotated querysets.

Limits: 5 photos (`Listing.MAX_IMAGES`), 25 open listings, 10 creations per
rolling 24 hours.

### Category

`name` (unique) and `slug` (unique, generated from the name when blank). Use
`category.slug` for the `category` query parameter. Seeded categories: Rice,
Corn, Tomato, Eggplant, Banana, Mango, Coconut, Leafy Greens.

### ListingImage

`listing`, `image`, `position` (small integer), `alt_text` (optional, max 200).
`image.url` is the display URL: local `/media/` in development, Supabase
Storage in production.

### ListingLike

`user`, `listing`, `created_at`, with a unique `user` + `listing` constraint.

### User and Profile

`User` has a unique `email`, an internal `username`, `username_changed_at`,
and a one-to-one `profile`. `Profile` has `role`, `phone`, `location`,
`email_notifications`, `sms_notifications`, `avatar`, `avatar_url`,
`created_at`, and `updated_at`.

## Styling and accessibility

- Tailwind CSS v4 through the npm CLI. Input: `assets/css/input.css`. Output:
  `static/css_output/output.css`, loaded by `base.html`.
- `npm run watch` rebuilds on change; `npm run build` builds once.
- Theme tokens: `mist` (`#E8EDF2`) page background, `paper` (`#FFFFFF`)
  cards, `ink` (`#1D1A1A`) text, `leaf` (`#8DB355`) and `leaf-deep`
  (`#7C9B46`) primary actions, `mute` (`#8B8E91`) secondary text, font
  `Inter`, and text sizes `text-h1` through `text-h6`, `text-body`,
  `text-small`. The older `bg` (`#000000`) and `fg` (`#F6F8F9`) tokens are
  still defined but no longer used by the templates.
- The whole site is light-themed: `base.html` body is `bg-mist text-ink`,
  the header is `bg-paper` with a `border-mist` bottom edge, nav CTAs are
  leaf pills, cards are `rounded-2xl border border-mist bg-paper shadow-sm`,
  inputs are `rounded-xl` with `border-mist` and a leaf focus ring, and
  selects opt into the custom chevron with the `form-select` class
  (`input.css`). The listing form ("List an item" sheet) uses the same
  tokens; its toggles, pills, and photo previews are styled by component
  rules in `input.css` under the `#listing-form` scope. The CSP report-only
  policy allows `connect-src` to Nominatim and Overpass for the form's
  geocoding and nearby-markets lookups; keep those entries if the CSP is
  enforced.
- Below 640px, `input.css` shrinks `h1`/`h2`, pads `body`, and pads
  `.container`. `.data-table` cells shrink below 768px.
- Any class not already in `output.css` renders unstyled until you rebuild.
- Use semantic landmarks, labels, and alt text. The like button uses
  `aria-pressed`. Messages render in a `role="status"` region.
- Do not hard-code a second color palette. Extend the existing tokens in
  `assets/css/input.css` if the design needs more.
- `Inter` is declared in the theme but not loaded by `base.html`. Confirm with
  design before relying on it; if it must load, account for the CSP and
  performance cost.

## Forms and security checklist

- Every POST form needs `{% csrf_token %}`.
- Photo forms need `enctype="multipart/form-data"`.
- Render `form.non_field_errors` and per-field errors, or use `{{ form.as_p }}`.
- Keep the `name` attributes produced by Django; do not rename form fields.
- Use `{% url %}` names, not hard-coded paths.
- Do not expose `listing.id`; use `listing.public_id`.
- Keep the `next` parameter on login links when a page is protected.
- Show `messages`; `base.html` already does.
- Do not add a second header, navigation, or logout form.

## Status and permission reference

| Situation | Result |
| --- | --- |
| Anonymous opens a protected page | 302 to `/accounts/login/?next=...` |
| Signed-in buyer opens a farmer-only page | 403 |
| Signed-in non-owner opens edit/delete | 404 |
| Anyone opens a non-public listing they do not own | 404 |
| Authenticated `GET` on the like endpoint | 405 |
| Anonymous request on the like endpoint | 302 to login |
| Missing CSRF token on a POST | 403 |
| Invalid listing/profile POST | 200 with form errors |
| Unverified email tries to log in | 302 to `account_email_verification_sent` |
| Successful create/edit/delete/profile action | 302 with a success message |

403 and 404 use Django's default error pages; there are no custom `403.html`
or `404.html`.

## Test contract

Run:

```bash
python manage.py test --settings=config.settings_test
```

The suite covers `accounts`, `listings`, and `config`. These assertions encode
product behavior; do not weaken them to make a UI change pass:

- Browse and detail contain the listing title, description, `₱100.00` price
  format, meet-up location, and seller username.
- Sold-out listings show `Sold out` and `status_note` on detail, saved, and
  dashboard pages.
- An owner viewing their own draft sees `Your listing is currently draft.`
- The like button shows `♥ Saved` after saving and `♡ Save` otherwise.
- The saved page shows `2 likes` when two users liked a listing.
- The create form shows `Add at least one photo.` on a missing photo.
- Detail pages render `image.image.url` for the cover.
- Signup contains `Account type`, `Buyer`, `Farmer`, and
  `Username (optional)`.
- Allauth pages contain `Sign In`, `Signup`, and `Password Reset`.
- The htmx like response uses `listings/_like_button.html` with `is_liked`.
- Browse exposes `page_obj` with 24 items on page one.
- Social signup start returns 404 when the provider has no credentials.
- The signup page links Google through `social_signup_start` for each role.
- Navigation shows "Sell produce" and "My listings" only for farmers.

## Backend conventions

Only change Python when the task requires it. Follow the existing patterns.

- **Views:** function-based views with decorators (`@login_required`,
  `@require_POST`, `@require_http_methods`, `@farmer_required`). Keep URL names
  and view function names stable.
- **Queries:** use `select_related`, `prefetch_related`, and annotations to
  avoid N+1 queries. Browse, detail, and saved select-relate
  `farmer__profile` so seller avatars cost no extra query. Use
  `with_likes_total` for like counts; it is a correlated subquery, not a join.
- **Transactions:** use `transaction.atomic` and `select_for_update` for
  limits, edits, and multi-row writes. Do not check a limit outside the lock.
- **Validation:** put rules in forms and models; database constraints are the
  backstop. Do not bypass `full_clean` or the constraints from scripts.
- **Files:** delete replaced or removed files with `transaction.on_commit` and
  `robust=True`. Never delete a file before the database change commits.
- **Images:** re-encode uploads through Pillow; strip EXIF/GPS; enforce size
  and pixel limits before decoding.
- **Migrations:** one logical change per migration. Run
  `makemigrations --check --dry-run`. Use `config.settings_direct` for remote
  schema changes.
- **Settings:** read configuration from environment variables; fail fast on
  missing production values. Never commit secrets.
- **Admin:** custom user admin, read-only username history and likes, listing
  image inline, `likes_total` annotation on the listing changelist.

## Decision guide

### Decide on your own

- Markup, Tailwind classes, responsive layout, and accessibility.
- Extracting or reusing template partials.
- Empty states, loading states, and visual polish.
- Query optimizations that preserve behavior.
- Tests for existing behavior.
- Bug fixes that restore documented behavior.

### Ask the human first

- Changing pricing, roles, permissions, search semantics, listing limits, or
  status rules.
- Renaming URL names, context variables, form fields, or template paths.
- Adding a dependency, API, SPA, Celery, Channels, or Redis.
- Changing authentication, CSP, deployment, or security settings.
- Deleting data, models, or templates.
- Large refactors or design-system changes.
- Changing a test because the product behavior changed.

### Common task playbooks

**Visual-only change**

1. Read the current template and its view.
2. Edit the template and/or Tailwind classes.
3. Preserve URL names, context variables, form field names, and test strings.
4. Run the relevant tests.
5. Run `npm run build` and commit the rebuilt CSS.

**New page**

1. Add the URL name and view following existing permission patterns.
2. Add the template under `templates/`, extending `base.html`.
3. Add the context the template needs, with query optimization.
4. Add tests for anonymous, buyer, farmer, and owner behavior as applicable.
5. Document the route and context in this file.

**New data on an existing page**

1. Add it to the view context, not a template query.
2. Use `select_related`/`prefetch_related`/annotations.
3. Document the variable in this file.
4. Add or update a test.

**Form change**

1. Update the form, template, tests, and this file together.
2. Do not rename existing fields; they are the POST contract.
3. Keep CSRF and multipart settings.
4. Check validation messages and error rendering.

**New dependency**

1. Check whether Django or an existing package already covers it.
2. If not, pin it in `requirements.txt`, run `pip-audit`, and document why.
3. Do not add infrastructure packages to `requirements.txt` until code imports
   them.

**Auth change**

1. Preserve email verification, role selection, and optional Google login.
2. Test both email and Google flows.
3. Check the `social_signup_start` role/session behavior.
4. Do not weaken the provider-credentials check or the direct-login setting
   without documenting the tradeoff.

## Known traps

- `likes_total` exists only on querysets annotated by the browse, detail,
  saved, or farmer dashboard views.
- `listing.cover_image` relies on the prefetched `images` cache. A listing
  fetched without `prefetch_related("images")` can query per card.
- `user.profile.avatar_url` is cached per profile instance. Clear the cache
  after replacing or clearing an avatar; `ProfileForm` already does this.
- `user.profile` is only safe for authenticated users. Check
  `user.is_authenticated` first.
- `DEBUG=True` auto-login hides real login redirects and 403/404 responses.
  Test permissions with `DEBUG=False`.
- After anonymous login from the like endpoint's redirect, the browser sends a
  `GET` to the like URL and gets 405. Link anonymous visitors to login with
  `next` set to the listing detail page.
- Search matches the farmer's internal username, so a query can surface a
  listing by a handle the UI does not show.
- `my_listings` select-relates `category`; browse, detail, and saved also
  select-relate `farmer__profile`.
- Replacing or clearing a profile photo deletes the previous file after the
  change commits. Deleting a profile or user removes the stored avatar too.
- `base.html` owns the navigation and logout form. "Sell produce" is only for
  signed-in farmers.
- `static/css_output/output.css` is generated. Never hand-edit it; CI fails if
  it is stale.
- `templates/bare.html` is only for temporary pages. Marketplace pages extend
  `base.html`.
- Supabase's direct connection (port 5432) is IPv6-only. On IPv4-only
  networks, use the session pooler string for `DIRECT_URL`.
- Public Supabase buckets use permanent object URLs; private buckets use
  signed URLs. A wrong `SUPABASE_S3_REGION` causes `SignatureDoesNotMatch`.
- CSP starts in report-only mode. Adding external images or scripts requires
  updating the policy before enforcing it.
- The admin path is configurable and should be restricted at the proxy.
- `Inter` is declared in the Tailwind theme but not loaded by `base.html`.

## Git and CI

- Branch from the latest `origin/main` as `<area>/<topic>`, for example
  `frontend/listing-cards` or `fix/like-redirect`.
- Commit messages use an area prefix and an imperative summary:
  `ui:`, `listings:`, `accounts:`, `fix:`, `perf:`, `security:`, `docs:`,
  `ci:`, `chore:`.
- Explain *why* in the commit body, including tradeoffs.
- Open a pull request against `main`; do not push directly to `main`.
- Keep pull requests focused. Update this file when the contract changes.
- CI runs the test suite, checks for missing migrations, builds CSS and fails
  if the committed output is stale, runs `check --deploy`, collects static
  files, and audits `requirements.txt` with `pip-audit`.
- Dependabot and CodeQL are configured in `.github/`.

## Definition of done

- [ ] Tests pass with `config.settings_test`.
- [ ] New behavior has tests; existing product assertions still pass.
- [ ] `npm run build` run and `static/css_output/output.css` committed.
- [ ] `makemigrations --check --dry-run` passes.
- [ ] Permissions verified for anonymous, buyer, farmer, and owner.
- [ ] Responsive and keyboard-accessible.
- [ ] CSRF, multipart, and error rendering correct on every form.
- [ ] No secrets, database files, uploaded media, or `node_modules/` staged.
- [ ] Contract changes documented in this file.
- [ ] Commit message explains the decision, not just the diff.

## Historical reference

The deleted `docs/frontend-instructions.md` is available in git history:

```bash
git show de85ead:docs/frontend-instructions.md
```

The marketplace templates are present in `templates/`. For earlier variants,
use `git log -- templates/` and `git show <commit>:<path>`.
