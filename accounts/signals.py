from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Profile, User


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Every user needs a profile; doing it here covers email signup, social
    signup, admin-created users, and tests without repeating the logic.
    """

    if created:
        Profile.objects.get_or_create(user=instance)
