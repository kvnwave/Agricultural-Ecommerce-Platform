import uuid
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.text import slugify


class Category(models.Model):
    """Produce type used to group listings and compare prices."""

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True, blank=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class Listing(models.Model):
    """Produce offered by a farmer, shaped after a marketplace listing."""

    MAX_IMAGES = 5

    class Condition(models.TextChoices):
        FRESH = "fresh", "Fresh Harvest"
        RIPE = "ripe", "Ripe"
        BLEMISHED = "blemished", "Slightly Blemished"
        OVERRIPE = "overripe", "Overripe"
        PROCESSING = "processing", "For Processing"

    class Unit(models.TextChoices):
        KILOGRAM = "kg", "Kilogram (kg)"
        GRAM = "g", "Gram (g)"
        SACK = "sack", "Sack"
        PIECE = "piece", "Piece"
        BUNCH = "bunch", "Bunch"
        CRATE = "crate", "Crate"
        TRAY = "tray", "Tray"
        BOX = "box", "Box"
        LITER = "liter", "Liter"
        DOZEN = "dozen", "Dozen"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        SOLD_OUT = "sold_out", "Sold out"
        ARCHIVED = "archived", "Archived"

    # Sequential IDs stay internal; random public IDs keep URLs non-guessable.
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    farmer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="listings",
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name="listings",
    )
    title = models.CharField(max_length=120)
    condition = models.CharField(
        max_length=20,
        choices=Condition.choices,
        default=Condition.FRESH,
    )
    description = models.TextField()
    # A free listing stores no price; the flag keeps that difference queryable.
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="Price in PHP per unit. Leave empty for free listings.",
    )
    is_free = models.BooleanField(
        default=False,
        help_text="Free listings are shown separately from paid ones.",
    )
    unit = models.CharField(
        max_length=10,
        choices=Unit.choices,
        default=Unit.KILOGRAM,
    )
    stock_quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Available stock in the selected unit.",
    )
    bulk_order = models.BooleanField(
        default=False,
        help_text="Accept orders larger than the listed stock.",
    )
    meetup = models.BooleanField(default=False)
    direct_to_market = models.BooleanField(default=False)
    delivery = models.BooleanField(default=False)
    meetup_location = models.CharField(max_length=255, blank=True)
    meetup_notes = models.TextField(blank=True)
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    status_note = models.CharField(
        max_length=255,
        blank=True,
        help_text="Tell buyers when you expect to restock.",
    )
    # Kept for the future "notify likers when sold out" task.
    sold_out_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["category", "status", "-created_at"],
                name="listing_cat_status_created_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(is_free=True, price__isnull=True)
                    | models.Q(is_free=False, price__isnull=False)
                ),
                name="listing_price_free_flag",
            ),
            models.CheckConstraint(
                condition=models.Q(stock_quantity__gte=0),
                name="listing_stock_non_negative",
            ),
        ]

    def clean(self):
        super().clean()

        if self.is_free and self.price is not None:
            raise ValidationError(
                {"price": "Free listings cannot have a price."}
            )
        if not self.is_free and self.price is None:
            raise ValidationError(
                {"price": "Set a price or mark the listing as free."}
            )
        if self.meetup and not (self.meetup_location or "").strip():
            raise ValidationError(
                {"meetup_location": "Add the meet-up location."}
            )

    def __str__(self):
        return self.title


def listing_image_upload_path(instance, filename):
    """Random names keep one upload from replacing another on any storage."""

    suffix = Path(filename).suffix.lower()
    return f"listings/{instance.listing.public_id}/{uuid.uuid4().hex}{suffix}"


class ListingImage(models.Model):
    listing = models.ForeignKey(
        Listing,
        on_delete=models.CASCADE,
        related_name="images",
    )
    image = models.ImageField(upload_to=listing_image_upload_path)
    position = models.PositiveSmallIntegerField(default=0)
    alt_text = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self):
        return f"{self.listing.title} photo {self.position}"


class ListingLike(models.Model):
    """A buyer's saved/favorite listing."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="listing_likes",
    )
    listing = models.ForeignKey(
        Listing,
        on_delete=models.CASCADE,
        related_name="likes",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "listing"],
                name="unique_listing_like",
            ),
        ]

    def __str__(self):
        return f"{self.user} likes {self.listing}"
