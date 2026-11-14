from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models


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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.get_username()} ({self.get_role_display()})"
