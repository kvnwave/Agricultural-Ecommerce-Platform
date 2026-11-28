import io
import logging
from pathlib import Path

from django import forms
from django.core.files.base import ContentFile
from django.db import transaction
from PIL import Image, ImageOps, UnidentifiedImageError

from .models import Listing, ListingImage

logger = logging.getLogger(__name__)

# Only formats the marketplace re-encodes cleanly. Rejecting the rest keeps
# stored files free of EXIF and other embedded metadata.
IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}
IMAGE_SUFFIXES = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024


def _scrub_image(upload):
    """Re-encode an upload so EXIF, GPS, and other metadata are dropped."""

    try:
        with Image.open(upload) as source:
            image_format = source.format
            if image_format not in IMAGE_FORMATS:
                raise forms.ValidationError(
                    "Upload a JPEG, PNG, or WebP photo."
                )
            max_pixels = Image.MAX_IMAGE_PIXELS
            if (
                max_pixels is not None
                and source.width * source.height > max_pixels
            ):
                raise forms.ValidationError(
                    "This photo is too large to process. "
                    f"Use an image under {max_pixels // 1_000_000} megapixels."
                )

            image = ImageOps.exif_transpose(source)
            if image_format == "JPEG":
                image = image.convert("RGB")
            elif image_format == "PNG":
                if image.mode not in ("RGB", "RGBA", "L", "LA", "P"):
                    image = image.convert("RGBA")
            elif image.mode not in ("RGB", "RGBA"):
                image = image.convert("RGBA")

            output = io.BytesIO()
            options = {"optimize": True}
            if image_format in {"JPEG", "WEBP"}:
                options["quality"] = 90
            image.save(output, format=image_format, **options)
    except forms.ValidationError:
        raise
    except (
        Image.DecompressionBombError,
        UnidentifiedImageError,
        OSError,
        ValueError,
    ) as exc:
        raise forms.ValidationError(
            "Upload a valid JPEG, PNG, or WebP photo."
        ) from exc

    data = output.getvalue()
    if len(data) > MAX_IMAGE_BYTES:
        raise forms.ValidationError("Each photo must be smaller than 5 MB.")
    stem = Path(upload.name).stem or "photo"
    return ContentFile(data, name=f"{stem}{IMAGE_SUFFIXES[image_format]}")


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
        # Count and size come first: Pillow must not parse files the request
        # would reject anyway.
        if len(data) > Listing.MAX_IMAGES:
            raise forms.ValidationError(
                f"Add at most {Listing.MAX_IMAGES} photos."
            )
        for item in data:
            if item.size > MAX_IMAGE_BYTES:
                raise forms.ValidationError(
                    "Each photo must be smaller than 5 MB."
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

        # The template renders condition as radio pills instead of a dropdown.
        # Choices live on the widget instance, so pass them to the new one.
        condition = self.fields["condition"]
        condition.widget = forms.RadioSelect(choices=condition.choices)

        field_class = (
            "w-full rounded-xl border border-mist bg-paper px-3.5 py-2.5 "
            "text-sm text-ink placeholder:text-mute focus:border-leaf "
            "focus:outline-none focus:ring-2 focus:ring-leaf/40"
        )
        placeholders = {
            "title": "Listing title",
            "description": "Describe your produce",
            "price": "Price of your listing",
            "meetup_location": "Search location",
            "meetup_notes": "Add notes for the buyer",
            "status_note": "Tell buyers when you expect to restock",
        }
        for name, field in self.fields.items():
            if name in {"images", "condition", "remove_images"}:
                continue
            widget = field.widget
            if isinstance(
                widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple)
            ):
                continue
            if isinstance(widget, forms.Textarea):
                widget.attrs.setdefault("rows", "4")
                # Buyer-facing notes stay compact; the description keeps 4.
                if name == "meetup_notes":
                    widget.attrs["rows"] = "2"
            widget.attrs.setdefault("class", field_class)
            if name == "price":
                widget.attrs["class"] += " pl-9"
                widget.attrs.setdefault("min", "0.01")
                widget.attrs.setdefault("step", "0.01")
            elif name == "meetup_location":
                widget.attrs["class"] += " pr-10"
            elif name == "stock_quantity":
                widget.attrs.setdefault("min", "0")
                widget.attrs.setdefault("step", "0.01")
            if name in placeholders:
                widget.attrs.setdefault("placeholder", placeholders[name])

    def clean_images(self):
        images = self.cleaned_data.get("images") or []
        return [_scrub_image(image) for image in images]

    def clean(self):
        cleaned_data = super().clean()

        # A rejected upload is missing from cleaned_data, so counting here
        # would also add "Add at least one photo." The upload error is the
        # actionable one; do not stack a contradictory second message on it.
        if self.has_error("images"):
            return cleaned_data

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
        if not commit:
            return super().save(commit=False)

        with transaction.atomic():
            listing = super().save(commit=True)

            removed = self.cleaned_data.get("remove_images")
            if removed:
                removed.delete()

            created_images = []
            try:
                position = max(
                    (image.position for image in listing.images.all()),
                    default=-1,
                ) + 1
                for offset, image in enumerate(
                    self.cleaned_data.get("images") or []
                ):
                    listing_image = ListingImage(
                        listing=listing,
                        image=image,
                        position=position + offset,
                    )
                    # Track before saving: a storage write can succeed while
                    # the row insert fails, and that file still needs cleanup.
                    created_images.append(listing_image)
                    listing_image.save()
            except Exception:
                self._delete_committed_images(created_images)
                raise

        return listing

    @staticmethod
    def _delete_committed_images(images):
        """Best-effort removal of files written before a failed save."""

        for listing_image in images:
            image_file = listing_image.image
            # _committed is only set after upload_to has run and the storage
            # backend has written the file, so this never deletes by the raw
            # upload filename.
            if not image_file or not image_file._committed:
                continue
            try:
                image_file.storage.delete(image_file.name)
            except Exception:
                logger.exception(
                    "Could not remove uploaded listing photo %s",
                    image_file.name,
                )
