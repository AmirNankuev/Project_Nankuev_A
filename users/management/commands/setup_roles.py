from django.core.management.base import BaseCommand

from users.models import CustomUser
from users.roles import sync_user_role, setup_role_groups


class Command(BaseCommand):
    help = "Создаёт группы ролей и синхронизирует роли существующих пользователей."

    def handle(self, *args, **options):
        setup_role_groups()

        synced = 0
        for user in CustomUser.objects.all():
            sync_user_role(user)
            synced += 1

        self.stdout.write(self.style.SUCCESS(f"Роли настроены. Пользователей синхронизировано: {synced}."))
