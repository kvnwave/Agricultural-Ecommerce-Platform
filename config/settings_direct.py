"""Settings for commands that change the database schema.

Django's migrations and ``createcachetable`` need a session that stays alive
for locks and cursors, which Supabase's transaction pooler does not provide.
Run those commands over the direct or session connection:

    python manage.py migrate --settings=config.settings_direct
    python manage.py createcachetable --settings=config.settings_direct

The web process keeps using the pooler through ``config.settings``.
"""

from config.database import direct_database_config
from config.settings import *  # noqa: E402,F403
from config.settings import (  # noqa: E402
    DATABASE_URL,
    DB_SSL_REQUIRE,
    DIRECT_DATABASE_URL,
)

DATABASES = {
    "default": direct_database_config(
        DATABASE_URL,
        DIRECT_DATABASE_URL,
        ssl_require=DB_SSL_REQUIRE,
    ),
}
