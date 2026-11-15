from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from storages.backends.s3 import S3Storage

from config import settings as base_settings
from config.storage import supabase_storage_options


class SupabaseStorageOptionsTests(SimpleTestCase):
    def make_options(self, **overrides):
        values = {
            "endpoint": "https://demo.supabase.co/storage/v1/s3",
            "bucket": "listings",
            "access_key": "key",
            "secret_key": "secret",
            "region": "ap-southeast-1",
        }
        values.update(overrides)
        return supabase_storage_options(**values)

    def test_public_bucket_uses_supabase_object_url(self):
        options = self.make_options()

        self.assertEqual(
            options["custom_domain"],
            "demo.supabase.co/storage/v1/object/public/listings",
        )
        self.assertFalse(options["querystring_auth"])
        self.assertEqual(options["addressing_style"], "path")
        self.assertEqual(options["signature_version"], "s3v4")
        self.assertFalse(options["file_overwrite"])
        self.assertEqual(options["url_protocol"], "https:")

    def test_explicit_custom_domain_is_normalized(self):
        options = self.make_options(
            custom_domain="https://cdn.example.com/media/",
        )

        self.assertEqual(options["custom_domain"], "cdn.example.com/media")

    def test_explicit_http_custom_domain_keeps_protocol(self):
        options = self.make_options(
            custom_domain="http://cdn.example.com/media/",
        )
        storage = S3Storage(**options)

        self.assertEqual(options["url_protocol"], "http:")
        self.assertTrue(
            storage.url("photo.png").startswith(
                "http://cdn.example.com/media/photo.png"
            )
        )

    def test_local_http_endpoint_returns_http_public_urls(self):
        options = self.make_options(
            endpoint="http://127.0.0.1:54321/storage/v1/s3",
        )
        storage = S3Storage(**options)

        self.assertEqual(options["url_protocol"], "http:")
        self.assertEqual(
            storage.url("listings/photo.png"),
            "http://127.0.0.1:54321/storage/v1/object/public/"
            "listings/listings/photo.png",
        )

    def test_storage_returns_public_object_url(self):
        storage = S3Storage(**self.make_options())

        self.assertEqual(
            storage.url("listings/photo.png"),
            "https://demo.supabase.co/storage/v1/object/public/listings/listings/photo.png",
        )

    def test_private_bucket_keeps_signed_s3_urls(self):
        options = self.make_options(
            querystring_auth=True,
            custom_domain="cdn.example.com",
        )

        self.assertTrue(options["querystring_auth"])
        self.assertNotIn("custom_domain", options)

    def test_invalid_endpoint_is_rejected(self):
        with self.assertRaises(ValueError):
            self.make_options(endpoint="not-a-url")


class ContentSecurityPolicyTests(TestCase):
    def test_marketplace_sends_report_only_policy(self):
        response = self.client.get(reverse("listings"))

        policy = response.headers["Content-Security-Policy-Report-Only"]

        self.assertIn("default-src 'self'", policy)
        self.assertIn(
            "img-src 'self' https://*.googleusercontent.com",
            policy,
        )
        self.assertIn("object-src 'none'", policy)
        self.assertIn("base-uri 'self'", policy)
        self.assertNotIn("Content-Security-Policy", response.headers)


class AdminPathTests(SimpleTestCase):
    def test_admin_is_not_at_the_default_path(self):
        self.assertNotEqual(settings.DJANGO_ADMIN_PATH, "admin/")
        self.assertEqual(
            reverse("admin:index"),
            f"/{settings.DJANGO_ADMIN_PATH}",
        )


class StaticFilesTests(SimpleTestCase):
    def test_whitenoise_follows_security_middleware(self):
        middleware = settings.MIDDLEWARE

        self.assertEqual(
            middleware.index("whitenoise.middleware.WhiteNoiseMiddleware"),
            middleware.index("django.middleware.security.SecurityMiddleware") + 1,
        )

    def test_static_files_use_compressed_manifest_storage(self):
        self.assertEqual(
            base_settings.STORAGES["staticfiles"]["BACKEND"],
            "whitenoise.storage.CompressedManifestStaticFilesStorage",
        )

    def test_htmx_is_vendored(self):
        self.assertIsNotNone(finders.find("js/htmx.min.js"))

    def test_timezone_is_manila(self):
        self.assertEqual(settings.TIME_ZONE, "Asia/Manila")
        self.assertTrue(settings.USE_TZ)
