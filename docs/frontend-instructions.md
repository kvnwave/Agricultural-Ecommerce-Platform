# Frontend handoff instructions

This document lists every route and the exact variables each view passes, so
the frontend can be rebuilt or changed without backend changes. The Django
views, URLs, models, forms, permissions, and authentication flow are the
contract; the markup is not.

On this branch the marketplace templates have been removed: `templates/` now
holds only `base.html`, the account pages, and the allauth shells. The old
templates remain in git history (see [Old templates for reference](#old-templates-for-reference)).

## Current state

- Marketplace templates were removed. `listings/`, `chat/`, `analytics/`, and
  `notifications/` template paths are empty, and the `listings/` partials
  (`_listing_card.html`, `_like_button.html`) and `partials/pagination.html`
  were removed with them.
- The account pages still work: `templates/accounts/accounts.html`,
  `templates/accounts/username_change.html`, and `templates/partials/avatar.html`
  are kept, and `base.html`, `templates/account/`, and
  `templates/socialaccount/` remain.
- Tailwind source, built CSS, htmx, and npm files stay in place. `base.html`
  loads `static/css_output/output.css` and `static/js/htmx.min.js`, so the
  `hx-*` attributes used by the like partial work once that partial is
  recreated.
- `static/css_output/output.css` is a build artifact generated from
  `assets/css/input.css`. Run `npm run build` after adding or changing
  Tailwind classes; until then, classes that are not already in the built file
  render unstyled.
- Marketplace routes raise `TemplateDoesNotExist` until a template is created
  at the path listed below. The account routes render normally.
- The test suite was intentionally left in place. Tests that render a removed
  template fail until the templates are restored.

## How templates connect

Django looks for templates in `templates/` first, then in installed apps. The
project setting is already in place:

```python
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        ...
    }
]
```

To reconnect or replace a page:

1. Create or edit the file at the exact path in the [template map](#template-map).
2. Start it with `{% extends "base.html" %}`.
3. Fill `{% block content %}`. `base.html` also exposes `title`, `extra_head`,
   and `extra_body` blocks.
4. Use `{% url "name" %}` with the URL names in this document instead of
   hard-coding paths.
5. Add `{% csrf_token %}` inside every POST form.
6. Add `enctype="multipart/form-data"` to forms that upload a profile photo or
   listing photos.

Minimal page:

```django
{% extends "base.html" %}

{% block title %}Browse produce{% endblock %}

{% block content %}
  <h1>Browse produce</h1>
  {% for listing in listings %}
    <a href="{% url 'listing_detail' listing.public_id %}">
      {{ listing.title }}
    </a>
  {% empty %}
    <p>No listings yet.</p>
  {% endfor %}
{% endblock %}
```

## Global context

These variables are available on every template through Django's context
processors (`request`, `auth`, `messages`) and the CSRF tag:

| Variable | Type | Notes |
| --- | --- | --- |
| `user` | `accounts.User` or `AnonymousUser` | Check `user.is_authenticated` before reading `user.profile`; anonymous requests have no profile row. |
| `messages` | message list | Success and error feedback from the views and allauth. `base.html` already renders it above `{% block content %}`. |
| `request` | `HttpRequest` | Useful for `request.path` when building a `next` parameter. |
| `csrf_token` | token | Use `{% csrf_token %}` inside forms. |

`user.profile` fields: `role` (`farmer` / `buyer`), `phone`, `location`,
`email_notifications`, `sms_notifications`, `avatar`, `avatar_url`,
`created_at`, `updated_at`, and `get_role_display`. `user.email`,
`user.get_full_name`, and `user.username` come from the custom user model.
`user.username` is an internal handle; signup can generate one, but the signup
form also exposes an optional username field. Show
`user.get_full_name|default:user.email` on marketplace pages for the signed-in
user. Seller names use `listing.farmer.get_full_name|default:listing.farmer.username`
in the old templates.

Profiles are created by a `post_save` signal on `User`, so `user.profile` is
always present for signed-in users.

## Route contract

### Route summary

| Path | URL name | Methods | Access | Template |
| --- | --- | --- | --- | --- |
| `/` | `home` | GET | Public | Redirects to `/listings/` |
| `/listings/` | `listings` | any (use GET) | Public | `listings/listings.html` |
| `/listings/<uuid>/` | `listing_detail` | any (use GET) | Public, with an owner exception | `listings/listing_detail.html` |
| `/listings/<uuid>/like/` | `listing_like_toggle` | POST | Signed in | `listings/_like_button.html` (htmx) or redirect |
| `/listings/liked/` | `liked_listings` | any (use GET) | Signed in | `listings/liked_listings.html` |
| `/listings/mine/` | `my_listings` | any (use GET) | Farmer | `listings/my_listings.html` |
| `/listings/new/` | `listing_create` | GET, POST | Farmer | `listings/listing_form.html` |
| `/listings/<uuid>/edit/` | `listing_update` | GET, POST | Owner | `listings/listing_form.html` |
| `/listings/<uuid>/delete/` | `listing_delete` | GET, POST | Owner | `listings/listing_confirm_delete.html` |
| `/accounts/` | `profile` | GET, POST | Signed in | `accounts/accounts.html` |
| `/accounts/username/` | `username_change` | GET, POST | Signed in | `accounts/username_change.html` |
| `/accounts/social/<provider>/start/<role>/` | `social_signup_start` | GET | Public | Redirects to the provider |
| `/chat/` | `chat` | any (use GET) | Public | `chat/chat.html` |
| `/analytics/` | `analytics` | any (use GET) | Public | `analytics/analytics.html` |
| `/notifications/` | `notifications` | any (use GET) | Public | `notifications/notifications.html` |
| `/control-panel/` | `admin:index` | GET | Staff | Django admin (path configurable with `DJANGO_ADMIN_PATH`) |

Allauth owns everything under `/accounts/` that is not listed above: login,
signup, logout, email verification, password reset, email management, and
social login. Those pages already render and need no new templates.

Access behaviour in the table:

- "Signed in" uses `@login_required`. Anonymous requests are redirected to
  `/accounts/login/?next=<original path>`.
- "Farmer" uses `@login_required` plus a role check. A signed-in buyer gets
  `403 Forbidden`.
- "Owner" uses a queryset filtered by `farmer=request.user`. Any other
  signed-in user, including buyers, gets `404 Not Found`. `listing_update` and
  `listing_delete` do not check the farmer role; ownership is the only check.

### Browse listings — `/listings/`

- View: `listings.views.listings_view`
- URL name: `listings`
- Methods: any (the view does not restrict methods; use `GET`)
- Access: public
- Template: `listings/listings.html`
- Page size: 24
- Ordering: newest first (`-created_at`)
- Only listings whose status is `active` or `sold_out` are included.

Query parameters:

| Parameter | Values | Behaviour |
| --- | --- | --- |
| `q` | text, trimmed to 100 characters | One case-insensitive substring match (`icontains`). The whole value must appear in the title, description, category name, farmer first name, farmer last name, or farmer username. It is not split into words, and there is no fuzzy matching or similarity ranking. |
| `category` | `Category.slug` | Exact category match. An unknown slug returns an empty list. |
| `condition` | `fresh`, `ripe`, `blemished`, `overripe`, `processing` | Exact condition match; unknown values are ignored. |
| `pricing` | `free` or `paid` | Filters on `is_free`; other values are ignored. |
| `page` | integer | Pagination page. A non-integer falls back to page 1; an out-of-range number falls back to the last page. |

Context:

| Variable | Type | Notes |
| --- | --- | --- |
| `page_obj` | Django `Page` | Paginated listings. |
| `listings` | `page_obj.object_list` | The current page's listings. Each one has a `likes_total` annotation, plus `category` and `farmer` select-related and `images` prefetched. |
| `categories` | `QuerySet[Category]` | All categories, ordered by name. |
| `conditions` | list of `(value, label)` | `Listing.Condition.choices`. |
| `pricing_options` | tuple of `(value, label)` | `(("free", "Free"), ("paid", "Paid"))`. |
| `query` | string | The submitted `q` value after trimming and truncation. |
| `selected_category` | string | The submitted `category` slug, trimmed. |
| `selected_condition` | string | The submitted `condition` value, trimmed. Present even when invalid and ignored. |
| `selected_pricing` | string | The submitted `pricing` value, trimmed. |

Use `{% url 'listing_detail' listing.public_id %}` for each card,
`{% url 'liked_listings' %}` for saved listings, and
`{% url 'my_listings' %}` for the seller dashboard.

### Listing detail — `/listings/<uuid>/`

- View: `listings.views.listing_detail`
- URL name: `listing_detail`
- Methods: any (use `GET`)
- Access: public for `active` and `sold_out` listings. Owners can also view
  their own `draft` and `archived` listings. Everyone else gets 404.
- Template: `listings/listing_detail.html`

Context:

| Variable | Type | Notes |
| --- | --- | --- |
| `listing` | `Listing` | Includes a `likes_total` annotation and prefetched `images`. |
| `is_owner` | boolean | True when the signed-in user is `listing.farmer`. |
| `can_like` | boolean | True when the status is `active` or `sold_out`. |
| `is_liked` | boolean | True when the signed-in user has saved this listing. Always false for anonymous users. |

Useful listing values in the template:

```django
{{ listing.title }}
{{ listing.category.name }}
{{ listing.get_condition_display }}
{{ listing.get_status_display }}
{{ listing.get_unit_display }}
₱{{ listing.price|floatformat:2 }}   {# show "Free" instead when listing.is_free #}
{{ listing.stock_quantity|floatformat:"-2" }}
{{ listing.bulk_order }}
{{ listing.status_note }}
{{ listing.description|linebreaks }}
{{ listing.meetup }} / {{ listing.meetup_location }} / {{ listing.meetup_notes }}
{{ listing.direct_to_market }} / {{ listing.delivery }}
{{ listing.farmer.get_full_name|default:listing.farmer.username }}
{{ listing.likes_total }}
```

Prices are in Philippine pesos (PHP) per `unit`.

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

The login link for anonymous visitors should preserve the return path:

```django
<a href="{% url 'account_login' %}?next={{ request.path|urlencode }}">
  Log in to save this listing
</a>
```

### Like / save toggle — `/listings/<uuid>/like/`

- View: `listings.views.listing_like_toggle`
- URL name: `listing_like_toggle`
- Methods: `POST` only. An authenticated `GET` returns 405.
- Access: signed in. Any anonymous request, including `POST`, redirects to
  login with `next` set to the like URL.
- Only `active` and `sold_out` listings can be liked. A missing or non-public
  listing returns 404.

Behaviour:

- Creates the `ListingLike` if it does not exist; deletes it if it does.
- When the request has `HX-Request: true` (htmx), the view renders
  `listings/_like_button.html` with `listing` (carrying a fresh `likes_total`)
  and `is_liked`.
- Otherwise it redirects to `listing_detail` for the same listing, regardless
  of which page the form was on.

Form:

```django
<form method="post" action="{% url 'listing_like_toggle' listing.public_id %}">
  {% csrf_token %}
  <button type="submit" aria-pressed="{{ is_liked|yesno:'true,false' }}">
    {% if is_liked %}♥ Saved{% else %}♡ Save{% endif %}
    <span>{{ listing.likes_total }}</span>
  </button>
</form>
```

For htmx behaviour, keep the `hx-post`, `hx-target="this"`, and
`hx-swap="outerHTML"` attributes from the old partial (in git history). htmx
itself is already loaded by `base.html`, so no script change is needed.
Without those attributes, the normal form POST still works.

### Saved listings — `/listings/liked/`

- View: `listings.views.liked_listings`
- URL name: `liked_listings`
- Methods: any (use `GET`)
- Access: signed in
- Template: `listings/liked_listings.html`
- Page size: 24
- Includes saved listings with status `active` or `sold_out`, newest save
  first. Each listing has a `likes_total` annotation counting likes from all
  users.

Context: `page_obj`, `listings`. The listings include `category` and `farmer`
select-related and `images` prefetched.

### Farmer dashboard — `/listings/mine/`

- View: `listings.views.my_listings`
- URL name: `my_listings`
- Methods: any (use `GET`)
- Access: signed-in farmer
- Template: `listings/my_listings.html`
- Page size: 24
- Includes every status: `draft`, `active`, `sold_out`, and `archived`.
  Newest first. Each listing has `likes_total`.
- `category` is select-related, so `listing.category.name` does not add a query
  per listing.

Context: `page_obj`, `listings`.

### Create listing — `/listings/new/`

- View: `listings.views.listing_create`
- URL name: `listing_create`
- Methods: `GET`, `POST`
- Access: signed-in farmer
- Template: `listings/listing_form.html`

Limits checked before the form is shown and again atomically on POST:

- At most 25 open listings. Archived listings do not count toward this limit.
- At most 10 listings created in a rolling 24-hour window.

When a limit is hit, the view adds an error message and redirects to
`my_listings`; it does not render the form. On a valid POST the view sets
`farmer` to the current user, saves the listing and its photos, adds the
message "Your listing has been created.", and redirects to `my_listings`. An
invalid POST re-renders the form with status 200.

Context:

| Variable | Type | Notes |
| --- | --- | --- |
| `form` | `ListingForm` | Bound form on an invalid POST, unbound on GET. |
| `is_edit` | boolean | Always `False` for this view. |

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
also render `form.non_field_errors`.

`ListingForm` fields, in display order:

| Field | Widget / values | Rules |
| --- | --- | --- |
| `title` | text | Required, max 120 characters. |
| `category` | select of `Category` | Required. |
| `condition` | select: `fresh`, `ripe`, `blemished`, `overripe`, `processing` | Required, defaults to `fresh`. |
| `description` | textarea | Required. |
| `price` | decimal | At least `0.01`. Required when `is_free` is unchecked; must be empty when `is_free` is checked. |
| `is_free` | checkbox | Default unchecked. |
| `unit` | select: `kg`, `g`, `sack`, `piece`, `bunch`, `crate`, `tray`, `box`, `liter`, `dozen` | Required, defaults to `kg`. |
| `stock_quantity` | decimal | At least `0`, defaults to `0`. |
| `bulk_order` | checkbox | Accept larger orders than the listed stock. |
| `meetup` | checkbox | Requires `meetup_location` when checked. |
| `meetup_location` | text | Max 255 characters. Required when `meetup` is checked. |
| `meetup_notes` | textarea | Optional. |
| `direct_to_market` | checkbox | Optional. |
| `delivery` | checkbox | Optional. |
| `status` | select: `draft`, `active`, `sold_out`, `archived` | Required, defaults to `active`. |
| `status_note` | text | Max 255 characters; used for restock notes. |
| `images` | multiple file input (`accept="image/*"`) | At least one photo is required in total. |
| `remove_images` | multiple checkbox | Only present when editing an existing listing. |

Validation messages the form produces:

- `Add at least one photo.` (field `images`)
- `Add at most 5 photos.` (field `images`)
- `Each photo must be smaller than 5 MB.` (field `images`)
- `Free listings cannot have a price.` (field `price`)
- `Set a price or mark the listing as free.` (field `price`)
- `Add the meet-up location.` (field `meetup_location`)

Photo rules:

- At most 5 photos per listing, counting remaining existing photos plus new
  ones.
- A photo larger than 5 MiB is rejected.
- JPEG, PNG, and WebP only. The form re-encodes each upload, stripping metadata
  such as EXIF and GPS.
- Photos above 25 megapixels are rejected before re-encoding
  (`Image.MAX_IMAGE_PIXELS`).
- The request accepts at most 10 uploaded files (`DATA_UPLOAD_MAX_NUMBER_FILES`).
- The lowest `position` is the cover. New photos are appended after the
  highest existing `position`. Removing a photo does not renumber the rest.
- `alt_text` has no form field. It can be set only in the admin; templates fall
  back to the listing title.
- Photos are written to storage under
  `listings/<listing.public_id>/<uuid>.<ext>`.

### Edit listing — `/listings/<uuid>/edit/`

- View: `listings.views.listing_update`
- URL name: `listing_update`
- Methods: `GET`, `POST`
- Access: signed-in owner. Non-owners get 404.
- Template: `listings/listing_form.html`

On POST the view locks the listing row inside a transaction before validating,
so two concurrent edits cannot both pass the minimum-photo check.

Context:

| Variable | Type | Notes |
| --- | --- | --- |
| `form` | `ListingForm` | Includes a `remove_images` field with the listing's current photos as choices. |
| `listing` | `Listing` | The listing being edited. After an invalid POST its in-memory fields hold the submitted values, not the saved ones. |
| `is_edit` | boolean | Always `True` for this view. |

Show existing photos and let the user tick `remove_images` choices. The form
still requires at least one photo after removals, and the 5-photo limit applies
to the total of remaining plus new photos. On success the view adds the message
"Your listing has been updated." and redirects to `my_listings`.

### Delete listing — `/listings/<uuid>/delete/`

- View: `listings.views.listing_delete`
- URL name: `listing_delete`
- Methods: `GET` (confirmation), `POST` (delete). Other methods return 405.
- Access: signed-in owner. Non-owners get 404.
- Template: `listings/listing_confirm_delete.html`
- Context: `listing`.
- `POST` deletes the listing, its likes, and its photo rows, adds the message
  "Your listing has been deleted.", and redirects to `my_listings`. Photo files
  are removed from storage after the transaction commits.

```django
<form method="post">
  {% csrf_token %}
  <p>Delete “{{ listing.title }}”? This cannot be undone.</p>
  <button type="submit">Delete listing</button>
  <a href="{% url 'my_listings' %}">Cancel</a>
</form>
```

### Profile — `/accounts/`

- View: `accounts.views.profile_view`
- URL name: `profile`
- Methods: `GET`, `POST`
- Access: signed in
- Template: `accounts/accounts.html`
- Context: `form` (`ProfileForm`), `cooldown_ends` (datetime or `None`; always
  `None` for staff).

`ProfileForm` contains only `avatar`. Use `enctype="multipart/form-data"` and
`{% csrf_token %}`. A successful upload adds the message "Your profile photo
was updated." and redirects to `profile`. A non-image renders the form with
Django's "Upload a valid image..." error and status 200. An avatar larger than
5 MiB renders "Choose an image smaller than 5 MB." When an avatar is replaced,
the old file is deleted after the new one commits.

Useful profile values:

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

`user.profile.avatar_url` returns the uploaded avatar first, then the Google
picture from a linked social account, then an empty string. Role, phone,
location, and the notification flags are not editable through any frontend
form yet.

The `partials/avatar.html` include renders the avatar or an initial:

```django
{% include 'partials/avatar.html' with avatar_user=user %}
```

### Change username — `/accounts/username/`

- View: `accounts.views.username_change`
- URL name: `username_change`
- Methods: `GET`, `POST`
- Access: signed in
- Template: `accounts/username_change.html`
- Context: `form` (`UsernameChangeForm`), `cooldown_ends` (datetime or `None`).

Rules:

- 3–30 characters.
- Only letters, numbers, underscores, and hyphens.
- Must start and end with a letter or number.
- Compared case-insensitively and stored lowercase.
- Reserved names such as `admin`, `support`, `farmer`, and `buyer` are
  rejected.
- The first change is immediate. Later changes have a 7-day cooldown.
- Staff bypass the cooldown.

If `cooldown_ends` is set, hide the form and show the date; the view ignores a
POST during the cooldown and renders the page again. On success it redirects to
`profile` with a success message. Validation failures render the form with
errors.

### Social signup start — `/accounts/social/<provider>/start/<role>/`

- View: `accounts.views.social_signup_start`
- URL name: `social_signup_start`
- Methods: `GET` only
- Access: public
- Context: none; redirects on success (invalid roles or providers return 404).
- `<role>` must be `buyer` or `farmer`. `<provider>` must be an installed
  allauth provider with a `<provider>_login` URL; `google` is the only one
  installed. Unknown values return 404.
- The view stores the chosen role in the session and redirects to allauth's
  provider login URL. The Google button works only when `GOOGLE_CLIENT_ID` and
  `GOOGLE_CLIENT_SECRET` are set.

Use this link when the visitor must choose a role before Google signup:

```django
<a href="{% url 'social_signup_start' 'google' 'farmer' %}">
  Sign up with Google as a farmer
</a>
```

### Placeholder pages — `/chat/`, `/analytics/`, `/notifications/`

- Views: `chat.views.chat_view`, `analytics.views.analytics_view`,
  `notifications.views.notifications_view`
- URL names: `chat`, `analytics`, `notifications`
- Methods: any (use `GET`)
- Access: public (no login check)
- Context: none
- Templates: `chat/chat.html`, `analytics/analytics.html`,
  `notifications/notifications.html`

These are static placeholder pages with no models or logic yet.

### Authentication pages

allauth owns these routes under `/accounts/`:

| URL name | Purpose |
| --- | --- |
| `account_login` | Email/password login |
| `account_signup` | Signup with the marketplace role choice |
| `account_logout` | Logout |
| `account_reset_password` | Password reset request |
| `account_email` | Email management |
| `account_email_verification_sent` | Verification instructions (served at `/accounts/confirm-email/`) |
| `google_login` | Start Google login |

Account settings: login is by email only, and email verification is
mandatory. An unverified account that tries to log in is redirected to
`account_email_verification_sent`. `LOGIN_REDIRECT_URL` is `/listings/`.
Development (`DEBUG=True`) uses Django's console email backend, so verification
emails print to the server terminal; production requires SMTP settings.

The signup form is `accounts.forms.SignupForm`:

| Field | Values | Notes |
| --- | --- | --- |
| `role` | `buyer`, `farmer` | Radio buttons, labelled "Account type", defaults to `buyer`, required. |
| `username` | text | Optional; labelled "Username (optional)". 3–30 characters using the same rules as username changes; generated when blank. |
| `email` | email | Required and unique; login is by email. |
| `password1`, `password2` | password | Standard Django password validation. |

Field order is `role`, `username`, `email`, `password1`, `password2`.

If the email already exists, allauth hides that fact and redirects to the same
verification-sent page without creating a user.

The social signup form is `accounts.forms.SocialSignupForm` with `role`,
`username`, and `email` (rendered in that order; `username` is required here).
It appears because `SOCIALACCOUNT_AUTO_SIGNUP` is off. The role chosen at
`social_signup_start` is preloaded from the session; when the visitor arrives
from the plain login page, no role is preselected and the field is required. A
Google account whose email matches an existing local account is linked
automatically and skips this form.

The kept shells are:

- `templates/account/base_entrance.html`
- `templates/account/base_manage.html`
- `templates/socialaccount/base_entrance.html`
- `templates/socialaccount/base_manage.html`

They extend `templates/base.html` and define a `head_title` block nested in
`title`, plus `content`. The actual login/signup/verification pages come from
the installed allauth package, so they load the project stylesheet through
`base.html`.

## Template map

| Template | Used by | Required | In repo |
| --- | --- | --- | --- |
| `base.html` | Every page | Yes | Yes |
| `listings/listings.html` | `listings_view` | Yes | No |
| `listings/listing_detail.html` | `listing_detail` | Yes | No |
| `listings/liked_listings.html` | `liked_listings` | Yes | No |
| `listings/my_listings.html` | `my_listings` | Yes | No |
| `listings/listing_form.html` | `listing_create`, `listing_update` | Yes | No |
| `listings/listing_confirm_delete.html` | `listing_delete` | Yes | No |
| `listings/_like_button.html` | htmx response from `listing_like_toggle` | Only when htmx is used | No |
| `listings/_listing_card.html` | Included by `listings.html` and `liked_listings.html` | Optional | No |
| `partials/pagination.html` | Included by `listings.html`, `liked_listings.html`, and `my_listings.html` | Optional | No |
| `partials/avatar.html` | Included by `accounts/accounts.html` | Optional | Yes |
| `accounts/accounts.html` | `profile_view` | Yes | Yes |
| `accounts/username_change.html` | `username_change` | Yes | Yes |
| `chat/chat.html` | `chat_view` | Yes | No |
| `analytics/analytics.html` | `analytics_view` | Yes | No |
| `notifications/notifications.html` | `notifications_view` | Yes | No |
| `account/base_entrance.html`, `account/base_manage.html` | allauth account pages | Yes | Yes |
| `socialaccount/base_entrance.html`, `socialaccount/base_manage.html` | allauth social pages | Yes | Yes |

`listings.html` and `liked_listings.html` both include `_listing_card.html`,
which uses a variable named `listing`. The removed pages included a separate
`partials/pagination.html`; there is no inline-only pagination convention to
follow.

## Pagination

The browse, saved, and farmer dashboard views provide `page_obj`, each with 24
items per page. It is a Django `Page`:

| Attribute | Meaning |
| --- | --- |
| `page_obj.number` | Current page. |
| `page_obj.paginator.num_pages` | Total pages. |
| `page_obj.has_previous` | Whether a previous page exists. |
| `page_obj.previous_page_number` | Previous page number. |
| `page_obj.has_next` | Whether a next page exists. |
| `page_obj.next_page_number` | Next page number. |

Django 6.1's `{% querystring %}` tag preserves the current filters while
replacing `page`:

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
| `public_id` | UUID | Use this in URLs, not the numeric `id`. |
| `farmer` | FK `User` | `listing.farmer`. |
| `category` | FK `Category` | `listing.category.name`, `listing.category.slug`. Protected from deletion while listings use it. |
| `title` | char(120) | |
| `condition` | `fresh`, `ripe`, `blemished`, `overripe`, `processing` | Use `get_condition_display`. |
| `description` | text | |
| `price` | decimal(10,2), nullable | `None` for free listings. Minimum `0.01`. |
| `is_free` | boolean | A database constraint requires `is_free` and `price is null` to agree. |
| `unit` | `kg`, `g`, `sack`, `piece`, `bunch`, `crate`, `tray`, `box`, `liter`, `dozen` | Use `get_unit_display`. |
| `stock_quantity` | decimal(10,2) | Never negative. |
| `bulk_order` | boolean | |
| `meetup` | boolean | |
| `meetup_location` | char(255) | Required when `meetup` is true. |
| `meetup_notes` | text | |
| `direct_to_market` | boolean | |
| `delivery` | boolean | |
| `status` | `draft`, `active`, `sold_out`, `archived` | Use `get_status_display`. |
| `status_note` | char(255) | Restock note. |
| `sold_out_at` | datetime, nullable | Set when status becomes `sold_out`, cleared when it leaves. Not in `ListingForm`. |
| `created_at`, `updated_at` | datetime | |

Listing helpers:

- `listing.cover_image` returns the first `ListingImage` by `position`, using
  the prefetch cache.
- `listing.images.all` returns all photos ordered by `position`, then `id`.
- `listing.likes_total` is annotated by the browse, detail, saved, and farmer
  dashboard views. It does not exist on a listing fetched any other way.

Limits: 5 photos per listing (`Listing.MAX_IMAGES`), 25 open listings, and 10
creations per rolling 24 hours (`MAX_OPEN_LISTINGS`, `MAX_LISTINGS_PER_DAY`).

### Category

`name` (unique) and `slug` (unique, generated from the name when blank). Use
`category.slug` for the `category` query parameter. Seeded categories: Rice,
Corn, Tomato, Eggplant, Banana, Mango, Coconut, Leafy Greens.

### ListingImage

`listing`, `image`, `position` (small integer), and `alt_text` (optional, max
200). `image.url` is the display URL; it is a local `/media/` URL in
development and a Supabase Storage URL in production.

### ListingLike

`user`, `listing`, `created_at`, with a unique `user` + `listing` constraint.

### User and Profile

`User` has a unique `email`, an internal `username`, `username_changed_at`, and
a one-to-one `profile`. `Profile` has `role`, `phone`, `location`,
`email_notifications`, `sms_notifications`, `avatar`, `avatar_url`,
`created_at`, and `updated_at`.

## Styling

- Tailwind CSS v4 through the npm CLI. Input: `assets/css/input.css`. Output:
  `static/css_output/output.css`, loaded by `base.html`.
- `npm run watch` rebuilds on change. `npm run build` builds once.
- Theme tokens: `bg` (`#000000`), `fg` (`#F6F8F9`), font `Inter`, and text
  sizes `text-h1` through `text-h6`, `text-body`, `text-small`.
- Below 640px, `input.css` shrinks `h1` and `h2`, pads `body`, and pads
  `.container`. The `.data-table` cells also shrink below 768px.
- Any class not already present in `output.css` renders unstyled until you
  rebuild.

## Forms and security checklist

- Every POST form needs `{% csrf_token %}`.
- Photo forms need `enctype="multipart/form-data"`.
- Render `form.non_field_errors` and per-field errors, or use `{{ form.as_p }}`.
- Keep the `name` attributes produced by Django; do not rename form fields.
- Use `{% url %}` names, not hard-coded paths.
- Do not expose `listing.id`; use `listing.public_id`.
- Keep the `next` parameter on login links when a page is protected.
- Show `messages` so success feedback is visible. `base.html` already does.

## Status and permission reference

| Situation | Result |
| --- | --- |
| Anonymous user opens a protected page | 302 to `/accounts/login/?next=...` |
| Signed-in buyer opens a farmer-only page (`my_listings`, `listing_create`) | 403 |
| Signed-in non-owner, including a buyer, opens edit/delete for a listing | 404 |
| Anyone opens a non-public listing they do not own | 404 |
| Authenticated `GET` on the like endpoint | 405 |
| Anonymous request on the like endpoint | 302 to login |
| Missing CSRF token on a POST | 403 |
| Invalid form POST (listing, profile) | 200 with form errors, once the form's template exists |
| Unverified email tries to log in | 302 to `account_email_verification_sent` |
| Successful create/edit/delete/profile action | 302 with a success message |

403 and 404 use Django's default error pages; the project has no custom
`403.html` or `404.html`.

## Known behaviour to design around

- After an anonymous user logs in from the like endpoint's redirect, the
  browser sends a `GET` to the like URL and receives 405. Link anonymous
  visitors to login with `next` set to the listing detail page, as shown in the
  detail section.
- htmx is loaded, so keeping the `hx-*` attributes on the recreated like partial
  gives an in-place toggle; without them the normal form POST still works.
- Search matches the farmer's internal `username`, so a query can surface a
  listing by a handle the UI never shows.
- `my_listings` select-relates `category`, so the dashboard does not run an
  extra query per listing.
- Replacing a profile photo deletes the previous file after the new upload
  commits.

## Tests

```bash
python manage.py test --settings=config.settings_test
```

The suite covers `accounts`, `listings`, and `config` (storage options). It
runs against the current templates, so template changes can fail these
assertions:

- Browse and detail pages contain the listing title, description, `₱100.00`
  price format, meet-up location, and the seller's username.
- Sold-out listings show the text `Sold out` and the `status_note` on the
  detail, saved, and dashboard pages.
- An owner viewing their own draft sees `Your listing is currently draft.`
- The like button shows `♥ Saved` after saving and `♡ Save` otherwise.
- The saved page shows `2 likes` when two users liked a listing.
- The create form shows `Add at least one photo.` on a missing photo.
- Detail pages render `image.image.url` for the cover.
- The signup page contains `Account type`, `Buyer`, `Farmer`, and
  `Username (optional)`.
- Allauth pages contain `Sign In`, `Signup`, and `Password Reset`.
- The htmx like response uses `listings/_like_button.html` with an `is_liked`
  context variable.
- Browse context exposes `page_obj` with 24 items on page one.

With the marketplace templates removed, those template-based tests currently
fail with `TemplateDoesNotExist`; they are the checklist for restoring the
frontend.

## Old templates for reference

The removed templates are in git history:

```bash
git show main:templates/listings/listings.html
git show main:templates/listings/listing_detail.html
git show main:templates/listings/_listing_card.html
git show main:templates/partials/pagination.html
```
