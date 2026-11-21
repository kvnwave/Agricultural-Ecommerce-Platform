from django.test import TestCase
from django.urls import reverse


class NotificationsViewTests(TestCase):
    def test_notifications_requires_login(self):
        response = self.client.get(reverse("notifications"))

        self.assertRedirects(
            response,
            f"{reverse('account_login')}?next={reverse('notifications')}",
        )
