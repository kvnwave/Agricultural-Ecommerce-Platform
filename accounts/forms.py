from django import forms

from .models import Profile


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
