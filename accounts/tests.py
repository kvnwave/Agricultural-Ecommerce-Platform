import io
import shutil
import tempfile
from pathlib import Path
from unittest import mock

from allauth.account.models import EmailAddress
from allauth.core import context as allauth_context
from allauth.socialaccount.forms import SignupForm as AllauthSocialSignupForm
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from PIL import Image

from . import usernames
from .adapters import AccountAdapter
from .forms import SOCIAL_SIGNUP_ROLE_SESSION_KEY, SocialSignupForm
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


class UsernamePolicyTests(TestCase):
    def test_normalizes_case_and_whitespace(self):
        self.assertEqual(
            usernames.normalize_username("  Farmer_Jane "),
            "farmer_jane",
        )

    def test_accepts_valid_handles(self):
        for value in ("farmer_jane", "a1b", "user-1234abcd", "x" * 30):
            with self.subTest(value=value):
                self.assertEqual(usernames.validate_username(value), value)

    def test_rejects_lengths_outside_bounds(self):
        for value in ("ab", "x" * 31):
            with self.subTest(value=value):
                with self.assertRaisesMessage(
                    ValidationError, "between 3 and 30"
                ):
                    usernames.validate_username(value)

    def test_rejects_invalid_characters_and_edges(self):
        values = (
            "-farmer",
            "farmer-",
            "farmer jane",
            "farmer@example.com",
            "fármer",
            "farmer.jane",
            "farmer+name",
        )

        for value in values:
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    usernames.validate_username(value)

    def test_rejects_reserved_names_case_insensitively(self):
        for value in ("Admin", "SUPPORT", "marketplace"):
            with self.subTest(value=value):
                with self.assertRaisesMessage(ValidationError, "reserved"):
                    usernames.validate_username(value)


class GeneratedUsernameTests(TestCase):
    def test_generated_handle_follows_policy_and_skips_collisions(self):
        User.objects.create_user(
            "user-deadbeef",
            email="taken@example.com",
            password="temporary-pass-1",
        )

        with mock.patch(
            "accounts.usernames.secrets.token_hex",
            side_effect=["deadbeef", "cafebabe"],
        ):
            handle = usernames.generate_username()

        self.assertEqual(handle, "user-cafebabe")
        self.assertEqual(usernames.validate_username(handle), handle)


class AccountAdapterTests(TestCase):
    def test_clean_username_normalizes_and_accepts(self):
        self.assertEqual(
            AccountAdapter().clean_username("  Farmer_Jane "),
            "farmer_jane",
        )

    def test_clean_username_rejects_taken_handle_ignoring_case(self):
        User.objects.create_user(
            "farmer_jane",
            email="jane@example.com",
            password="temporary-pass-1",
        )

        with self.assertRaisesMessage(ValidationError, "already taken"):
            AccountAdapter().clean_username("Farmer_Jane")

    def test_clean_username_shallow_skips_uniqueness(self):
        User.objects.create_user(
            "farmer_jane",
            email="jane@example.com",
            password="temporary-pass-1",
        )

        self.assertEqual(
            AccountAdapter().clean_username("Farmer_Jane", shallow=True),
            "farmer_jane",
        )

    def test_generate_unique_username_uses_neutral_handle(self):
        with mock.patch(
            "accounts.adapters.usernames.generate_username",
            return_value="user-1a2b3c4d",
        ) as generate:
            handle = AccountAdapter().generate_unique_username(
                ["Jane", "jane@example.com"]
            )

        self.assertEqual(handle, "user-1a2b3c4d")
        generate.assert_called_once_with()


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
        self.assertRegex(user.username, r"^user-[0-9a-f]{8}$")
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


class SocialSignupRoleTests(TestCase):
    def sociallogin(self):
        return SocialLogin(user=User(email="social@example.com"))

    def test_start_stores_role_and_redirects_to_provider(self):
        response = self.client.get(
            reverse(
                "social_signup_start",
                kwargs={"provider": "google", "role": Profile.Role.FARMER},
            )
        )

        self.assertRedirects(
            response,
            reverse("google_login"),
            fetch_redirect_response=False,
        )
        self.assertEqual(
            self.client.session[SOCIAL_SIGNUP_ROLE_SESSION_KEY],
            Profile.Role.FARMER,
        )

    def test_start_rejects_unknown_role_or_provider(self):
        cases = (
            {"provider": "google", "role": "admin"},
            {"provider": "not-a-provider", "role": Profile.Role.FARMER},
        )

        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                response = self.client.get(
                    reverse("social_signup_start", kwargs=kwargs)
                )
                self.assertEqual(response.status_code, 404)

    def test_social_signup_view_uses_custom_form(self):
        from allauth.socialaccount.views import SignupView

        self.assertIs(SignupView().get_form_class(), SocialSignupForm)

    def test_social_form_has_no_default_role(self):
        form = SocialSignupForm(sociallogin=self.sociallogin())

        self.assertTrue(form.fields["role"].required)
        self.assertIsNone(form.fields["role"].initial)

    def test_social_form_prefills_role_from_session(self):
        request = RequestFactory().get("/")
        request.session = {
            SOCIAL_SIGNUP_ROLE_SESSION_KEY: Profile.Role.FARMER,
        }

        with allauth_context.request_context(request):
            form = SocialSignupForm(sociallogin=self.sociallogin())

        self.assertEqual(form.fields["role"].initial, Profile.Role.FARMER)

    def test_social_form_saves_role_and_clears_session(self):
        user = User.objects.create_user(
            "social",
            email="social@example.com",
            password="temporary-pass-1",
        )
        request = RequestFactory().get("/")
        request.session = {
            SOCIAL_SIGNUP_ROLE_SESSION_KEY: Profile.Role.FARMER,
        }
        form = SocialSignupForm(sociallogin=self.sociallogin())
        form.cleaned_data = {"role": Profile.Role.FARMER}

        with mock.patch.object(
            AllauthSocialSignupForm,
            "save",
            return_value=user,
        ) as base_save:
            result = form.save(request)

        self.assertIs(result, user)
        self.assertEqual(user.profile.role, Profile.Role.FARMER)
        self.assertNotIn(SOCIAL_SIGNUP_ROLE_SESSION_KEY, request.session)
        base_save.assert_called_once_with(request)


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
