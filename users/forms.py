import re

from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.core.exceptions import ValidationError

from .models import CustomUser


class RegisterForm(UserCreationForm):
    full_name = forms.CharField(label="ФИО", max_length=150)
    phone = forms.CharField(
        label="Телефон",
        max_length=16,
        widget=forms.TextInput(attrs={
            "class": "auth-input",
            "placeholder": "+7(999)123-45-67",
            "autocomplete": "tel",
        })
    )
    email = forms.EmailField(label="Email")

    class Meta:
        model = CustomUser
        fields = ("username", "full_name", "phone", "email", "password1", "password2")
        labels = {
            "username": "Логин"
        }

    def clean_username(self):
        username = self.cleaned_data.get("username")

        if not re.fullmatch(r"[A-Za-z0-9]+", username):
            raise ValidationError("Логин должен содержать только латинские буквы и цифры")

        if CustomUser.objects.filter(username=username).exists():
            raise ValidationError("Пользователь с таким логином уже существует")

        return username

    def clean_full_name(self):
        full_name = self.cleaned_data.get("full_name")

        if not re.fullmatch(r"[А-Яа-яЁё\s]+", full_name):
            raise ValidationError("ФИО должно содержать только кириллицу и пробелы")

        return full_name

    def clean_phone(self):
        phone = self.cleaned_data.get("phone")

        if not re.fullmatch(r"\+7\(\d{3}\)\d{3}-\d{2}-\d{2}", phone):
            raise ValidationError("Телефон должен быть в формате +7(XXX)XXX-XX-XX")

        if CustomUser.objects.filter(phone=phone).exists():
            raise ValidationError("Пользователь с таким телефоном уже существует")

        return phone

    def clean_email(self):
        email = self.cleaned_data.get("email")

        if CustomUser.objects.filter(email=email).exists():
            raise ValidationError("Пользователь с такой почтой уже существует")

        return email


class LoginForm(AuthenticationForm):
    username = forms.CharField(label="Логин", max_length=150)
    password = forms.CharField(
        label="Пароль",
        widget=forms.PasswordInput
    )