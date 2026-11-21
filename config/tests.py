from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from storages.backends.s3 import S3Storage

from config import settings as base_settings
from config.database import (
    database_config,
    direct_database_config,
    encode_url_password,
    uses_transaction_pooler,
)
from config.storage import supabase_storage_options

POOLER_URL = (
    "postgresql://postgres.project:secret@"
    "aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres"
)
DIRECT_URL = "postgresql://postgres:secret@db.project.supabase.co:5432/postgres"


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


class DatabaseConfigTests(SimpleTestCase):
    def test_sqlite_url_is_not_given_tls_options(self):
        config = database_config("sqlite:///db.sqlite3", ssl_require=True)

        self.assertEqual(config["ENGINE"], "django.db.backends.sqlite3")
        self.assertFalse(config.get("OPTIONS"))

    def test_postgres_url_requires_tls_outside_debug(self):
        config = database_config(POOLER_URL, ssl_require=True)

        self.assertEqual(config["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(config["OPTIONS"]["sslmode"], "require")

    def test_postgres_url_can_skip_tls(self):
        config = database_config(POOLER_URL, ssl_require=False)

        self.assertNotEqual(config.get("OPTIONS", {}).get("sslmode"), "require")

    def test_server_side_cursors_are_disabled(self):
        config = database_config(POOLER_URL, ssl_require=True)

        self.assertTrue(config["DISABLE_SERVER_SIDE_CURSORS"])

    def test_psycopg3_prepared_statements_are_disabled(self):
        config = database_config(POOLER_URL, ssl_require=True)

        self.assertIsNone(config["OPTIONS"]["prepare_threshold"])

    def test_missing_url_is_rejected(self):
        with self.assertRaisesRegex(ImproperlyConfigured, "DATABASE_URL"):
            database_config("", ssl_require=True)

    def test_unsupported_scheme_is_rejected(self):
        with self.assertRaisesRegex(ImproperlyConfigured, "mysql"):
            database_config("mysql://user:secret@localhost/db", ssl_require=True)

    def test_transaction_pooler_is_detected_by_port(self):
        self.assertTrue(
            uses_transaction_pooler(
                "postgresql://postgres:secret@db.example.com:6543/postgres"
            )
        )

    def test_transaction_pooler_is_detected_by_host(self):
        self.assertTrue(uses_transaction_pooler(POOLER_URL))

    def test_pooler_detection_works_with_reserved_password_characters(self):
        # Detection runs before parsing succeeds for bracketed passwords.
        self.assertTrue(
            uses_transaction_pooler(
                "postgresql://postgres.emlaiex:pa[ss]@"
                "aws-0-ap-southeast-1.pooler.supabase.com:6543/postgres"
            )
        )

    def test_direct_connection_is_not_a_pooler(self):
        self.assertFalse(uses_transaction_pooler(DIRECT_URL))
        self.assertFalse(uses_transaction_pooler("sqlite:///db.sqlite3"))
        self.assertFalse(uses_transaction_pooler(""))

    def test_session_pooler_is_not_a_transaction_pooler(self):
        # The session pooler shares the transaction pooler's host; only the
        # port differs, and migrations work on 5432.
        self.assertFalse(
            uses_transaction_pooler(
                "postgresql://postgres.project:secret@"
                "aws-0-ap-southeast-1.pooler.supabase.com:5432/postgres"
            )
        )


class DirectDatabaseConfigTests(SimpleTestCase):
    def test_direct_url_takes_precedence(self):
        config = direct_database_config(
            POOLER_URL,
            DIRECT_URL,
            ssl_require=True,
        )

        self.assertEqual(config["HOST"], "db.project.supabase.co")
        self.assertEqual(str(config["PORT"]), "5432")
        self.assertEqual(config["OPTIONS"]["sslmode"], "require")

    def test_missing_direct_url_warns_when_falling_back_to_pooler(self):
        with self.assertLogs("config.database", level="WARNING") as logs:
            config = direct_database_config(POOLER_URL, "", ssl_require=True)

        self.assertIn("DIRECT_URL", logs.output[0])
        self.assertEqual(
            config["HOST"],
            "aws-0-ap-southeast-1.pooler.supabase.com",
        )

    def test_pooler_direct_url_is_reported(self):
        with self.assertLogs("config.database", level="WARNING") as logs:
            config = direct_database_config(
                DIRECT_URL,
                POOLER_URL,
                ssl_require=True,
            )

        self.assertIn(
            "DIRECT_URL points at the Supabase transaction pooler",
            logs.output[0],
        )
        self.assertEqual(str(config["PORT"]), "6543")

    def test_sqlite_fallback_does_not_warn(self):
        with self.assertNoLogs("config.database", level="WARNING"):
            config = direct_database_config(
                "sqlite:///db.sqlite3",
                "",
                ssl_require=True,
            )

        self.assertEqual(config["ENGINE"], "django.db.backends.sqlite3")

    def test_runtime_settings_build_from_the_configured_url(self):
        # The test runner rewrites the alias's NAME to its own database, so
        # only the engine and cursor settings are comparable here.
        expected = database_config(
            base_settings.DATABASE_URL,
            ssl_require=base_settings.DB_SSL_REQUIRE,
        )
        runtime = base_settings.DATABASES["default"]

        self.assertEqual(runtime["ENGINE"], expected["ENGINE"])
        self.assertTrue(runtime["DISABLE_SERVER_SIDE_CURSORS"])


class DatabaseUrlPasswordTests(SimpleTestCase):
    def test_reserved_password_characters_are_encoded(self):
        passwords = (
            'pa ss',
            'pa"ss',
            "pa#ss",
            "pa/ss",
            "pa:ss",
            "pa?ss",
            "pa@ss",
            "pa[ss]",
            "pa&ss",
        )
        for password in passwords:
            with self.subTest(password=password):
                url = (
                    "postgresql://postgres."
                    f"project:{password}@db.project.supabase.co:5432/postgres"
                )

                config = database_config(url, ssl_require=True)

                self.assertEqual(config["HOST"], "db.project.supabase.co")
                self.assertEqual(config["PORT"], 5432)
                self.assertEqual(config["NAME"], "postgres")
                self.assertEqual(config["PASSWORD"], password)

    def test_bracketed_password_no_longer_breaks_url_parsing(self):
        # CPython reads a raw '[' in the userinfo as an IPv6 literal.
        url = "postgresql://postgres:pa[ss]word@db.project.supabase.co:5432/postgres"

        self.assertEqual(
            encode_url_password(url),
            "postgresql://postgres:pa%5Bss%5Dword@db.project.supabase.co:5432/postgres",
        )

    def test_literal_percent_in_password_survives_parsing(self):
        # A raw '%' would otherwise decode into a different password.
        config = database_config(
            "postgresql://postgres:pa%ss@db.project.supabase.co:5432/postgres",
            ssl_require=True,
        )

        self.assertEqual(config["PASSWORD"], "pa%ss")
        self.assertEqual(config["HOST"], "db.project.supabase.co")

    def test_percent_with_brackets_is_encoded_once(self):
        config = database_config(
            "postgresql://postgres:pa[%]ss@db.project.supabase.co:5432/postgres",
            ssl_require=True,
        )

        self.assertEqual(config["PASSWORD"], "pa[%]ss")

    def test_password_encoding_is_idempotent(self):
        url = "postgresql://postgres:pa[ss]%40word@db.project.supabase.co:5432/postgres"

        self.assertEqual(
            encode_url_password(encode_url_password(url)),
            encode_url_password(url),
        )

    def test_already_encoded_password_is_not_double_encoded(self):
        config = database_config(
            "postgresql://postgres:pa%5Bss%5D%40word@db.project.supabase.co:5432/postgres",
            ssl_require=True,
        )

        self.assertEqual(config["PASSWORD"], "pa[ss]@word")

    def test_query_parameters_survive_password_encoding(self):
        config = database_config(
            "postgresql://postgres:pa[ss]@db.project.supabase.co:5432/postgres"
            "?sslmode=require&connect_timeout=5",
            ssl_require=True,
        )

        self.assertEqual(config["HOST"], "db.project.supabase.co")
        self.assertEqual(config["PASSWORD"], "pa[ss]")

    def test_url_without_password_is_unchanged(self):
        url = "postgresql://postgres@db.project.supabase.co:5432/postgres"

        self.assertEqual(encode_url_password(url), url)

    def test_unparseable_url_reports_how_to_fix_it(self):
        with self.assertRaisesRegex(ImproperlyConfigured, "Percent-encode"):
            database_config(
                "postgresql://postgres:secret@ho[st:5432/postgres",
                ssl_require=True,
            )


class TestDatabaseIsolationTests(SimpleTestCase):
    def test_test_suite_never_uses_the_configured_database(self):
        # A Supabase URL in .env must not turn the test run into a client of
        # the live project.
        self.assertEqual(
            settings.DATABASES["default"]["ENGINE"],
            "django.db.backends.sqlite3",
        )
        self.assertEqual(base_settings.DATABASE_URL, "sqlite:///db.sqlite3")


class ContentSecurityPolicyTests(TestCase):
    def test_pages_send_report_only_policy(self):
        # The middleware applies to every response. Use a route whose template
        # exists during the frontend handoff so this only tests the header.
        response = self.client.get(reverse("account_login"))

        policy = response.headers["Content-Security-Policy-Report-Only"]

        self.assertIn("default-src 'self'", policy)
        self.assertIn(
            "img-src 'self' https://*.googleusercontent.com",
            policy,
        )
        self.assertIn("object-src 'none'", policy)
        self.assertIn("base-uri 'self'", policy)
        self.assertNotIn("Content-Security-Policy", response.headers)


class ProductionSettingsTests(SimpleTestCase):
    def test_dev_secret_key_is_not_used(self):
        self.assertNotEqual(
            base_settings.SECRET_KEY,
            base_settings.INSECURE_DEV_SECRET_KEY,
        )

    def test_https_and_secure_cookies_are_enabled(self):
        self.assertTrue(base_settings.SECURE_SSL_REDIRECT)
        self.assertTrue(base_settings.SESSION_COOKIE_SECURE)
        self.assertTrue(base_settings.CSRF_COOKIE_SECURE)
        self.assertGreater(base_settings.SECURE_HSTS_SECONDS, 0)

    def test_email_uses_smtp_outside_debug(self):
        self.assertEqual(
            base_settings.MAILERS["default"]["BACKEND"],
            "django.core.mail.backends.smtp.EmailBackend",
        )
        self.assertTrue(base_settings.DEFAULT_FROM_EMAIL)


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
