from django.test import TestCase
from django.urls import reverse


class AnalyticsViewTests(TestCase):
    def test_analytics_requires_login(self):
        response = self.client.get(reverse("analytics"))

        self.assertRedirects(
            response,
            f"{reverse('account_login')}?next={reverse('analytics')}",
        )
