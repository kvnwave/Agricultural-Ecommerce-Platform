from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = 'accounts'

    def ready(self):
        # Importing signals here avoids loading models before the app registry
        # is ready, which would prevent the receiver from connecting.
        from . import signals  # noqa: F401
