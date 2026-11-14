from django import forms

from .models import Listing, ListingImage


class MultipleFileInput(forms.FileInput):
    """Allow the browser to submit more than one file for one field."""

    allow_multiple_selected = True


class MultipleImageField(forms.ImageField):
    """ImageField that validates each file returned by ``getlist``."""

    widget = MultipleFileInput

    def clean(self, data, initial=None):
        if not data:
            data = []
        elif not isinstance(data, (list, tuple)):
            data = [data]

        if self.required and not data:
            raise forms.ValidationError(
                self.error_messages["required"],
                code="required",
            )

        return [super().clean(item, initial=None) for item in data]


class ListingForm(forms.ModelForm):
    images = MultipleImageField(
        required=False,
        widget=MultipleFileInput(attrs={"accept": "image/*"}),
        help_text=f"Add up to {Listing.MAX_IMAGES} photos. The first is the cover.",
    )
    remove_images = forms.ModelMultipleChoiceField(
        queryset=ListingImage.objects.none(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Remove photos",
    )
    field_order = (
        "title",
        "category",
        "condition",
        "description",
        "price",
        "is_free",
        "unit",
        "stock_quantity",
        "bulk_order",
        "meetup",
        "meetup_location",
        "meetup_notes",
        "direct_to_market",
        "delivery",
        "status",
        "status_note",
        "images",
        "remove_images",
    )

    class Meta:
        model = Listing
        fields = (
            "title",
            "category",
            "condition",
            "description",
            "price",
            "is_free",
            "unit",
            "stock_quantity",
            "bulk_order",
            "meetup",
            "meetup_location",
            "meetup_notes",
            "direct_to_market",
            "delivery",
            "status",
            "status_note",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["remove_images"].queryset = self.instance.images.all()
        else:
            self.fields.pop("remove_images")

    def clean_images(self):
        images = self.cleaned_data.get("images") or []
        for image in images:
            if image.size > 5 * 1024 * 1024:
                raise forms.ValidationError("Each photo must be smaller than 5 MB.")
        return images

    def clean(self):
        cleaned_data = super().clean()
        images = cleaned_data.get("images") or []
        removed = cleaned_data.get("remove_images")
        existing = self.instance.images.count() if self.instance.pk else 0
        remaining = existing - (removed.count() if removed else 0)
        total = remaining + len(images)

        if total == 0:
            self.add_error("images", "Add at least one photo.")
        elif total > Listing.MAX_IMAGES:
            self.add_error(
                "images",
                f"Add at most {Listing.MAX_IMAGES} photos.",
            )

        return cleaned_data

    def save(self, commit=True):
        listing = super().save(commit=commit)
        if not commit:
            return listing

        removed = self.cleaned_data.get("remove_images")
        if removed:
            removed.delete()

        position = max(
            (image.position for image in listing.images.all()),
            default=-1,
        ) + 1
        for offset, image in enumerate(self.cleaned_data.get("images") or []):
            ListingImage.objects.create(
                listing=listing,
                image=image,
                position=position + offset,
            )

        return listing
