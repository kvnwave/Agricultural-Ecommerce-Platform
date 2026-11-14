from django.test import SimpleTestCase
from storages.backends.s3 import S3Storage

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

    def test_explicit_custom_domain_is_normalized(self):
        options = self.make_options(
            custom_domain="https://cdn.example.com/media/",
        )

        self.assertEqual(options["custom_domain"], "cdn.example.com/media")

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
