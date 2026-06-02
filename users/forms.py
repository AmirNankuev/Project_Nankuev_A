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

    error_messages = {
        **AuthenticationForm.error_messages,
        "email_not_confirmed": "Аккаунт ещё не активирован. Подтвердите email по ссылке из письма.",
    }

    def clean(self):
        username = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")

        if username and password:
            user = CustomUser.objects.filter(username=username).first()
            if user and not user.is_active and not user.email_confirmed and user.check_password(password):
                raise ValidationError(
                    self.error_messages["email_not_confirmed"],
                    code="email_not_confirmed",
                )

        return super().clean()


class ProfileForm(forms.ModelForm):
    class Meta:
        model = CustomUser
        fields = ("full_name", "phone", "email")
        labels = {
            "full_name": "ФИО",
            "phone": "Телефон",
            "email": "Email",
        }
        widgets = {
            "full_name": forms.TextInput(attrs={
                "class": "profile-input",
                "placeholder": "Иванов Иван Иванович",
            }),
            "phone": forms.TextInput(attrs={
                "class": "profile-input",
                "placeholder": "+7(999)123-45-67",
                "autocomplete": "tel",
            }),
            "email": forms.EmailInput(attrs={
                "class": "profile-input",
                "placeholder": "mail@example.com",
                "autocomplete": "email",
            }),
        }

    def clean_full_name(self):
        full_name = self.cleaned_data.get("full_name", "").strip()

        if not re.fullmatch(r"[А-Яа-яЁё\s]+", full_name):
            raise ValidationError("ФИО должно содержать только кириллицу и пробелы")

        return full_name

    def clean_phone(self):
        phone = self.cleaned_data.get("phone", "").strip()

        if not re.fullmatch(r"\+7\(\d{3}\)\d{3}-\d{2}-\d{2}", phone):
            raise ValidationError("Телефон должен быть в формате +7(XXX)XXX-XX-XX")

        duplicate = CustomUser.objects.filter(phone=phone).exclude(pk=self.instance.pk).exists()
        if duplicate:
            raise ValidationError("Пользователь с таким телефоном уже существует")

        return phone

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip()

        duplicate = CustomUser.objects.filter(email=email).exclude(pk=self.instance.pk).exists()
        if duplicate:
            raise ValidationError("Пользователь с такой почтой уже существует")

        return email
