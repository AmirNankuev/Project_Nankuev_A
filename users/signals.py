from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import CustomUser
from .roles import sync_user_role


@receiver(post_save, sender=CustomUser)
def sync_custom_user_role(sender, instance, **kwargs):
    sync_user_role(instance)
