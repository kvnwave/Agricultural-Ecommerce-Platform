from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Profile, User


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Every user needs a profile; doing it here covers email signup, social
    signup, admin-created users, and tests without repeating the logic.
    """

    if created:
        Profile.objects.get_or_create(user=instance)


@receiver(post_delete, sender=Profile)
def delete_profile_avatar_file(sender, instance, **kwargs):
    """Remove the stored avatar after the profile row is gone.

    Deleting a user cascades to the profile, so this also covers account
    deletion. Running on commit means a rolled-back delete keeps the file.
    """

    name = instance.avatar.name
    if not name:
        return
    storage = instance.avatar.storage
    transaction.on_commit(lambda: storage.delete(name), robust=True)
