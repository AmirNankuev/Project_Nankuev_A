from django.contrib.auth.models import AbstractUser
from django.db import models

from .roles import UserRole


class CustomUser(AbstractUser):
    REQUIRED_FIELDS = ["full_name", "phone", "email"]

    ROLE_CHOICES = [
        (UserRole.CUSTOMER, "Покупатель"),
        (UserRole.MANAGER, "Менеджер"),
        (UserRole.ADMINISTRATOR, "Администратор"),
    ]

    full_name = models.CharField(
        max_length=150,
        verbose_name="ФИО"
    )

    phone = models.CharField(
        max_length=16,
        unique=True,
        verbose_name="Телефон"
    )

    email = models.EmailField(
        unique=True,
        verbose_name="Email"
    )

    email_confirmed = models.BooleanField(
        "Email подтверждён",
        default=True,
        help_text="Для новых покупателей становится True после перехода по ссылке из письма.",
    )

    role = models.CharField(
        "Роль в системе",
        max_length=20,
        choices=ROLE_CHOICES,
        default=UserRole.CUSTOMER,
        db_index=True,
        help_text="Определяет доступ пользователя: покупатель, менеджер или администратор.",
    )

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"

    def save(self, *args, **kwargs):
        # createsuperuser создаёт пользователя с флагом superuser, но без выбора роли.
        # В этом случае автоматически переводим его в роль администратора.
        if self.is_superuser and self.role == UserRole.CUSTOMER:
            self.role = UserRole.ADMINISTRATOR
        super().save(*args, **kwargs)

    @property
    def is_customer_role(self):
        return self.role == UserRole.CUSTOMER

    @property
    def is_manager_role(self):
        return self.role == UserRole.MANAGER

    @property
    def is_administrator_role(self):
        return self.role == UserRole.ADMINISTRATOR

    @property
    def can_manage_shop(self):
        return self.role in {UserRole.MANAGER, UserRole.ADMINISTRATOR}

    @property
    def can_manage_users(self):
        return self.role == UserRole.ADMINISTRATOR

    @property
    def role_label(self):
        return self.get_role_display()

    def __str__(self):
        return self.username
