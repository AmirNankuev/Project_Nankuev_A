from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser):
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

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"

    def __str__(self):
        return self.username