from allauth.account.forms import SignupForm as AllauthSignupForm
from allauth.core import context as allauth_context
from allauth.socialaccount.forms import SignupForm as AllauthSocialSignupForm
from django import forms

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


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ("avatar",)
        widgets = {
            "avatar": forms.ClearableFileInput(
                attrs={"accept": "image/*", "class": "mt-2 block w-full text-sm text-fg"}
            ),
        }

    def clean_avatar(self):
        avatar = self.cleaned_data.get("avatar")
        if avatar and avatar.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Choose an image smaller than 5 MB.")
        return avatar
