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

    parsed = urlparse(url)
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
    """Whether ``url`` points at a Supabase transaction pooler endpoint."""

    if not url:
        return False

    parsed = urlparse(url)
    if parsed.scheme not in POSTGRES_SCHEMES:
        return False

    try:
        port = parsed.port
    except ValueError:
        return False

    host = parsed.hostname or ""
    return port == TRANSACTION_POOLER_PORT or host.endswith(POOLER_HOST_SUFFIX)


def direct_database_config(database_url, direct_url, *, ssl_require):
    """Build the ``DATABASES`` entry used by schema-changing commands.

    ``DIRECT_URL`` wins. Without it the runtime URL is reused so SQLite setups
    keep working, and a warning is logged when that would send migrations
    through the transaction pooler.
    """

    url = (direct_url or "").strip()
    if not url:
        if uses_transaction_pooler(database_url):
            logger.warning(
                "DIRECT_URL is not set, so schema changes would run through the "
                "Supabase transaction pooler. Set DIRECT_URL to the direct or "
                "session connection (port 5432)."
            )
        url = database_url

    return database_config(url, ssl_require=ssl_require)
