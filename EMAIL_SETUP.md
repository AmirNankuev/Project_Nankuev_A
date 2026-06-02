# Email-уведомления

В проект добавлена отправка писем пользователю в следующих ситуациях:

- после оформления заказа;
- после успешной оплаты/изменения статуса заказа;
- после создания заявки на возврат;
- после одобрения, отклонения или завершения возврата менеджером;
- после успешной смены пароля пользователем.

## Где меняется пароль

Страница смены пароля доступна по адресу:

```text
/users/password/change/
```

Также ссылка добавлена в личный кабинет покупателя.

## Настройка отправки через почту

Для реальной отправки писем нужно указать данные SMTP-аккаунта. В качестве отправителя можно использовать Yandex или Google. Пароль от обычного входа в почту использовать не нужно — нужен **пароль приложения**.

### Вариант через переменные окружения

Пример для Yandex:

```env
EMAIL_HOST=smtp.yandex.ru
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
EMAIL_HOST_USER=your_mail@yandex.ru
EMAIL_HOST_PASSWORD=your_app_password
DEFAULT_FROM_EMAIL=your_mail@yandex.ru
SITE_URL=http://127.0.0.1:8000
EMAIL_NOTIFICATIONS_ENABLED=True
```

Пример для Google:

```env
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
EMAIL_HOST_USER=your_mail@gmail.com
EMAIL_HOST_PASSWORD=your_app_password
DEFAULT_FROM_EMAIL=your_mail@gmail.com
SITE_URL=http://127.0.0.1:8000
EMAIL_NOTIFICATIONS_ENABLED=True
```

## Проверка без настоящей почты

Если `EMAIL_HOST_USER` или `EMAIL_HOST_PASSWORD` не указаны, Django использует консольный backend. Это значит, что письма не отправляются наружу, а выводятся в терминал, где запущен сервер.

Так можно проверить текст письма без настройки реального SMTP.

## Где находится код

- настройки SMTP: `Project_Nankuev_A/settings.py`;
- функции отправки писем: `main/email_notifications.py`;
- отправка после заказа/возврата: `catalog/views.py`;
- отправка после изменения статусов и смены пароля: `users/views.py`.
