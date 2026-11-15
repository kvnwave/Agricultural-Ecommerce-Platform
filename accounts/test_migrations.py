import re

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class RenameEmailUsernamesMigrationTests(TransactionTestCase):
    migrate_from = [("accounts", "0003_username_policy")]
    migrate_to = [("accounts", "0004_rename_email_usernames")]

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(
            self.migrate_from
            + executor.loader.graph.leaf_nodes("socialaccount")
        ).apps
        User = old_apps.get_model("accounts", "User")
        SocialAccount = old_apps.get_model("socialaccount", "SocialAccount")

        self.email_user = User.objects.create(
            username="jane.doe",
            email="jane.doe@example.com",
        )
        self.collision_user = User.objects.create(
            username="farmer1",
            email="farmer@example.com",
        )
        self.near_miss_user = User.objects.create(
            username="farmer1a",
            email="farmer@example.net",
        )
        self.staff_user = User.objects.create(
            username="admin.person",
            email="admin@example.com",
            is_staff=True,
        )
        self.social_user = User.objects.create(
            username="jane",
            email="jane@example.com",
            first_name="Jane",
        )
        SocialAccount.objects.create(
            user=self.social_user,
            provider="google",
            uid="123",
        )
        self.social_suffix_user = User.objects.create(
            username="jane12",
            email="jane12@example.com",
            first_name="Jane",
        )
        SocialAccount.objects.create(
            user=self.social_suffix_user,
            provider="google",
            uid="456",
        )
        self.custom_user = User.objects.create(
            username="custom_handle",
            email="custom@example.com",
        )
        User.objects.filter(pk=self.email_user.pk).update(
            username_changed_at=timezone.now()
        )

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        self.apps = executor.loader.project_state(self.migrate_to).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        super().tearDown()

    def test_renames_only_email_derived_non_staff_handles(self):
        User = self.apps.get_model("accounts", "User")
        History = self.apps.get_model("accounts", "UsernameHistory")

        renamed = User.objects.get(pk=self.email_user.pk)
        collision = User.objects.get(pk=self.collision_user.pk)

        self.assertRegex(renamed.username, r"^user-[0-9a-f]{8}$")
        self.assertRegex(collision.username, r"^user-[0-9a-f]{8}$")
        self.assertIsNone(renamed.username_changed_at)
        self.assertIsNone(collision.username_changed_at)

        self.assertEqual(
            History.objects.get(user_id=self.email_user.pk).old_username,
            "jane.doe",
        )
        self.assertEqual(
            History.objects.get(user_id=self.collision_user.pk).old_username,
            "farmer1",
        )
        self.assertEqual(History.objects.count(), 2)
        for entry in History.objects.all():
            self.assertEqual(entry.reason, "migration")
            self.assertIsNone(entry.changed_by_id)

        self.assertEqual(
            User.objects.get(pk=self.staff_user.pk).username,
            "admin.person",
        )
        self.assertEqual(
            User.objects.get(pk=self.social_user.pk).username,
            "jane",
        )
        self.assertEqual(
            User.objects.get(pk=self.custom_user.pk).username,
            "custom_handle",
        )
        self.assertEqual(
            User.objects.get(pk=self.near_miss_user.pk).username,
            "farmer1a",
        )
        self.assertEqual(
            User.objects.get(pk=self.social_suffix_user.pk).username,
            "jane12",
        )

    def test_generated_handles_do_not_collide(self):
        User = self.apps.get_model("accounts", "User")

        renamed = User.objects.get(pk=self.email_user.pk)
        collision = User.objects.get(pk=self.collision_user.pk)

        self.assertNotEqual(renamed.username, collision.username)
        self.assertTrue(re.match(r"^user-[0-9a-f]{8}$", renamed.username))
