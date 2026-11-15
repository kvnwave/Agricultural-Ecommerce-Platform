import io
import shutil
import tempfile
import uuid
import warnings
from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.storage import storages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import IntegrityError, connection, transaction
from django.db.models import ProtectedError
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from accounts.models import Profile, User

from .forms import ListingForm
from .models import Category, Listing, ListingImage, ListingLike
from .views import LISTINGS_PER_PAGE, SEARCH_QUERY_MAX_LENGTH


def image_bytes():
    buffer = io.BytesIO()
    Image.new("RGB", (20, 20), "green").save(buffer, format="PNG")
    return buffer.getvalue()


def uploaded_image(filename="photo.png"):
    return SimpleUploadedFile(
        filename,
        image_bytes(),
        content_type="image/png",
    )


def gps_jpeg_bytes():
    """A sideways JPEG carrying GPS coordinates in EXIF."""

    exif = Image.Exif()
    exif[0x0112] = 6  # Rotate 90 degrees clockwise when displayed.
    gps = exif.get_ifd(0x8825)
    gps[1] = "N"
    gps[2] = (14.0, 35.0, 0.0)
    gps[3] = "E"
    gps[4] = (120.0, 58.0, 0.0)
    buffer = io.BytesIO()
    Image.new("RGB", (20, 10), "green").save(buffer, format="JPEG", exif=exif)
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

    def test_marking_sold_out_records_timestamp(self):
        listing = self.make_listing(status=Listing.Status.SOLD_OUT)
        listing.save()

        self.assertIsNotNone(listing.sold_out_at)

    def test_relisting_clears_sold_out_timestamp(self):
        listing = self.make_listing(status=Listing.Status.SOLD_OUT)
        listing.save()
        sold_out_at = listing.sold_out_at

        listing.status = Listing.Status.ACTIVE
        listing.save(update_fields=["status"])
        listing.refresh_from_db()

        self.assertIsNotNone(sold_out_at)
        self.assertIsNone(listing.sold_out_at)

    def test_sold_out_timestamp_survives_other_edits(self):
        listing = self.make_listing(status=Listing.Status.SOLD_OUT)
        listing.save()
        sold_out_at = listing.sold_out_at

        listing.title = "Renamed tomatoes"
        listing.save()
        listing.refresh_from_db()

        self.assertEqual(listing.sold_out_at, sold_out_at)

    def test_status_change_is_ignored_when_update_fields_excludes_status(self):
        listing = self.make_listing()
        listing.save()
        listing.status = Listing.Status.SOLD_OUT

        listing.save(update_fields=["title"])
        listing.refresh_from_db()

        self.assertEqual(listing.status, Listing.Status.ACTIVE)
        self.assertIsNone(listing.sold_out_at)

    def test_iterator_update_fields_persists_title_without_status_transition(self):
        listing = self.make_listing()
        listing.save()
        listing.title = "Renamed tomatoes"
        listing.status = Listing.Status.SOLD_OUT

        listing.save(update_fields=iter(["title"]))
        self.assertIsNone(listing.sold_out_at)
        listing.refresh_from_db()

        self.assertEqual(listing.title, "Renamed tomatoes")
        self.assertEqual(listing.status, Listing.Status.ACTIVE)
        self.assertIsNone(listing.sold_out_at)

    def test_empty_update_fields_does_not_write_sold_out_timestamp(self):
        listing = self.make_listing()
        listing.save()
        listing.status = Listing.Status.SOLD_OUT

        listing.save(update_fields=[])
        listing.refresh_from_db()

        self.assertEqual(listing.status, Listing.Status.ACTIVE)
        self.assertIsNone(listing.sold_out_at)

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

    def test_cover_image_uses_first_position(self):
        self.upload(filename="second.png", position=1)
        first = self.upload(filename="first.png", position=0)

        self.assertEqual(self.listing.cover_image, first)

    def test_deleting_image_removes_file_after_commit(self):
        image = self.upload()
        storage = image.image.storage
        name = image.image.name

        with self.captureOnCommitCallbacks(execute=True):
            image.delete()

        self.assertFalse(storage.exists(name))

    def test_deleting_listing_removes_cascaded_image_files(self):
        image = self.upload()
        storage = image.image.storage
        name = image.image.name

        with self.captureOnCommitCallbacks(execute=True):
            self.listing.delete()

        self.assertFalse(storage.exists(name))

    def test_failed_file_cleanup_allows_later_cleanup_callbacks(self):
        first = self.upload(filename="first.png")
        second = self.upload(filename="second.png")
        storage = first.image.storage
        first_name = first.image.name
        second_name = second.image.name
        delete = storage.delete

        def delete_with_failure(name):
            if name == first_name:
                raise OSError("Storage unavailable")
            delete(name)

        with mock.patch.object(
            storage, "delete", side_effect=delete_with_failure
        ) as mocked_delete:
            with self.assertLogs("django.test", level="ERROR"):
                with self.captureOnCommitCallbacks(execute=True):
                    first.delete()
                    second.delete()

        self.assertEqual(
            mocked_delete.call_args_list,
            [mock.call(first_name), mock.call(second_name)],
        )
        self.assertFalse(ListingImage.objects.exists())
        self.assertTrue(storage.exists(first_name))
        self.assertFalse(storage.exists(second_name))

    def test_rollback_keeps_image_file(self):
        image = self.upload()
        storage = image.image.storage
        name = image.image.name

        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                image.delete()
                raise RuntimeError("change rejected")

        self.assertTrue(storage.exists(name))


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
)
class ListingImageStorageTests(TestCase):
    """Listings must work without local disk, as on Supabase Storage."""

    def setUp(self):
        self.farmer = create_farmer("storage-farmer")
        self.category = Category.objects.create(name="Storage Produce")
        self.listing = Listing.objects.create(
            farmer=self.farmer,
            category=self.category,
            title="Stored tomatoes",
            description="Fresh from the farm.",
            price=Decimal("120.00"),
        )

    def test_image_round_trips_through_default_storage(self):
        image = ListingImage.objects.create(
            listing=self.listing,
            image=uploaded_image("stored.png"),
        )
        storage = storages["default"]

        self.assertEqual(type(storage).__name__, "InMemoryStorage")
        self.assertTrue(storage.exists(image.image.name))
        self.assertTrue(image.image.url.startswith(settings.MEDIA_URL))

        with storage.open(image.image.name, "rb") as stored:
            self.assertEqual(stored.read(), image_bytes())

    def test_detail_page_renders_storage_url(self):
        image = ListingImage.objects.create(
            listing=self.listing,
            image=uploaded_image("stored.png"),
        )

        response = self.client.get(
            reverse("listing_detail", args=[self.listing.public_id])
        )

        self.assertContains(response, image.image.url)


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
)
class ListingFormTests(TestCase):
    def setUp(self):
        self.farmer = create_farmer()
        self.category = Category.objects.create(name="Test Produce")
        self.media_root = tempfile.mkdtemp()
        self.media_override = override_settings(MEDIA_ROOT=self.media_root)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)

    def valid_data(self, **overrides):
        data = {
            "title": "Fresh tomatoes",
            "category": self.category.pk,
            "condition": Listing.Condition.FRESH,
            "description": "Picked this morning.",
            "price": "120.00",
            "unit": Listing.Unit.KILOGRAM,
            "stock_quantity": "25",
            "status": Listing.Status.ACTIVE,
        }
        data.update(overrides)
        return data

    def test_create_requires_at_least_one_photo(self):
        form = ListingForm(data=self.valid_data())

        self.assertFalse(form.is_valid())
        self.assertIn("images", form.errors)

    def test_create_accepts_one_photo(self):
        form = ListingForm(
            data=self.valid_data(),
            files={"images": [uploaded_image()]},
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_upload_strips_exif_gps_and_applies_orientation(self):
        upload = SimpleUploadedFile(
            "farm.jpg",
            gps_jpeg_bytes(),
            content_type="image/jpeg",
        )
        form = ListingForm(
            data=self.valid_data(),
            files={"images": [upload]},
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.instance.farmer = self.farmer

        listing = form.save()
        stored = listing.images.get()

        with stored.image.open("rb") as file:
            with Image.open(file) as saved:
                self.assertEqual(saved.size, (10, 20))
                self.assertEqual(dict(saved.getexif()), {})
                self.assertEqual(dict(saved.getexif().get_ifd(0x8825)), {})

    def test_upload_rejects_unsupported_image_formats(self):
        buffer = io.BytesIO()
        Image.new("RGB", (20, 20), "green").save(buffer, format="BMP")
        upload = SimpleUploadedFile(
            "farm.bmp",
            buffer.getvalue(),
            content_type="image/bmp",
        )

        form = ListingForm(
            data=self.valid_data(),
            files={"images": [upload]},
        )

        self.assertFalse(form.is_valid())
        self.assertIn("JPEG, PNG, or WebP", form.errors["images"][0])

    def test_upload_extension_matches_detected_format(self):
        upload = SimpleUploadedFile(
            "farm.png",
            gps_jpeg_bytes(),
            content_type="image/png",
        )
        form = ListingForm(
            data=self.valid_data(),
            files={"images": [upload]},
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.instance.farmer = self.farmer

        listing = form.save()

        self.assertTrue(listing.images.get().image.name.endswith(".jpg"))

    def test_upload_rejects_images_over_pixel_limit(self):
        with mock.patch.object(Image, "MAX_IMAGE_PIXELS", 300):
            form = ListingForm(
                data=self.valid_data(),
                files={"images": [uploaded_image()]},
            )
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", Image.DecompressionBombWarning)
                self.assertFalse(form.is_valid())

        self.assertIn("too large", form.errors["images"][0])

    def test_create_rejects_more_than_five_photos(self):
        form = ListingForm(
            data=self.valid_data(),
            files={
                "images": [
                    uploaded_image(f"photo-{index}.png") for index in range(6)
                ]
            },
        )

        self.assertFalse(form.is_valid())
        self.assertIn("images", form.errors)

    def test_too_many_photos_rejected_before_image_validation(self):
        files = [
            SimpleUploadedFile(
                f"broken-{index}.png",
                b"not an image",
                content_type="image/png",
            )
            for index in range(6)
        ]

        form = ListingForm(
            data=self.valid_data(),
            files={"images": files},
        )

        self.assertFalse(form.is_valid())
        self.assertIn("Add at most 5 photos.", form.errors["images"][0])

    def test_oversized_photo_rejected_before_image_validation(self):
        upload = SimpleUploadedFile(
            "huge.png",
            b"x" * (5 * 1024 * 1024 + 1),
            content_type="image/png",
        )

        form = ListingForm(
            data=self.valid_data(),
            files={"images": [upload]},
        )

        self.assertFalse(form.is_valid())
        self.assertIn("smaller than 5 MB", form.errors["images"][0])

    def test_free_listing_needs_no_price(self):
        form = ListingForm(
            data=self.valid_data(is_free="on", price=""),
            files={"images": [uploaded_image()]},
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_free_listing_rejects_price(self):
        form = ListingForm(
            data=self.valid_data(is_free="on"),
            files={"images": [uploaded_image()]},
        )

        self.assertFalse(form.is_valid())
        self.assertIn("price", form.errors)

    def test_meetup_requires_location(self):
        form = ListingForm(
            data=self.valid_data(meetup="on", meetup_location=""),
            files={"images": [uploaded_image()]},
        )

        self.assertFalse(form.is_valid())
        self.assertIn("meetup_location", form.errors)

    def test_sold_out_listing_accepts_blank_restock_note(self):
        form = ListingForm(
            data=self.valid_data(
                status=Listing.Status.SOLD_OUT,
                status_note="",
            ),
            files={"images": [uploaded_image()]},
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_edit_accepts_existing_photo_without_new_upload(self):
        listing = Listing.objects.create(
            farmer=self.farmer,
            category=self.category,
            title="Existing",
            description="Already has a photo.",
            price=Decimal("50.00"),
        )
        ListingImage.objects.create(listing=listing, image=uploaded_image())

        form = ListingForm(
            data=self.valid_data(title="Existing"),
            instance=listing,
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_edit_rejects_removing_the_last_photo(self):
        listing = Listing.objects.create(
            farmer=self.farmer,
            category=self.category,
            title="Existing",
            description="Already has a photo.",
            price=Decimal("50.00"),
        )
        image = ListingImage.objects.create(
            listing=listing,
            image=uploaded_image(),
        )

        form = ListingForm(
            data=self.valid_data(
                title="Existing",
                remove_images=[image.pk],
            ),
            instance=listing,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("images", form.errors)

    def test_edit_counts_existing_and_new_photos_together(self):
        listing = Listing.objects.create(
            farmer=self.farmer,
            category=self.category,
            title="Existing",
            description="Already has a photo.",
            price=Decimal("50.00"),
        )
        ListingImage.objects.create(listing=listing, image=uploaded_image())

        form = ListingForm(
            data=self.valid_data(title="Existing"),
            files={
                "images": [
                    uploaded_image(f"new-{index}.png") for index in range(5)
                ]
            },
            instance=listing,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("images", form.errors)

    def test_failed_photo_upload_rolls_back_new_listing(self):
        written_files = []
        real_save = ListingImage.save

        def fail_after_first_upload(instance, *args, **kwargs):
            if written_files:
                raise RuntimeError("storage failed")
            result = real_save(instance, *args, **kwargs)
            written_files.append(instance.image.name)
            return result

        form = ListingForm(
            data=self.valid_data(),
            files={
                "images": [
                    uploaded_image("first.png"),
                    uploaded_image("second.png"),
                ]
            },
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.instance.farmer = self.farmer

        with mock.patch.object(
            ListingImage,
            "save",
            autospec=True,
            side_effect=fail_after_first_upload,
        ):
            with self.assertRaises(RuntimeError):
                form.save()

        self.assertFalse(Listing.objects.filter(title="Fresh tomatoes").exists())
        self.assertEqual(ListingImage.objects.count(), 0)
        self.assertEqual(len(written_files), 1)
        self.assertFalse(storages["default"].exists(written_files[0]))

    def test_failed_upload_restores_removed_photo_and_listing(self):
        listing = Listing.objects.create(
            farmer=self.farmer,
            category=self.category,
            title="Existing",
            description="Already has a photo.",
            price=Decimal("50.00"),
        )
        existing = ListingImage.objects.create(
            listing=listing,
            image=uploaded_image("existing.png"),
        )
        existing_name = existing.image.name

        form = ListingForm(
            data=self.valid_data(
                title="Renamed",
                remove_images=[existing.pk],
            ),
            files={"images": [uploaded_image("replacement.png")]},
            instance=listing,
        )
        self.assertTrue(form.is_valid(), form.errors)

        with mock.patch.object(
            ListingImage,
            "save",
            autospec=True,
            side_effect=RuntimeError("storage failed"),
        ):
            with self.assertRaises(RuntimeError):
                form.save()

        listing.refresh_from_db()
        self.assertEqual(listing.title, "Existing")
        self.assertTrue(ListingImage.objects.filter(pk=existing.pk).exists())
        self.assertTrue(storages["default"].exists(existing_name))


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
)
class ListingViewTests(TestCase):
    def setUp(self):
        self.farmer = create_farmer()
        self.other_farmer = create_farmer("other-farmer")
        self.buyer = User.objects.create_user(
            "listing-buyer",
            email="listing-buyer@example.com",
            password="temporary-pass-1",
        )
        self.category = Category.objects.create(name="View Produce")
        self.media_root = tempfile.mkdtemp()
        self.media_override = override_settings(MEDIA_ROOT=self.media_root)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)

        self.listing = Listing.objects.create(
            farmer=self.farmer,
            category=self.category,
            title="Existing tomatoes",
            description="Already listed.",
            price=Decimal("100.00"),
        )
        self.add_image(self.listing)

    def add_image(self, listing, filename="existing.png"):
        return ListingImage.objects.create(
            listing=listing,
            image=uploaded_image(filename),
            position=listing.images.count(),
        )

    def create_listings(self, count, status=Listing.Status.ACTIVE):
        Listing.objects.bulk_create(
            Listing(
                farmer=self.farmer,
                category=self.category,
                title=f"Bulk listing {index}",
                description="Bulk listing.",
                price=Decimal("10.00"),
                status=status,
            )
            for index in range(count)
        )

    def valid_data(self, **overrides):
        data = {
            "title": "Fresh tomatoes",
            "category": self.category.pk,
            "condition": Listing.Condition.FRESH,
            "description": "Picked this morning.",
            "price": "120.00",
            "unit": Listing.Unit.KILOGRAM,
            "stock_quantity": "25",
            "status": Listing.Status.ACTIVE,
        }
        data.update(overrides)
        return data

    def test_create_requires_login(self):
        response = self.client.get(reverse("listing_create"))

        self.assertRedirects(
            response,
            f"{reverse('account_login')}?next={reverse('listing_create')}",
        )

    def test_buyer_cannot_create_listing(self):
        self.client.force_login(self.buyer)

        response = self.client.get(reverse("listing_create"))

        self.assertEqual(response.status_code, 403)

    def test_farmer_can_create_listing_with_photo(self):
        self.client.force_login(self.farmer)

        response = self.client.post(
            reverse("listing_create"),
            {
                **self.valid_data(),
                "images": uploaded_image("cover.png"),
            },
        )

        self.assertRedirects(response, reverse("my_listings"))
        listing = Listing.objects.get(title="Fresh tomatoes")
        self.assertEqual(listing.farmer, self.farmer)
        self.assertEqual(listing.images.count(), 1)

    def test_create_page_redirects_when_open_listing_limit_is_reached(self):
        self.create_listings(Listing.MAX_OPEN_LISTINGS - 1)
        Listing.objects.filter(farmer=self.farmer).update(
            created_at=timezone.now() - timedelta(days=2)
        )
        self.client.force_login(self.farmer)

        response = self.client.get(reverse("listing_create"), follow=True)

        self.assertEqual(
            response.redirect_chain,
            [(reverse("my_listings"), 302)],
        )
        self.assertContains(response, "Archive or delete one")

    def test_create_is_blocked_when_open_listing_limit_is_reached(self):
        self.create_listings(Listing.MAX_OPEN_LISTINGS - 1)
        Listing.objects.filter(farmer=self.farmer).update(
            created_at=timezone.now() - timedelta(days=2)
        )
        self.client.force_login(self.farmer)

        response = self.client.post(
            reverse("listing_create"),
            {
                **self.valid_data(),
                "images": uploaded_image("cover.png"),
            },
            follow=True,
        )

        self.assertEqual(
            response.redirect_chain,
            [(reverse("my_listings"), 302)],
        )
        self.assertContains(response, "Archive or delete one")
        self.assertFalse(Listing.objects.filter(title="Fresh tomatoes").exists())

    def test_create_is_blocked_after_daily_limit(self):
        self.create_listings(
            Listing.MAX_LISTINGS_PER_DAY - 1,
            status=Listing.Status.ARCHIVED,
        )
        self.client.force_login(self.farmer)

        response = self.client.post(
            reverse("listing_create"),
            {
                **self.valid_data(),
                "images": uploaded_image("cover.png"),
            },
            follow=True,
        )

        self.assertEqual(
            response.redirect_chain,
            [(reverse("my_listings"), 302)],
        )
        self.assertContains(response, "in 24 hours")
        self.assertFalse(Listing.objects.filter(title="Fresh tomatoes").exists())

    def test_create_rejects_listing_without_photo(self):
        self.client.force_login(self.farmer)

        response = self.client.post(
            reverse("listing_create"),
            self.valid_data(),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add at least one photo.")
        self.assertFalse(Listing.objects.filter(title="Fresh tomatoes").exists())

    def test_owner_can_update_listing(self):
        self.client.force_login(self.farmer)

        response = self.client.post(
            reverse("listing_update", args=[self.listing.public_id]),
            self.valid_data(title="Updated tomatoes"),
        )

        self.assertRedirects(response, reverse("my_listings"))
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.title, "Updated tomatoes")
        self.assertEqual(self.listing.images.count(), 1)

    def test_non_owner_cannot_update_listing(self):
        self.client.force_login(self.other_farmer)

        response = self.client.get(
            reverse("listing_update", args=[self.listing.public_id])
        )

        self.assertEqual(response.status_code, 404)

    def test_buyer_cannot_update_listing(self):
        self.client.force_login(self.buyer)

        response = self.client.get(
            reverse("listing_update", args=[self.listing.public_id])
        )

        self.assertEqual(response.status_code, 404)

    def test_owner_can_delete_listing(self):
        self.client.force_login(self.farmer)

        response = self.client.get(
            reverse("listing_delete", args=[self.listing.public_id])
        )

        self.assertEqual(response.status_code, 200)

        response = self.client.post(
            reverse("listing_delete", args=[self.listing.public_id])
        )

        self.assertRedirects(response, reverse("my_listings"))
        self.assertFalse(Listing.objects.filter(pk=self.listing.pk).exists())

    def test_non_owner_cannot_delete_listing(self):
        self.client.force_login(self.other_farmer)

        response = self.client.post(
            reverse("listing_delete", args=[self.listing.public_id])
        )

        self.assertEqual(response.status_code, 404)

    def test_my_listings_only_shows_own(self):
        other_listing = Listing.objects.create(
            farmer=self.other_farmer,
            category=self.category,
            title="Someone else's tomatoes",
            description="Not mine.",
            price=Decimal("90.00"),
        )
        self.client.force_login(self.farmer)

        response = self.client.get(reverse("my_listings"))

        self.assertContains(response, self.listing.title)
        self.assertNotContains(response, other_listing.title)

    def test_my_listings_shows_restock_note(self):
        self.listing.status = Listing.Status.SOLD_OUT
        self.listing.status_note = "Back in stock Friday."
        self.listing.save()
        self.client.force_login(self.farmer)

        response = self.client.get(reverse("my_listings"))

        self.assertContains(response, "Sold out")
        self.assertContains(response, "Back in stock Friday.")

    def test_my_listings_paginates(self):
        self.create_listings(LISTINGS_PER_PAGE)
        self.client.force_login(self.farmer)

        first_page = self.client.get(reverse("my_listings"))
        second_page = self.client.get(reverse("my_listings"), {"page": 2})

        self.assertEqual(
            first_page.context["page_obj"].paginator.count,
            LISTINGS_PER_PAGE + 1,
        )
        self.assertEqual(
            len(first_page.context["listings"]),
            LISTINGS_PER_PAGE,
        )
        self.assertEqual(len(second_page.context["listings"]), 1)
        self.assertContains(first_page, "Page 1 of 2")
        self.assertContains(second_page, "Page 2 of 2")

    def test_my_listings_query_count_is_constant(self):
        self.client.force_login(self.farmer)

        with CaptureQueriesContext(connection) as one_listing:
            self.client.get(reverse("my_listings"))

        self.create_listings(5)

        with CaptureQueriesContext(connection) as many_listings:
            self.client.get(reverse("my_listings"))

        self.assertEqual(
            len(many_listings.captured_queries),
            len(one_listing.captured_queries),
        )

    def test_buyer_cannot_open_my_listings(self):
        self.client.force_login(self.buyer)

        response = self.client.get(reverse("my_listings"))

        self.assertEqual(response.status_code, 403)

    def test_owner_can_remove_one_photo(self):
        second = self.add_image(self.listing, "second.png")
        self.client.force_login(self.farmer)

        response = self.client.post(
            reverse("listing_update", args=[self.listing.public_id]),
            {
                **self.valid_data(title=self.listing.title),
                "remove_images": [second.pk],
            },
        )

        self.assertRedirects(response, reverse("my_listings"))
        self.assertEqual(self.listing.images.count(), 1)

    def test_owner_can_add_a_photo(self):
        self.client.force_login(self.farmer)

        response = self.client.post(
            reverse("listing_update", args=[self.listing.public_id]),
            {
                **self.valid_data(title=self.listing.title),
                "images": uploaded_image("added.png"),
            },
        )

        self.assertRedirects(response, reverse("my_listings"))
        self.assertEqual(self.listing.images.count(), 2)


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
)
class ListingBrowseTests(TestCase):
    def setUp(self):
        self.farmer = create_farmer("browse-farmer")
        self.category = Category.objects.create(name="Browse Vegetables")
        self.other_category = Category.objects.create(name="Browse Fruit")
        self.media_root = tempfile.mkdtemp()
        self.media_override = override_settings(MEDIA_ROOT=self.media_root)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)

        self.active = self.make_listing(
            "Active tomatoes",
            description="Leafy greens from the farm.",
            meetup=True,
            meetup_location="Public market",
        )
        self.sold_out = self.make_listing(
            "Sold out mangoes",
            category=self.other_category,
            condition=Listing.Condition.RIPE,
            price=Decimal("80.00"),
            status=Listing.Status.SOLD_OUT,
        )
        self.free = self.make_listing(
            "Free lemons",
            description="A giveaway box.",
            price=None,
            is_free=True,
        )
        self.draft = self.make_listing(
            "Draft squash",
            status=Listing.Status.DRAFT,
        )
        self.archived = self.make_listing(
            "Archived corn",
            status=Listing.Status.ARCHIVED,
        )

    def make_listing(self, title, **overrides):
        data = {
            "farmer": self.farmer,
            "category": self.category,
            "title": title,
            "description": "Fresh from the farm.",
            "price": Decimal("100.00"),
            "stock_quantity": Decimal("10"),
            "meetup": True,
            "meetup_location": "Public market",
        }
        data.update(overrides)
        return Listing.objects.create(**data)

    def test_root_redirects_to_listings(self):
        response = self.client.get("/")

        self.assertRedirects(response, reverse("listings"))

    def test_browse_shows_only_public_statuses(self):
        response = self.client.get(reverse("listings"))

        self.assertContains(response, self.active.title)
        self.assertContains(response, self.sold_out.title)
        self.assertContains(response, self.free.title)
        self.assertNotContains(response, self.draft.title)
        self.assertNotContains(response, self.archived.title)

    def test_search_matches_title_description_and_category(self):
        cases = (
            ("tomatoes", self.active.title),
            ("leafy", self.active.title),
            ("Browse Fruit", self.sold_out.title),
            ("browse-farmer", self.active.title),
        )

        for query, expected in cases:
            with self.subTest(query=query):
                response = self.client.get(reverse("listings"), {"q": query})
                self.assertContains(response, expected)

    def test_search_query_is_capped(self):
        response = self.client.get(reverse("listings"), {"q": "a" * 500})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            len(response.context["query"]),
            SEARCH_QUERY_MAX_LENGTH,
        )

    def test_browse_filters_by_category(self):
        response = self.client.get(
            reverse("listings"),
            {"category": self.other_category.slug},
        )

        self.assertContains(response, self.sold_out.title)
        self.assertNotContains(response, self.active.title)

    def test_browse_filters_by_condition(self):
        response = self.client.get(
            reverse("listings"),
            {"condition": Listing.Condition.RIPE},
        )

        self.assertContains(response, self.sold_out.title)
        self.assertNotContains(response, self.active.title)

    def test_browse_filters_free_and_paid(self):
        free_response = self.client.get(
            reverse("listings"),
            {"pricing": "free"},
        )
        paid_response = self.client.get(
            reverse("listings"),
            {"pricing": "paid"},
        )

        self.assertContains(free_response, self.free.title)
        self.assertNotContains(free_response, self.active.title)
        self.assertContains(paid_response, self.active.title)
        self.assertNotContains(paid_response, self.free.title)

    def test_browse_ignores_unknown_condition(self):
        response = self.client.get(
            reverse("listings"),
            {"condition": "not-a-condition"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.active.title)

    def test_browse_paginates_listings(self):
        for index in range(25):
            self.make_listing(f"Bulk listing {index}")

        first_page = self.client.get(reverse("listings"))
        second_page = self.client.get(reverse("listings"), {"page": 2})

        self.assertEqual(first_page.context["page_obj"].paginator.count, 28)
        self.assertEqual(len(first_page.context["page_obj"]), 24)
        self.assertEqual(len(second_page.context["page_obj"]), 4)

    def test_browse_count_does_not_join_likes(self):
        with CaptureQueriesContext(connection) as queries:
            self.client.get(reverse("listings"))

        count_queries = [
            query["sql"]
            for query in queries.captured_queries
            if '"__count"' in query["sql"]
        ]

        self.assertEqual(len(count_queries), 1)
        self.assertNotIn("listinglike", count_queries[0].lower())

    def test_detail_renders_listing(self):
        response = self.client.get(
            reverse("listing_detail", args=[self.active.public_id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.active.title)
        self.assertContains(response, self.active.description)
        self.assertContains(response, "₱100.00")
        self.assertContains(response, "Public market")
        self.assertContains(response, self.farmer.username)

    def test_detail_shows_sold_out_note(self):
        self.sold_out.status_note = "Back in stock next week."
        self.sold_out.save(update_fields=["status_note"])

        response = self.client.get(
            reverse("listing_detail", args=[self.sold_out.public_id])
        )

        self.assertContains(response, "Sold out")
        self.assertContains(response, "Back in stock next week.")

    def test_detail_hides_unpublished_listings_from_public(self):
        for listing in (self.draft, self.archived):
            with self.subTest(status=listing.status):
                response = self.client.get(
                    reverse("listing_detail", args=[listing.public_id])
                )
                self.assertEqual(response.status_code, 404)

    def test_owner_can_preview_unpublished_listing(self):
        self.client.force_login(self.farmer)

        response = self.client.get(
            reverse("listing_detail", args=[self.draft.public_id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your listing is currently draft.")

    def test_unknown_listing_returns_404(self):
        response = self.client.get(
            reverse("listing_detail", args=[uuid.uuid4()])
        )

        self.assertEqual(response.status_code, 404)

    def test_detail_uses_storage_url_for_cover(self):
        image = ListingImage.objects.create(
            listing=self.active,
            image=uploaded_image("cover.png"),
            position=0,
        )

        response = self.client.get(
            reverse("listing_detail", args=[self.active.public_id])
        )

        self.assertContains(response, image.image.url)
        self.assertTrue(image.image.url.startswith("/media/"))


class ListingLikeViewTests(TestCase):
    def setUp(self):
        self.farmer = create_farmer("like-farmer")
        self.buyer = User.objects.create_user(
            "like-buyer",
            email="like-buyer@example.com",
            password="temporary-pass-1",
        )
        self.other_buyer = User.objects.create_user(
            "other-like-buyer",
            email="other-like-buyer@example.com",
            password="temporary-pass-1",
        )
        self.category = Category.objects.create(name="Like Produce")
        self.listing = self.make_listing("Liked tomatoes")
        self.other_listing = self.make_listing("Other tomatoes")
        self.draft = self.make_listing(
            "Draft tomatoes",
            status=Listing.Status.DRAFT,
        )

    def make_listing(self, title, **overrides):
        data = {
            "farmer": self.farmer,
            "category": self.category,
            "title": title,
            "description": "Fresh from the farm.",
            "price": Decimal("100.00"),
            "stock_quantity": Decimal("10"),
        }
        data.update(overrides)
        return Listing.objects.create(**data)

    def like_url(self, listing):
        return reverse("listing_like_toggle", args=[listing.public_id])

    def detail_url(self, listing):
        return reverse("listing_detail", args=[listing.public_id])

    def test_like_toggle_requires_login(self):
        response = self.client.post(self.like_url(self.listing))

        self.assertRedirects(
            response,
            f"{reverse('account_login')}?next={self.like_url(self.listing)}",
        )
        self.assertFalse(ListingLike.objects.exists())

    def test_like_toggle_saves_listing(self):
        self.client.force_login(self.buyer)

        response = self.client.post(self.like_url(self.listing))

        self.assertRedirects(response, self.detail_url(self.listing))
        self.assertTrue(
            ListingLike.objects.filter(
                user=self.buyer,
                listing=self.listing,
            ).exists()
        )
        detail = self.client.get(self.detail_url(self.listing))
        self.assertContains(detail, "♥ Saved")

    def test_second_toggle_removes_like(self):
        ListingLike.objects.create(user=self.buyer, listing=self.listing)
        self.client.force_login(self.buyer)

        response = self.client.post(self.like_url(self.listing))

        self.assertRedirects(response, self.detail_url(self.listing))
        self.assertFalse(
            ListingLike.objects.filter(
                user=self.buyer,
                listing=self.listing,
            ).exists()
        )
        detail = self.client.get(self.detail_url(self.listing))
        self.assertContains(detail, "♡ Save")

    def test_like_toggle_returns_partial_for_htmx(self):
        self.client.force_login(self.buyer)

        response = self.client.post(
            self.like_url(self.listing),
            headers={"HX-Request": "true"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "listings/_like_button.html")
        self.assertContains(response, "♥ Saved")
        self.assertTrue(response.context["is_liked"])

    def test_like_toggle_rejects_get(self):
        self.client.force_login(self.buyer)

        response = self.client.get(self.like_url(self.listing))

        self.assertEqual(response.status_code, 405)
        self.assertFalse(ListingLike.objects.exists())

    def test_unpublished_listing_cannot_be_liked(self):
        self.client.force_login(self.buyer)

        response = self.client.post(self.like_url(self.draft))

        self.assertEqual(response.status_code, 404)
        self.assertFalse(ListingLike.objects.exists())

    def test_liked_listings_requires_login(self):
        response = self.client.get(reverse("liked_listings"))

        self.assertRedirects(
            response,
            f"{reverse('account_login')}?next={reverse('liked_listings')}",
        )

    def test_liked_listings_shows_only_own_saved_listings(self):
        ListingLike.objects.create(user=self.buyer, listing=self.listing)
        ListingLike.objects.create(
            user=self.other_buyer,
            listing=self.other_listing,
        )
        ListingLike.objects.create(user=self.buyer, listing=self.draft)
        self.client.force_login(self.buyer)

        response = self.client.get(reverse("liked_listings"))

        self.assertContains(response, self.listing.title)
        self.assertNotContains(response, self.other_listing.title)
        self.assertNotContains(response, self.draft.title)

    def test_liked_listings_keeps_sold_out_listings(self):
        sold_out = self.make_listing(
            "Sold out tomatoes",
            status=Listing.Status.SOLD_OUT,
            status_note="Back next week.",
        )
        ListingLike.objects.create(user=self.buyer, listing=sold_out)
        self.client.force_login(self.buyer)

        response = self.client.get(reverse("liked_listings"))

        self.assertContains(response, sold_out.title)
        self.assertContains(response, "Sold out")
        self.assertContains(response, "Back next week.")

    def test_liked_listings_counts_all_likes(self):
        ListingLike.objects.create(user=self.buyer, listing=self.listing)
        ListingLike.objects.create(
            user=self.other_buyer,
            listing=self.listing,
        )
        self.client.force_login(self.buyer)

        response = self.client.get(reverse("liked_listings"))

        self.assertContains(response, "2 likes")

    def test_liked_listings_paginates(self):
        ListingLike.objects.create(user=self.buyer, listing=self.listing)
        for index in range(LISTINGS_PER_PAGE):
            listing = self.make_listing(f"Saved listing {index}")
            ListingLike.objects.create(user=self.buyer, listing=listing)
        self.client.force_login(self.buyer)

        first_page = self.client.get(reverse("liked_listings"))
        second_page = self.client.get(reverse("liked_listings"), {"page": 2})

        self.assertEqual(
            first_page.context["page_obj"].paginator.count,
            LISTINGS_PER_PAGE + 1,
        )
        self.assertEqual(
            len(first_page.context["listings"]),
            LISTINGS_PER_PAGE,
        )
        self.assertEqual(len(second_page.context["listings"]), 1)
        self.assertContains(first_page, "Page 1 of 2")
        self.assertContains(second_page, "Page 2 of 2")


class ListingAdminTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            "admin",
            email="admin@example.com",
            password="temporary-pass-1",
        )
        self.farmer = create_farmer()
        self.buyer = User.objects.create_user(
            "admin-buyer",
            email="admin-buyer@example.com",
            password="temporary-pass-1",
        )
        self.category = Category.objects.create(name="Admin Produce")
        self.listing = Listing.objects.create(
            farmer=self.farmer,
            category=self.category,
            title="Admin tomatoes",
            description="Fresh from the farm.",
            price=Decimal("120.00"),
        )
        ListingLike.objects.create(user=self.buyer, listing=self.listing)
        self.client.force_login(self.admin)

    def test_admin_changelists_render(self):
        pages = (
            reverse("admin:listings_category_changelist"),
            reverse("admin:listings_listing_changelist"),
            reverse("admin:listings_listingimage_changelist"),
            reverse("admin:listings_listinglike_changelist"),
        )

        for url in pages:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)

    def test_listing_change_page_renders_images_and_likes(self):
        response = self.client.get(
            reverse("admin:listings_listing_change", args=[self.listing.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Admin tomatoes")
        self.assertContains(response, "Likes")


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


class DeleteDemoListingsCommandTests(TestCase):
    """Demo data must be removable without touching real listings."""

    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.media_override = override_settings(MEDIA_ROOT=self.media_root)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)
        self.category = Category.objects.create(name="Demo Produce")

        self.demo_farmer = User.objects.create_user(
            "demo-farmer",
            email="demo-farmer@example.com",
            password="temporary-pass-1",
        )
        self.demo_listing = self.make_listing(self.demo_farmer, "Demo tomatoes")

        self.real_farmer = create_farmer("real-farmer")
        self.real_listing = self.make_listing(self.real_farmer, "Real tomatoes")

    def make_listing(self, farmer, title):
        return Listing.objects.create(
            farmer=farmer,
            category=self.category,
            title=title,
            description="Fixture listing.",
            price=Decimal("10.00"),
        )

    def test_dry_run_reports_without_deleting(self):
        output = StringIO()

        call_command("delete_demo_listings", "--dry-run", stdout=output)

        self.assertIn("Would delete", output.getvalue())
        self.assertIn("1 listing(s)", output.getvalue())
        self.assertTrue(Listing.objects.filter(pk=self.demo_listing.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.demo_farmer.pk).exists())

    def test_command_deletes_demo_data_and_keeps_real_listings(self):
        output = StringIO()

        call_command("delete_demo_listings", stdout=output)

        self.assertIn("Deleted", output.getvalue())
        self.assertFalse(Listing.objects.filter(pk=self.demo_listing.pk).exists())
        self.assertFalse(User.objects.filter(pk=self.demo_farmer.pk).exists())
        self.assertTrue(Listing.objects.filter(pk=self.real_listing.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.real_farmer.pk).exists())

    def test_command_reports_when_there_is_nothing_to_delete(self):
        self.demo_farmer.delete()
        output = StringIO()

        call_command("delete_demo_listings", stdout=output)

        self.assertIn("No demo listings found", output.getvalue())
