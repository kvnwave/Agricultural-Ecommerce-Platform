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
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from accounts.models import Profile, User

from .forms import ListingForm
from .models import Category, Listing, ListingImage, ListingLike


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
