# Generated for email confirmation support.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0002_customuser_role"),
    ]

    operations = [
        migrations.AddField(
            model_name="customuser",
            name="email_confirmed",
            field=models.BooleanField(
                default=True,
                help_text="Для новых покупателей становится True после перехода по ссылке из письма.",
                verbose_name="Email подтверждён",
            ),
        ),
    ]
