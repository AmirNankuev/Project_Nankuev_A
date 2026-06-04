from django.core.management.base import BaseCommand

from main.services.reservations import release_expired_reservations


class Command(BaseCommand):
    help = "Освобождает истёкшие резервы товаров и отменяет неоплаченные заказы."

    def handle(self, *args, **options):
        released_count = release_expired_reservations()
        self.stdout.write(self.style.SUCCESS(f"Освобождено резервов: {released_count}"))
