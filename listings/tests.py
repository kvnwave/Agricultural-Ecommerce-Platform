import io
import shutil
import tempfile
import uuid
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image

from accounts.models import Profile, User

from .models import Category, Listing, ListingImage, ListingLike


def image_bytes():
    buffer = io.BytesIO()
    Image.new("RGB", (20, 20), "green").save(buffer, format="PNG")
    return buffer.getvalue()


def create_farmer(username="farmer"):
    user = User.objects.create_user(
        username,
        email=f"{username}@example.com",
        password="temporary-pass-1",
    )
    user.profile.role = Profile.Role.FARMER
    user.profile.save(update_fields=["role"])
    return user


class CategoryTests(TestCase):
    def test_slug_is_generated_from_name(self):
        category = Category.objects.create(name="Dragon Fruit")

        self.assertEqual(category.slug, "dragon-fruit")
        self.assertEqual(str(category), "Dragon Fruit")

    def test_seeded_categories_are_available(self):
        self.assertTrue(Category.objects.filter(slug="rice").exists())
        self.assertTrue(Category.objects.filter(slug="tomato").exists())


class ListingModelTests(TestCase):
    def setUp(self):
        self.farmer = create_farmer()
        self.category = Category.objects.create(name="Test Produce")

    def make_listing(self, **overrides):
        data = {
            "farmer": self.farmer,
            "category": self.category,
            "title": "Test tomatoes",
            "description": "Fresh from the farm.",
            "price": Decimal("120.00"),
            "unit": Listing.Unit.KILOGRAM,
            "stock_quantity": Decimal("25.00"),
            "meetup_location": "Public market",
        }
        data.update(overrides)
        return Listing(**data)

    def test_defaults_and_public_id(self):
        listing = self.make_listing()
        listing.save()

        self.assertIsInstance(listing.public_id, uuid.UUID)
        self.assertEqual(listing.status, Listing.Status.ACTIVE)
        self.assertEqual(listing.condition, Listing.Condition.FRESH)
        self.assertEqual(listing.unit, Listing.Unit.KILOGRAM)
        self.assertFalse(listing.is_free)
        self.assertFalse(listing.bulk_order)
        self.assertEqual(str(listing), "Test tomatoes")

    def test_public_ids_are_unique(self):
        first = self.make_listing(title="Tomatoes")
        first.save()
        second = self.make_listing(title="Eggplants")
        second.save()

        self.assertNotEqual(first.public_id, second.public_id)

    def test_valid_listing_passes_full_clean(self):
        self.make_listing().full_clean()

    def test_paid_listing_requires_price(self):
        with self.assertRaises(ValidationError):
            self.make_listing(price=None).full_clean()

    def test_free_listing_rejects_price(self):
        with self.assertRaises(ValidationError):
            self.make_listing(is_free=True).full_clean()

    def test_free_listing_without_price_is_valid(self):
        self.make_listing(is_free=True, price=None).full_clean()

    def test_meetup_requires_location(self):
        with self.assertRaises(ValidationError):
            self.make_listing(meetup=True, meetup_location="").full_clean()

    def test_meetup_with_location_is_valid(self):
        self.make_listing(meetup=True).full_clean()

    def test_negative_stock_is_rejected(self):
        with self.assertRaises(ValidationError):
            self.make_listing(stock_quantity=Decimal("-1")).full_clean()

    def test_newest_listing_is_first(self):
        older = self.make_listing(title="Older")
        older.save()
        newer = self.make_listing(title="Newer")
        newer.save()
        Listing.objects.filter(pk=older.pk).update(
            created_at=timezone.now() - timedelta(days=1)
        )

        self.assertEqual(list(Listing.objects.all()), [newer, older])

    def test_category_with_listings_cannot_be_deleted(self):
        self.make_listing().save()

        with self.assertRaises(ProtectedError):
            self.category.delete()


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
)
class ListingImageTests(TestCase):
    def setUp(self):
        self.farmer = create_farmer()
        self.category = Category.objects.create(name="Test Produce")
        self.listing = Listing.objects.create(
            farmer=self.farmer,
            category=self.category,
            title="Test tomatoes",
            description="Fresh from the farm.",
            price=Decimal("120.00"),
        )
        self.media_root = tempfile.mkdtemp()
        self.media_override = override_settings(MEDIA_ROOT=self.media_root)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)

    def upload(self, filename="tomatoes.png", position=0):
        return ListingImage.objects.create(
            listing=self.listing,
            position=position,
            image=SimpleUploadedFile(
                filename,
                image_bytes(),
                content_type="image/png",
            ),
        )

    def test_upload_path_uses_public_id_and_random_name(self):
        image = self.upload()

        self.assertTrue(
            image.image.name.startswith(f"listings/{self.listing.public_id}/")
        )
        self.assertTrue(image.image.name.endswith(".png"))

    def test_two_uploads_with_same_name_do_not_collide(self):
        first = self.upload(filename="tomatoes.png")
        second = self.upload(filename="tomatoes.png")

        self.assertNotEqual(first.image.name, second.image.name)

    def test_images_are_ordered_by_position(self):
        second = self.upload(filename="second.png", position=1)
        first = self.upload(filename="first.png", position=0)

        self.assertEqual(list(self.listing.images.all()), [first, second])


class ListingLikeTests(TestCase):
    def setUp(self):
        self.farmer = create_farmer()
        self.user = User.objects.create_user(
            "buyer",
            email="buyer@example.com",
            password="temporary-pass-1",
        )
        self.category = Category.objects.create(name="Test Produce")
        self.listing = Listing.objects.create(
            farmer=self.farmer,
            category=self.category,
            title="Test tomatoes",
            description="Fresh from the farm.",
            price=Decimal("120.00"),
        )

    def test_a_user_can_like_a_listing_only_once(self):
        ListingLike.objects.create(user=self.user, listing=self.listing)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ListingLike.objects.create(user=self.user, listing=self.listing)

        self.assertEqual(self.listing.likes.count(), 1)

    def test_listing_delete_removes_likes(self):
        ListingLike.objects.create(user=self.user, listing=self.listing)

        self.listing.delete()

        self.assertFalse(ListingLike.objects.exists())
