"""Helpers for shop roles and Django groups/permissions."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db import OperationalError, ProgrammingError


class UserRole:
    CUSTOMER = "customer"
    MANAGER = "manager"
    ADMINISTRATOR = "administrator"


ROLE_GROUPS = {
    UserRole.CUSTOMER: "Покупатели",
    UserRole.MANAGER: "Менеджеры",
    UserRole.ADMINISTRATOR: "Администраторы",
}

MANAGER_PERMISSIONS = (
    # Каталог: менеджер может вести товары, остатки, категории и справочники.
    ("catalog", "view_brand"),
    ("catalog", "add_brand"),
    ("catalog", "change_brand"),
    ("catalog", "view_category"),
    ("catalog", "add_category"),
    ("catalog", "change_category"),
    ("catalog", "view_color"),
    ("catalog", "add_color"),
    ("catalog", "change_color"),
    ("catalog", "view_product"),
    ("catalog", "add_product"),
    ("catalog", "change_product"),
    ("catalog", "view_productvariant"),
    ("catalog", "add_productvariant"),
    ("catalog", "change_productvariant"),
    ("catalog", "view_productimage"),
    ("catalog", "add_productimage"),
    ("catalog", "change_productimage"),

    # Заказы, возвраты и покупатели: менеджер обрабатывает, но не удаляет.
    ("main", "view_customerprofile"),
    ("main", "change_customerprofile"),
    ("main", "view_order"),
    ("main", "change_order"),
    ("main", "view_orderitem"),
    ("main", "view_returnrequest"),
    ("main", "add_returnrequest"),
    ("main", "change_returnrequest"),
    ("main", "view_cartitem"),
)

ADMINISTRATOR_APP_LABELS = {"catalog", "main", "users"}


def role_group_names() -> set[str]:
    return set(ROLE_GROUPS.values())


def role_group_name(role: str) -> str:
    return ROLE_GROUPS.get(role, ROLE_GROUPS[UserRole.CUSTOMER])


def role_permissions(role: str):
    """Return queryset with permissions for a role."""
    if role == UserRole.MANAGER:
        query = None
        for app_label, codename in MANAGER_PERMISSIONS:
            condition = {"content_type__app_label": app_label, "codename": codename}
            item = Permission.objects.filter(**condition)
            query = item if query is None else query | item
        return query.distinct() if query is not None else Permission.objects.none()

    if role == UserRole.ADMINISTRATOR:
        return Permission.objects.filter(content_type__app_label__in=ADMINISTRATOR_APP_LABELS)

    return Permission.objects.none()


def setup_role_groups(*args, **kwargs):
    """Create role groups and fill permissions after migrations."""
    try:
        for role, group_name in ROLE_GROUPS.items():
            group, _ = Group.objects.get_or_create(name=group_name)
            group.permissions.set(role_permissions(role))
    except (OperationalError, ProgrammingError):
        # During the first migrations database tables may not exist yet.
        return


def sync_user_role(user):
    """Synchronize role field with admin flags and Django groups."""
    if not getattr(user, "pk", None):
        return

    try:
        role = getattr(user, "role", UserRole.CUSTOMER) or UserRole.CUSTOMER

        is_admin = role == UserRole.ADMINISTRATOR
        is_manager = role == UserRole.MANAGER
        target_is_staff = is_manager or is_admin
        target_is_superuser = is_admin

        fields_to_update = []
        if user.is_staff != target_is_staff:
            user.is_staff = target_is_staff
            fields_to_update.append("is_staff")
        if user.is_superuser != target_is_superuser:
            user.is_superuser = target_is_superuser
            fields_to_update.append("is_superuser")

        if fields_to_update:
            get_user_model().objects.filter(pk=user.pk).update(**{field: getattr(user, field) for field in fields_to_update})

        setup_role_groups()
        user.groups.remove(*Group.objects.filter(name__in=role_group_names()))
        user.groups.add(Group.objects.get(name=role_group_name(role)))
    except (OperationalError, ProgrammingError):
        return
