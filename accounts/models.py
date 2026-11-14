import uuid
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


def avatar_upload_path(instance, filename):
    """Unique per-user names prevent one upload from replacing another."""

    return f"avatars/{instance.user_id}/{uuid.uuid4().hex}{Path(filename).suffix.lower()}"


class User(AbstractUser):
    """Django admin and permissions assume a username; allauth logs in by email."""

    email = models.EmailField(unique=True)


class Profile(models.Model):
    """Marketplace data kept out of User so auth changes do not affect it."""

    class Role(models.TextChoices):
        FARMER = "farmer", "Farmer"
        BUYER = "buyer", "Buyer"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    # Signup collects only email/password, so new accounts start as buyers.
    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.BUYER,
    )
    phone = models.CharField(max_length=32, blank=True)
    location = models.CharField(max_length=255, blank=True)
    email_notifications = models.BooleanField(default=True)
    # SMS is opt-in because each send has a cost.
    sms_notifications = models.BooleanField(default=False)
    avatar = models.ImageField(
        upload_to=avatar_upload_path,
        blank=True,
        help_text="Shown instead of your Google photo.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def avatar_url(self):
        """An uploaded photo wins; otherwise linked Google accounts have one."""

        if self.avatar:
            return self.avatar.url

        account = self.user.socialaccount_set.filter(provider="google").first()
        return (account.get_avatar_url() or "") if account else ""

    def __str__(self):
        return f"{self.user.get_username()} ({self.get_role_display()})"
