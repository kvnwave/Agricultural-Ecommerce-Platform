"""allauth hooks that apply the marketplace username policy."""

from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.core.exceptions import ValidationError

from . import usernames


class AccountAdapter(DefaultAccountAdapter):
    """Normalize and validate usernames for email and social signup."""

    def clean_username(self, username, shallow=False):
        username = usernames.validate_username(username)
        # Keep allauth's configured validators and blacklist in the loop, but
        # skip its exact-match query; the case-insensitive check follows.
        username = super().clean_username(username, shallow=True)
        if not shallow and usernames.username_exists(username):
            raise ValidationError(
                "That username is already taken.",
                code="username_taken",
            )
        return username

    def generate_unique_username(self, txts, regex=None):
        """Ignore name/email-derived candidates and use a neutral handle."""

        return usernames.generate_username()


class SocialAccountAdapter(DefaultSocialAccountAdapter):
    """Do not carry provider names or email addresses into the username."""

    def get_signup_form_initial_data(self, sociallogin):
        initial = super().get_signup_form_initial_data(sociallogin)
        initial["username"] = ""
        return initial
