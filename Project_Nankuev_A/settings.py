"""
Django settings for Project_Nankuev_A project.

Настройки подготовлены для учебной разработки и безопасного развёртывания:
секреты и параметры окружения читаются из переменных окружения или файла .env.
Файл .env нельзя публиковать в Git.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured


BASE_DIR = Path(__file__).resolve().parent.parent


def load_dotenv(path: Path) -> None:
    """Простая загрузка .env без дополнительной зависимости python-dotenv."""
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if key and key not in os.environ:
            os.environ[key] = value


load_dotenv(BASE_DIR / ".env")


def env(name: str, default: str | None = None, *, required: bool = False) -> str:
    value = os.getenv(name, default)
    if required and (value is None or value == ""):
        raise ImproperlyConfigured(f"Не задана обязательная переменная окружения {name}")
    return value or ""


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "да"}


def env_int(name: str, default: int = 0) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ImproperlyConfigured(f"Переменная {name} должна быть числом") from exc


def env_list(name: str, default: str = "") -> list[str]:
    value = os.getenv(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


# -----------------------------------------------------------------------------
# Core security
# -----------------------------------------------------------------------------

DEBUG = env_bool("DEBUG", True)

SECRET_KEY = env("SECRET_KEY")
if not SECRET_KEY:
    if DEBUG:
        # Только для локальной разработки. Для защиты проекта задайте SECRET_KEY в .env.
        SECRET_KEY = "django-insecure-local-dev-key-change-me"
    else:
        raise ImproperlyConfigured("Для DEBUG=False обязательно задайте SECRET_KEY в .env")

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "127.0.0.1,localhost" if DEBUG else "")
if not DEBUG and not ALLOWED_HOSTS:
    raise ImproperlyConfigured("Для DEBUG=False обязательно задайте ALLOWED_HOSTS в .env")

CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", "")

# URL админ-панели можно изменить в .env, например ADMIN_URL=secure-admin-2026/
ADMIN_URL = env("ADMIN_URL", "admin/").strip("/") + "/"


# -----------------------------------------------------------------------------
# Application definition
# -----------------------------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "image_uploader_widget",
    "main",
    "catalog",
    "users.apps.UsersConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "Project_Nankuev_A.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "catalog.context_processors.header_navigation",
                "catalog.context_processors.cart_counter",
            ],
        },
    },
]

WSGI_APPLICATION = "Project_Nankuev_A.wsgi.application"


# -----------------------------------------------------------------------------
# Database
# -----------------------------------------------------------------------------

DATABASES = {
    "default": {
        "ENGINE": env("DB_ENGINE", "django.db.backends.postgresql"),
        "NAME": env("DB_NAME", "project_nankuev_new"),
        "USER": env("DB_USER", "postgres"),
        "PASSWORD": env("DB_PASSWORD", "admin" if DEBUG else "", required=not DEBUG),
        "HOST": env("DB_HOST", "localhost"),
        "PORT": env("DB_PORT", "5432"),
        "CONN_MAX_AGE": env_int("DB_CONN_MAX_AGE", 60 if not DEBUG else 0),
    }
}


# -----------------------------------------------------------------------------
# Authentication and password policy
# -----------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": env_int("PASSWORD_MIN_LENGTH", 8)},
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

AUTH_USER_MODEL = "users.CustomUser"
LOGIN_URL = "users:login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "home"


# -----------------------------------------------------------------------------
# Internationalization
# -----------------------------------------------------------------------------

LANGUAGE_CODE = "ru"
TIME_ZONE = env("TIME_ZONE", "UTC")
USE_I18N = True
USE_TZ = True


# -----------------------------------------------------------------------------
# Static and media files
# -----------------------------------------------------------------------------

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Ограничение размера загружаемых файлов и количества полей формы.
DATA_UPLOAD_MAX_MEMORY_SIZE = env_int("DATA_UPLOAD_MAX_MEMORY_SIZE", 2_621_440)
FILE_UPLOAD_MAX_MEMORY_SIZE = env_int("FILE_UPLOAD_MAX_MEMORY_SIZE", 2_621_440)
DATA_UPLOAD_MAX_NUMBER_FIELDS = env_int("DATA_UPLOAD_MAX_NUMBER_FIELDS", 1000)


# -----------------------------------------------------------------------------
# Browser/session security
# -----------------------------------------------------------------------------

SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = env_bool("CSRF_COOKIE_HTTPONLY", True)
SESSION_COOKIE_SAMESITE = env("SESSION_COOKIE_SAMESITE", "Lax")
CSRF_COOKIE_SAMESITE = env("CSRF_COOKIE_SAMESITE", "Lax")
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", not DEBUG)
CSRF_COOKIE_SECURE = env_bool("CSRF_COOKIE_SECURE", not DEBUG)

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = env("X_FRAME_OPTIONS", "DENY")
SECURE_REFERRER_POLICY = env("SECURE_REFERRER_POLICY", "strict-origin-when-cross-origin")
SECURE_CROSS_ORIGIN_OPENER_POLICY = env("SECURE_CROSS_ORIGIN_OPENER_POLICY", "same-origin")

# Включайте SECURE_SSL_REDIRECT только на сервере с настроенным HTTPS.
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", False)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https") if env_bool("USE_X_FORWARDED_PROTO", False) else None
SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 0 if DEBUG else 31_536_000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", not DEBUG)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", not DEBUG)


# -----------------------------------------------------------------------------
# CDEK integration settings
# -----------------------------------------------------------------------------
# Для реального API задайте CDEK_DEMO_MODE=false и укажите CDEK_CLIENT_ID / CDEK_CLIENT_SECRET.

CDEK_DEMO_MODE = env_bool("CDEK_DEMO_MODE", True)
CDEK_BASE_URL = env("CDEK_BASE_URL", "https://api.edu.cdek.ru/v2")
CDEK_CLIENT_ID = env("CDEK_CLIENT_ID", "")
CDEK_CLIENT_SECRET = env("CDEK_CLIENT_SECRET", "")
CDEK_FROM_CITY_CODE = env_int("CDEK_FROM_CITY_CODE", 44)
CDEK_DEFAULT_TARIFF_CODE = env_int("CDEK_DEFAULT_TARIFF_CODE", 137)
CDEK_DEFAULT_WEIGHT_GRAMS = env_int("CDEK_DEFAULT_WEIGHT_GRAMS", 300)
CDEK_DEFAULT_PACKAGE_LENGTH_CM = env_int("CDEK_DEFAULT_PACKAGE_LENGTH_CM", 30)
CDEK_DEFAULT_PACKAGE_WIDTH_CM = env_int("CDEK_DEFAULT_PACKAGE_WIDTH_CM", 20)
CDEK_DEFAULT_PACKAGE_HEIGHT_CM = env_int("CDEK_DEFAULT_PACKAGE_HEIGHT_CM", 10)
CDEK_REQUEST_TIMEOUT = env_int("CDEK_REQUEST_TIMEOUT", 20)


# -----------------------------------------------------------------------------
# YooKassa integration settings
# -----------------------------------------------------------------------------
# Для тестовой ЮKassa задайте YOOKASSA_DEMO_MODE=false и укажите тестовые Shop ID / Secret Key.

YOOKASSA_DEMO_MODE = env_bool("YOOKASSA_DEMO_MODE", True)
YOOKASSA_API_URL = env("YOOKASSA_API_URL", "https://api.yookassa.ru/v3")
YOOKASSA_SHOP_ID = env("YOOKASSA_SHOP_ID", "")
YOOKASSA_SECRET_KEY = env("YOOKASSA_SECRET_KEY", "")
YOOKASSA_RETURN_BASE_URL = env("YOOKASSA_RETURN_BASE_URL", "http://127.0.0.1:8000")
YOOKASSA_CURRENCY = env("YOOKASSA_CURRENCY", "RUB")
YOOKASSA_CAPTURE = env_bool("YOOKASSA_CAPTURE", True)
YOOKASSA_REQUEST_TIMEOUT = env_int("YOOKASSA_REQUEST_TIMEOUT", 20)


# -----------------------------------------------------------------------------
# Email notifications
# -----------------------------------------------------------------------------
# Для реальной отправки задайте EMAIL_HOST_USER и EMAIL_HOST_PASSWORD паролем приложения.

EMAIL_HOST_USER = env("EMAIL_HOST_USER", "amirnankuev@yandex.ru")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "ocvtWsE08c8d")
EMAIL_HOST = env("EMAIL_HOST", "smtp.yandex.ru")
EMAIL_PORT = env_int("EMAIL_PORT", 465)
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", False)
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", True)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER or "no-reply@example.local")
SERVER_EMAIL = DEFAULT_FROM_EMAIL
SITE_URL = env("SITE_URL", "http://127.0.0.1:8000")
EMAIL_NOTIFICATIONS_ENABLED = env_bool("EMAIL_NOTIFICATIONS_ENABLED", True)

if EMAIL_HOST_USER and EMAIL_HOST_PASSWORD:
    EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
else:
    EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")


# -----------------------------------------------------------------------------
# Stock reservation
# -----------------------------------------------------------------------------
# Время, на которое товар удерживается за покупателем во время онлайн-оплаты.

RESERVATION_HOLD_MINUTES = env_int("RESERVATION_HOLD_MINUTES", 30)
