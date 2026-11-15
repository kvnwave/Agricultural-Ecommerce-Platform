"""Rename allauth's email-derived usernames to neutral generated handles.

The old fallback used the email local part, which exposed part of every
address. Staff accounts are skipped so ``/admin/`` login stays unchanged, and
social handles derived from a provider name are left alone.
"""

import re
import secrets
import unicodedata

from django.db import migrations

INVALID_USERNAME_CHARS = re.compile(r"[^\w\s@+.-]")
GENERATED_PREFIX = "user-"


def _allauth_base(value):
    """Mirror allauth's old ``_generate_unique_username_base``."""

    if not value:
        return ""
    value = unicodedata.normalize("NFKD", str(value))
    value = value.encode("ascii", "ignore").decode("ascii")
    value = INVALID_USERNAME_CHARS.sub("", value).lower()
    value = value.split("@")[0].strip()
    return re.sub(r"\s+", "_", value)


def _matches_allauth_candidate(username, base, max_length):
    """Return True for ``base`` or ``base`` plus a 1-6 char suffix."""

    if not base or not username:
        return False
    username = username.lower()
    if username == base:
        return True
    for suffix_length in range(1, 7):
        prefix = base[: max_length - suffix_length]
        if not username.startswith(prefix):
            continue
        suffix = username[len(prefix) :]
        if len(suffix) != suffix_length or not suffix.isascii():
            continue
        if not suffix[:4].isdigit():
            continue
        if suffix[4:] and not suffix[4:].isalpha():
            continue
        return True
    return False


def _name_derived(username, user, SocialAccount, max_length):
    """A provider name may legitimately produce the same handle."""

    if not SocialAccount.objects.filter(user_id=user.pk).exists():
        return False
    return any(
        _matches_allauth_candidate(
            username, _allauth_base(name), max_length
        )
        for name in (user.first_name, user.last_name)
    )


def _generate_username(User):
    for _ in range(10):
        candidate = f"{GENERATED_PREFIX}{secrets.token_hex(4)}"
        if not User.objects.filter(username__iexact=candidate).exists():
            return candidate
    raise RuntimeError("Unable to generate a unique username during migration.")


def rename_email_usernames(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    UsernameHistory = apps.get_model("accounts", "UsernameHistory")
    SocialAccount = apps.get_model("socialaccount", "SocialAccount")
    max_length = User._meta.get_field("username").max_length or 150

    users = (
        User.objects.filter(is_staff=False, is_superuser=False)
        .exclude(email="")
        .iterator()
    )
    for user in users:
        base = _allauth_base(user.email)
        if not _matches_allauth_candidate(user.username, base, max_length):
            continue
        if _name_derived(user.username, user, SocialAccount, max_length):
            continue

        old_username = user.username
        new_username = _generate_username(User)
        user.username = new_username
        # Affected users get one immediate change to pick their own handle.
        user.username_changed_at = None
        user.save(update_fields=["username", "username_changed_at"])
        UsernameHistory.objects.create(
            user_id=user.pk,
            old_username=old_username,
            new_username=new_username,
            changed_by_id=None,
            reason="migration",
        )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_username_policy"),
        ("socialaccount", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(rename_email_usernames, migrations.RunPython.noop),
    ]
