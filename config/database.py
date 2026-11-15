"""Database connection helpers for Supabase Postgres.

Supabase exposes the same database through two endpoints:

* the transaction pooler (port 6543), used by the web process, which gives
  every request a short-lived connection;
* the direct or session connection (port 5432), used by schema-changing
  commands, because the pooler cannot keep the session state, advisory locks,
  and server-side cursors that Django's migrations and ``createcachetable``
  rely on.
"""

import logging
import re
from urllib.parse import urlparse

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

logger = logging.getLogger(__name__)

POSTGRES_SCHEMES = {"postgres", "postgresql"}
SQLITE_SCHEMES = {"sqlite", "sqlite3"}
SUPPORTED_SCHEMES = POSTGRES_SCHEMES | SQLITE_SCHEMES

# Supabase's transaction pooler listens on 6543; the direct/session connection
# uses 5432.
TRANSACTION_POOLER_PORT = 6543
POOLER_HOST_SUFFIX = "pooler.supabase.com"

# Characters that cannot appear raw inside the password portion of a
# connection URL. Password managers hand these out unescaped, and CPython then
# reports a misleading "does not appear to be an IPv4 or IPv6 address" error
# for a bracketed password. Percent signs are handled separately, so an
# existing escape is not encoded twice.
_PASSWORD_ESCAPES = {
    " ": "%20",
    '"': "%22",
    "#": "%23",
    "/": "%2F",
    ":": "%3A",
    "?": "%3F",
    "@": "%40",
    "[": "%5B",
    "]": "%5D",
}
_PASSWORD_TRANSLATION = str.maketrans(_PASSWORD_ESCAPES)
_AUTHORITY_END = re.compile(r"[/?#]")
# A '%' that does not start a valid escape is a literal percent sign. The URL
# parser decodes escapes in the password, so leaving it raw would send a
# different string and silently fail authentication.
_STRAY_PERCENT = re.compile(r"%(?![0-9A-Fa-f]{2})")


def _encode_password(password):
    """Escape reserved characters, keeping existing ``%XX`` escapes intact."""

    return _STRAY_PERCENT.sub("%25", password.translate(_PASSWORD_TRANSLATION))


def encode_url_password(url):
    """Percent-encode reserved characters in a database URL's password.

    Only characters that cannot appear raw in ``userinfo`` are escaped, plus a
    literal ``%``, so a password that is already percent-encoded comes back
    unchanged.
    """

    scheme, separator, rest = url.partition("://")
    if not separator:
        return url

    authority_end = _AUTHORITY_END.search(rest)
    if authority_end:
        authority = rest[: authority_end.start()]
        tail = rest[authority_end.start() :]
    else:
        authority, tail = rest, ""

    userinfo, at, host = authority.rpartition("@")
    if not at:
        # A delimiter inside the password hides the authority boundary. Hosts
        # cannot contain '@', so the URL's last '@' is still the delimiter.
        userinfo, at, remainder = rest.rpartition("@")
        if not at:
            return url
        remainder_end = _AUTHORITY_END.search(remainder)
        if remainder_end:
            host = remainder[: remainder_end.start()]
            tail = remainder[remainder_end.start() :]
        else:
            host, tail = remainder, ""

    user, colon, password = userinfo.partition(":")
    if not colon or not password:
        return url

    encoded = _encode_password(password)
    return f"{scheme}{separator}{user}:{encoded}@{host}{tail}"


def _parse_url(url):
    """Parse ``url``, turning parser edge cases into configuration errors."""

    try:
        parsed = urlparse(url)
        # urlparse defers host and port validation; touch them to force it.
        parsed.hostname
        parsed.port
    except ValueError as exc:
        raise ImproperlyConfigured(
            "The database URL could not be parsed. Percent-encode reserved "
            'characters in the password: space, ", #, /, :, ?, @, [, ].'
        ) from exc
    return parsed


def _parse_url_or_none(url):
    try:
        return _parse_url(url)
    except ImproperlyConfigured:
        return None


def database_config(url, *, ssl_require):
    """Build a Django ``DATABASES`` entry from ``url``.

    TLS is requested only for Postgres URLs: SQLite passes ``OPTIONS`` straight
    to sqlite3, which rejects ``sslmode``.
    """

    if not url:
        raise ImproperlyConfigured(
            "DATABASE_URL must be set. Use sqlite:///db.sqlite3 for local "
            "development or the Supabase transaction pooler URL."
        )

    url = encode_url_password(url.strip())
    parsed = _parse_url(url)
    if parsed.scheme not in SUPPORTED_SCHEMES:
        raise ImproperlyConfigured(
            f"Unsupported database URL scheme '{parsed.scheme}'. Use "
            "postgresql:// for Supabase or sqlite:/// for local development."
        )

    config = dj_database_url.parse(
        url,
        ssl_require=ssl_require and parsed.scheme in POSTGRES_SCHEMES,
    )
    # Supabase's transaction pooler cannot keep server-side cursors open
    # between statements, so Django must page results in memory.
    config["DISABLE_SERVER_SIDE_CURSORS"] = True
    return config


def uses_transaction_pooler(url):
    """Whether ``url`` points at a Supabase transaction pooler endpoint.

    The session pooler shares the ``pooler.supabase.com`` host and only differs
    by running on port 5432, where migrations work, so the port decides when it
    is present.
    """

    if not url:
        return False

    parsed = _parse_url_or_none(encode_url_password(url.strip()))
    if parsed is None or parsed.scheme not in POSTGRES_SCHEMES:
        return False

    if parsed.port is not None:
        return parsed.port == TRANSACTION_POOLER_PORT

    return (parsed.hostname or "").endswith(POOLER_HOST_SUFFIX)


def direct_database_config(database_url, direct_url, *, ssl_require):
    """Build the ``DATABASES`` entry used by schema-changing commands.

    ``DIRECT_URL`` wins; without it the runtime URL is reused so SQLite setups
    keep working. Either way, a warning is logged when the connection used for
    schema changes is the transaction pooler, since migrations and
    ``createcachetable`` fail there.
    """

    direct = (direct_url or "").strip()
    url = direct or database_url

    if uses_transaction_pooler(url):
        if direct:
            logger.warning(
                "DIRECT_URL points at the Supabase transaction pooler "
                "(port 6543). Schema changes need the direct or session "
                "connection (port 5432)."
            )
        else:
            logger.warning(
                "DIRECT_URL is not set, so schema changes would run through the "
                "Supabase transaction pooler. Set DIRECT_URL to the direct or "
                "session connection (port 5432)."
            )

    return database_config(url, ssl_require=ssl_require)
