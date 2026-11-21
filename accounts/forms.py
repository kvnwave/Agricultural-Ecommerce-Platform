from allauth.account.forms import SignupForm as AllauthSignupForm
from allauth.core import context as allauth_context
from allauth.socialaccount.forms import SignupForm as AllauthSocialSignupForm
from django import forms
from django.db import transaction

from . import usernames
from .models import Profile

SOCIAL_SIGNUP_ROLE_SESSION_KEY = "social_signup_role"
USERNAME_HELP_TEXT = (
    f"{usernames.USERNAME_MIN_LENGTH}-{usernames.USERNAME_MAX_LENGTH} "
    "characters. Letters, numbers, underscores, and hyphens. "
    "Leave blank and we'll generate one."
)


def configure_username_field(form):
    """Make allauth's optional username field match the marketplace policy."""

    field = form.fields.get("username")
    if field is None:
        return
    field.min_length = usernames.USERNAME_MIN_LENGTH
    field.max_length = usernames.USERNAME_MAX_LENGTH
    field.widget.attrs["maxlength"] = str(usernames.USERNAME_MAX_LENGTH)
    field.help_text = USERNAME_HELP_TEXT


def account_role_field(*, initial=None):
    return forms.ChoiceField(
        choices=Profile.Role.choices,
        label="Account type",
        initial=initial,
        widget=forms.RadioSelect,
        help_text="Choose Farmer if you want to sell produce.",
    )


def save_profile_role(user, role):
    user.profile.role = role
    user.profile.save(update_fields=["role"])


class SignupForm(AllauthSignupForm):
    """allauth's email signup plus the marketplace account type."""

    role = account_role_field(initial=Profile.Role.BUYER)
    field_order = ["role", "username", "email", "password1", "password2"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        configure_username_field(self)

    def save(self, request):
        user = super().save(request)
        save_profile_role(user, self.cleaned_data["role"])
        return user


class SocialSignupForm(AllauthSocialSignupForm):
    """Social signup keeps the role chosen before leaving for the provider."""

    role = account_role_field()
    field_order = ["role", "username", "email"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        configure_username_field(self)
        request = allauth_context.request
        role = request.session.get(SOCIAL_SIGNUP_ROLE_SESSION_KEY) if request else None
        if role in Profile.Role.values:
            self.fields["role"].initial = role

    def save(self, request):
        user = super().save(request)
        save_profile_role(user, self.cleaned_data["role"])
        request.session.pop(SOCIAL_SIGNUP_ROLE_SESSION_KEY, None)
        return user


class UsernameChangeForm(forms.Form):
    username = forms.CharField(
        label="New username",
        min_length=usernames.USERNAME_MIN_LENGTH,
        max_length=usernames.USERNAME_MAX_LENGTH,
        help_text=USERNAME_HELP_TEXT,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "username",
                "maxlength": str(usernames.USERNAME_MAX_LENGTH),
            }
        ),
    )

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        self.fields["username"].initial = user.username

    def clean_username(self):
        value = usernames.validate_username(self.cleaned_data["username"])
        if value == usernames.normalize_username(self.user.username):
            raise forms.ValidationError("That is already your username.")
        if usernames.username_exists(value):
            raise forms.ValidationError("That username is already taken.")
        return value


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ("avatar",)
        widgets = {
            "avatar": forms.ClearableFileInput(
                attrs={"accept": "image/*", "class": "mt-2 block w-full text-sm text-fg"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # ``_post_clean`` replaces the field before ``save`` runs, so keep the
        # stored name now and delete it only after the new one commits.
        self._old_avatar = self.instance.avatar.name if self.instance.pk else ""

    def clean_avatar(self):
        avatar = self.cleaned_data.get("avatar")
        if avatar and avatar.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Choose an image smaller than 5 MB.")
        return avatar

    def save(self, commit=True):
        profile = super().save(commit=commit)
        if not commit:
            return profile

        old_avatar = self._old_avatar
        if old_avatar and old_avatar != profile.avatar.name:
            storage = profile.avatar.storage
            transaction.on_commit(
                lambda: storage.delete(old_avatar),
                robust=True,
            )

        # The URL was cached before the upload replaced or cleared the file.
        profile.__dict__.pop("avatar_url", None)
        return profile
