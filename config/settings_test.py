"""Settings for the automated test suite.

Production-like settings are the default here (``DEBUG = False``) so tests
exercise the same code paths as deployment. The HTTPS redirect and secure
cookie flags are disabled because the Django test client speaks plain HTTP.
"""

import os

# Set the environment before importing the project settings. ``load_dotenv``
# does not override existing variables, so these values win over a local .env.
os.environ["DEBUG"] = "False"
os.environ["SECRET_KEY"] = (
    "test-only-secret-key-that-is-long-enough-for-deploy-checks-1234567890"
)
os.environ["ALLOWED_HOSTS"] = "testserver,localhost,127.0.0.1"
os.environ["EMAIL_HOST"] = "smtp.test.invalid"
os.environ["DEFAULT_FROM_EMAIL"] = "test@example.com"

from config.settings import *  # noqa: E402,F403
from config.settings import BASE_DIR  # noqa: E402

DEBUG = False

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.locmem.EmailBackend",
    },
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "allauth-tests",
    }
}
ACCOUNT_RATE_LIMITS = False

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

# The test client uses HTTP; redirecting to HTTPS would turn every request into
# a 301 and hide the behavior under test.
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

MEDIA_ROOT = BASE_DIR / "media"
