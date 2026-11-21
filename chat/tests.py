from django.test import TestCase
from django.urls import reverse


class ChatViewTests(TestCase):
    def test_chat_requires_login(self):
        response = self.client.get(reverse("chat"))

        self.assertRedirects(
            response,
            f"{reverse('account_login')}?next={reverse('chat')}",
        )
