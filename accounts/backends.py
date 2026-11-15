from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class ProfileModelBackend(ModelBackend):
    """Load the profile with the session user.

    Every page reads ``user.profile`` for the role and notification settings.
    Joining it here keeps session restoration to one query instead of two,
    without changing how password authentication or permissions work.
    """

    def get_user(self, user_id):
        User = get_user_model()
        try:
            user = User._default_manager.select_related("profile").get(pk=user_id)
        except User.DoesNotExist:
            return None
        return user if self.user_can_authenticate(user) else None
