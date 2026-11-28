"""Development-only middleware.

Debug builds sign anonymous visitors in as a local developer account so the
protected pages (dashboard, create listing, profile, chat, analytics,
notifications) can be reviewed without registering. The guard is
``settings.DEBUG``: with ``DEBUG=False`` this middleware does nothing and
allauth's login requirement applies exactly as it does in deployment.
"""

import logging

from django.conf import settings
from django.contrib.auth import login
from django.db import DatabaseError, IntegrityError

logger = logging.getLogger(__name__)

# Stable identity so the account is created once and reused across restarts.
DEV_USER_EMAIL = "dev@example.com"
DEV_USER_USERNAME = "dev-user"


class DebugAutoLoginMiddleware:
    """Sign anonymous requests in as the local developer account in DEBUG."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if settings.DEBUG and request.user.is_anonymous:
            self._sign_in(request)
        return self.get_response(request)

    def _sign_in(self, request):
        try:
            user = developer_user()
        except DatabaseError:
            # Migrations not run, or the database is unreachable. Let the view
            # render the real error instead of failing here.
            logger.warning(
                "DEBUG auto-login skipped: the database is unavailable.",
                exc_info=True,
            )
            return

        login(request, user, backend=settings.AUTHENTICATION_BACKENDS[0])


def developer_user():
    """Return the shared development account, creating it on first use.

    The account is a farmer (so "Sell produce" and the dashboard are visible)
    and staff (so an admin link works), with an unusable password: nobody can
    sign in as it through the login form.
    """

    from .models import Profile, User

    user = User.objects.filter(email=DEV_USER_EMAIL).first()
    if user is not None:
        return user

    try:
        user = User.objects.create_user(
            username=DEV_USER_USERNAME,
            email=DEV_USER_EMAIL,
            password=None,
        )
    except IntegrityError:
        # Another worker created it between the lookup and the insert.
        return User.objects.get(email=DEV_USER_EMAIL)

    user.is_staff = True
    user.save(update_fields=["is_staff"])
    # The post_save signal creates the profile; make it a farmer.
    Profile.objects.filter(user=user).update(role=Profile.Role.FARMER)
    return user
