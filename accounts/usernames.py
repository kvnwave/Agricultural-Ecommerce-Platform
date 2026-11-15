"""Shared username rules for signup, profile changes, and data migrations."""

import re
import secrets

from django.core.exceptions import ValidationError

from .models import User

USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 30
USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*[a-z0-9]$")
USERNAME_PREFIX = "user-"

# Public routes and support identities. Compared after normalization, so the
# set only needs lowercase entries.
RESERVED_USERNAMES = frozenset(
    {
        "admin",
        "administrator",
        "accounts",
        "api",
        "buyer",
        "contact",
        "farmer",
        "help",
        "info",
        "marketplace",
        "moderator",
        "moderators",
        "official",
        "profile",
        "root",
        "sales",
        "security",
        "settings",
        "staff",
        "support",
        "system",
        "team",
        "user",
    }
)


def normalize_username(value):
    """Trim surrounding whitespace and fold case for storage and comparison."""

    return value.strip().lower()


def validate_username(value):
    """Return a normalized username or raise a form-friendly ValidationError."""

    value = normalize_username(value)
    if not USERNAME_MIN_LENGTH <= len(value) <= USERNAME_MAX_LENGTH:
        raise ValidationError(
            f"Username must be between {USERNAME_MIN_LENGTH} and "
            f"{USERNAME_MAX_LENGTH} characters.",
            code="username_length",
        )
    if not USERNAME_PATTERN.fullmatch(value):
        raise ValidationError(
            "Use only letters, numbers, underscores, and hyphens. "
            "Start and end with a letter or number.",
            code="username_invalid",
        )
    if value in RESERVED_USERNAMES:
        raise ValidationError(
            "That username is reserved. Please choose another.",
            code="username_reserved",
        )
    return value


def username_exists(value):
    return User.objects.filter(username__iexact=value).exists()


def generate_username():
    """Return an unused handle like ``user-1a2b3c4d``."""

    for _ in range(10):
        candidate = f"{USERNAME_PREFIX}{secrets.token_hex(4)}"
        if not username_exists(candidate):
            return candidate
    raise RuntimeError("Unable to generate a unique username.")
