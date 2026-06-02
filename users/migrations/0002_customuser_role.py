from django.db import migrations, models


ROLE_CUSTOMER = "customer"
ROLE_MANAGER = "manager"
ROLE_ADMINISTRATOR = "administrator"
ROLE_GROUPS = {
    ROLE_CUSTOMER: "Покупатели",
    ROLE_MANAGER: "Менеджеры",
    ROLE_ADMINISTRATOR: "Администраторы",
}


def assign_roles_to_existing_users(apps, schema_editor):
    CustomUser = apps.get_model("users", "CustomUser")
    Group = apps.get_model("auth", "Group")

    groups = {
        role: Group.objects.get_or_create(name=group_name)[0]
        for role, group_name in ROLE_GROUPS.items()
    }

    for user in CustomUser.objects.all():
        if user.is_superuser:
            role = ROLE_ADMINISTRATOR
            user.is_staff = True
        elif user.is_staff:
            role = ROLE_MANAGER
        else:
            role = ROLE_CUSTOMER
            user.is_staff = False
            user.is_superuser = False

        user.role = role
        user.save(update_fields=["role", "is_staff", "is_superuser"])
        user.groups.add(groups[role])


def reverse_roles(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name__in=ROLE_GROUPS.values()).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="customuser",
            name="role",
            field=models.CharField(
                choices=[
                    ("customer", "Покупатель"),
                    ("manager", "Менеджер"),
                    ("administrator", "Администратор"),
                ],
                db_index=True,
                default="customer",
                help_text="Определяет доступ пользователя: покупатель, менеджер или администратор.",
                max_length=20,
                verbose_name="Роль в системе",
            ),
        ),
        migrations.RunPython(assign_roles_to_existing_users, reverse_roles),
    ]
