import io
import shutil
import tempfile
from pathlib import Path

from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from .models import Profile, User


def image_bytes():
    buffer = io.BytesIO()
    Image.new("RGB", (20, 20), "green").save(buffer, format="PNG")
    return buffer.getvalue()


class UserModelTests(TestCase):
    def test_custom_user_model_is_active(self):
        self.assertIs(get_user_model(), User)
        self.assertTrue(User._meta.get_field("email").unique)

    def test_profile_is_created_once_per_user(self):
        user = User.objects.create_user(
            "buyer", email="buyer@example.com", password="temporary-pass-1"
        )

        self.assertEqual(user.profile.role, Profile.Role.BUYER)

        Profile.objects.get_or_create(user=user)
        self.assertEqual(Profile.objects.filter(user=user).count(), 1)

    def test_duplicate_email_is_rejected(self):
        User.objects.create_user(
            "first", email="same@example.com", password="temporary-pass-1"
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                User.objects.create_user(
                    "second", email="same@example.com", password="temporary-pass-1"
                )


class AuthPageTests(TestCase):
    def test_auth_pages_render(self):
        pages = {
            "account_login": "Sign In",
            "account_signup": "Signup",
            "account_reset_password": "Password Reset",
        }

        for url_name, title in pages.items():
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, title)


class SignupFlowTests(TestCase):
    password = "temporary-pass-1"

    def test_signup_page_offers_both_account_types(self):
        response = self.client.get(reverse("account_signup"))

        self.assertContains(response, "Account type")
        self.assertContains(response, "Buyer")
        self.assertContains(response, "Farmer")

    def test_signup_creates_user_profile_and_verification_email(self):
        response = self.client.post(
            reverse("account_signup"),
            {
                "role": Profile.Role.BUYER,
                "email": "new@example.com",
                "password1": self.password,
                "password2": self.password,
            },
        )

        self.assertRedirects(
            response,
            reverse("account_email_verification_sent"),
            fetch_redirect_response=False,
        )

        user = User.objects.get(email="new@example.com")
        self.assertEqual(user.profile.role, Profile.Role.BUYER)
        self.assertFalse(user.emailaddress_set.get(email=user.email).verified)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("confirm", mail.outbox[0].body.lower())

    def test_signup_does_not_duplicate_an_existing_email(self):
        User.objects.create_user(
            "existing", email="taken@example.com", password=self.password
        )

        response = self.client.post(
            reverse("account_signup"),
            {
                "role": Profile.Role.BUYER,
                "email": "taken@example.com",
                "password1": self.password,
                "password2": self.password,
            },
        )

        # allauth hides whether the address is already registered, so it
        # redirects to the same confirmation page instead of creating a user.
        self.assertRedirects(
            response,
            reverse("account_email_verification_sent"),
            fetch_redirect_response=False,
        )
        self.assertEqual(User.objects.filter(email="taken@example.com").count(), 1)

    def test_signup_creates_farmer_account(self):
        response = self.client.post(
            reverse("account_signup"),
            {
                "role": Profile.Role.FARMER,
                "email": "farmer@example.com",
                "password1": self.password,
                "password2": self.password,
            },
        )

        self.assertRedirects(
            response,
            reverse("account_email_verification_sent"),
            fetch_redirect_response=False,
        )
        user = User.objects.get(email="farmer@example.com")
        self.assertEqual(user.profile.role, Profile.Role.FARMER)

    def test_signup_requires_an_account_type(self):
        response = self.client.post(
            reverse("account_signup"),
            {
                "email": "no-role@example.com",
                "password1": self.password,
                "password2": self.password,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "This field is required.")
        self.assertFalse(User.objects.filter(email="no-role@example.com").exists())


class LoginFlowTests(TestCase):
    password = "temporary-pass-1"

    def setUp(self):
        self.user = User.objects.create_user(
            "buyer", email="buyer@example.com", password=self.password
        )

    def test_login_by_email_redirects_to_listings(self):
        EmailAddress.objects.create(
            user=self.user,
            email=self.user.email,
            verified=True,
            primary=True,
        )

        response = self.client.post(
            reverse("account_login"),
            {"login": self.user.email, "password": self.password},
        )

        self.assertRedirects(
            response,
            settings.LOGIN_REDIRECT_URL,
            fetch_redirect_response=False,
        )
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.user.pk)

    def test_unverified_email_cannot_log_in(self):
        EmailAddress.objects.create(
            user=self.user,
            email=self.user.email,
            verified=False,
            primary=True,
        )

        response = self.client.post(
            reverse("account_login"),
            {"login": self.user.email, "password": self.password},
        )

        self.assertRedirects(
            response,
            reverse("account_email_verification_sent"),
            fetch_redirect_response=False,
        )
        self.assertNotIn("_auth_user_id", self.client.session)


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
)
class AvatarTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            "buyer", email="buyer@example.com", password="temporary-pass-1"
        )
        self.media_root = tempfile.mkdtemp()
        self.media_override = override_settings(MEDIA_ROOT=self.media_root)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.addCleanup(shutil.rmtree, self.media_root, ignore_errors=True)

    def test_avatar_url_is_empty_without_upload_or_google(self):
        self.assertEqual(self.user.profile.avatar_url, "")

    @override_settings(
        SOCIALACCOUNT_PROVIDERS={
            "google": {"APP": {"client_id": "test", "secret": "test"}}
        }
    )
    def test_avatar_url_falls_back_to_google(self):
        SocialAccount.objects.create(
            user=self.user,
            provider="google",
            uid="google-1",
            extra_data={"picture": "https://example.com/photo.jpg"},
        )

        self.assertEqual(
            self.user.profile.avatar_url, "https://example.com/photo.jpg"
        )

    @override_settings(
        SOCIALACCOUNT_PROVIDERS={
            "google": {"APP": {"client_id": "test", "secret": "test"}}
        }
    )
    def test_uploaded_avatar_wins_over_google(self):
        SocialAccount.objects.create(
            user=self.user,
            provider="google",
            uid="google-1",
            extra_data={"picture": "https://example.com/photo.jpg"},
        )
        self.user.profile.avatar.save("me.png", ContentFile(image_bytes()))

        self.assertEqual(
            self.user.profile.avatar_url, self.user.profile.avatar.url
        )

    def test_profile_view_requires_login(self):
        response = self.client.get(reverse("profile"))

        self.assertRedirects(
            response,
            f"{reverse('account_login')}?next={reverse('profile')}",
        )

    def test_profile_view_uploads_avatar(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("profile"),
            {
                "avatar": SimpleUploadedFile(
                    "me.png", image_bytes(), content_type="image/png"
                )
            },
        )

        self.assertRedirects(response, reverse("profile"))
        self.user.profile.refresh_from_db()
        self.assertTrue(self.user.profile.avatar)
        self.assertTrue(Path(self.user.profile.avatar.path).exists())

    def test_profile_view_rejects_non_image(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("profile"),
            {
                "avatar": SimpleUploadedFile(
                    "notes.txt", b"not an image", content_type="text/plain"
                )
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Upload a valid image")
        self.user.profile.refresh_from_db()
        self.assertFalse(self.user.profile.avatar)
