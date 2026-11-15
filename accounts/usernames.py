"""Shared username rules for signup, profile changes, and data migrations."""

import re
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import UsernameHistory, User

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


class UsernameChangeError(Exception):
    """Base class for user-facing username change failures."""


class UsernameTakenError(UsernameChangeError):
    """Another account already holds the requested handle."""


class UsernameUnchangedError(UsernameChangeError):
    """The requested handle is the one already in use."""


class UsernameCooldownError(UsernameChangeError):
    """The seven-day cooldown has not elapsed."""

    def __init__(self, available_at):
        self.available_at = available_at
        super().__init__("Username change is on cooldown.")


def username_cooldown_ends(user):
    """When the user may change their handle again, or ``None`` if now."""

    if user.username_changed_at is None:
        return None
    available_at = user.username_changed_at + timedelta(
        days=settings.USERNAME_CHANGE_COOLDOWN_DAYS
    )
    return available_at if available_at > timezone.now() else None


def change_username(
    user,
    new_username,
    *,
    actor=None,
    reason=UsernameHistory.Reason.USER,
    enforce_cooldown=True,
):
    """Atomically rename a user, enforce the cooldown, and log the change.

    ``actor`` is the account making the change. Staff actors bypass the
    cooldown; every successful change still resets it.
    """

    new_username = validate_username(new_username)
    try:
        with transaction.atomic():
            locked = User.objects.select_for_update().get(pk=user.pk)
            old_username = locked.username

            if new_username == normalize_username(old_username):
                raise UsernameUnchangedError
            if enforce_cooldown and not (actor and actor.is_staff):
                available_at = username_cooldown_ends(locked)
                if available_at:
                    raise UsernameCooldownError(available_at)
            if (
                User.objects.filter(username__iexact=new_username)
                .exclude(pk=locked.pk)
                .exists()
            ):
                raise UsernameTakenError

            locked.username = new_username
            locked.username_changed_at = timezone.now()
            locked.save(update_fields=["username", "username_changed_at"])
            UsernameHistory.objects.create(
                user=locked,
                old_username=old_username,
                new_username=new_username,
                changed_by=actor,
                reason=reason,
            )
    except IntegrityError as exc:
        raise UsernameTakenError from exc
    return locked

