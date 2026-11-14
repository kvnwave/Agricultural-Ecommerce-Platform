from allauth.account.forms import SignupForm as AllauthSignupForm
from django import forms

from .models import Profile


class SignupForm(AllauthSignupForm):
    """allauth's email signup plus the marketplace account type."""

    role = forms.ChoiceField(
        choices=Profile.Role.choices,
        label="Account type",
        initial=Profile.Role.BUYER,
        widget=forms.RadioSelect,
        help_text="Choose Farmer if you want to sell produce.",
    )
    field_order = ["role", "email", "password1", "password2"]

    def save(self, request):
        user = super().save(request)
        user.profile.role = self.cleaned_data["role"]
        user.profile.save(update_fields=["role"])
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
