# Подтверждение email и восстановление пароля

Добавлена активация аккаунта через ссылку на почту и восстановление пароля через email.

## Новые страницы

- `/users/register/` — регистрация с отправкой письма подтверждения.
- `/users/confirm/sent/` — сообщение о том, что письмо отправлено.
- `/users/confirm/<uidb64>/<token>/` — подтверждение email и активация аккаунта.
- `/users/password/reset/` — форма «Забыли пароль?».
- `/users/password/reset/done/` — письмо для восстановления отправлено.
- `/users/password/reset/<uidb64>/<token>/` — ввод нового пароля.
- `/users/password/reset/complete/` — пароль успешно изменён.

## Как работает подтверждение email

1. Пользователь проходит регистрацию.
2. Аккаунт создаётся с `is_active=False` и `email_confirmed=False`.
3. На почту отправляется ссылка подтверждения.
4. После перехода по ссылке система ставит `is_active=True`, `email_confirmed=True` и автоматически авторизует пользователя.

Пользователь не сможет войти до подтверждения почты.

## Как работает восстановление пароля

1. На странице входа пользователь нажимает «Забыли пароль?».
2. Вводит email.
3. Получает письмо со ссылкой.
4. Переходит по ссылке и задаёт новый пароль.
5. После изменения пароля отправляется отдельное уведомление о смене пароля.

## Настройка SMTP

Используются существующие настройки из `settings.py`:

```python
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.yandex.ru")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "465"))
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", False)
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", True)
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER or "noreply@example.com")
SITE_URL = os.getenv("SITE_URL", "http://127.0.0.1:8000")
```

Для Яндекса нужен пароль приложения, а не обычный пароль от почты.

## После замены файлов

```bash
python manage.py migrate
```

Затем проверить:

```bash
python manage.py check
```
