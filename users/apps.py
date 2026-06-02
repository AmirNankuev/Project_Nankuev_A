from django.apps import AppConfig
from django.db.models.signals import post_migrate


class UsersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "users"
    verbose_name = "Пользователи и роли"

    def ready(self):
        from .roles import setup_role_groups
        from . import signals  # noqa: F401

        post_migrate.connect(setup_role_groups, sender=self)
