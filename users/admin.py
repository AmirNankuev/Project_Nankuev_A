from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import CustomUser
from .roles import UserRole


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ("id", "username", "full_name", "email", "email_confirmed", "phone", "role", "is_staff", "is_active")
    list_filter = ("role", "email_confirmed", "is_staff", "is_active", "is_superuser", "groups")
    search_fields = ("username", "full_name", "email", "phone")
    ordering = ("username",)

    fieldsets = (
        (None, {"fields": ("username", "password")}),
        ("Персональные данные", {"fields": ("full_name", "email", "email_confirmed", "phone")}),
        ("Роль и права", {
            "fields": ("role", "is_active", "is_staff", "is_superuser", "groups", "user_permissions"),
            "description": (
                "Основное поле — «Роль в системе». После сохранения Django автоматически "
                "синхронизирует is_staff, is_superuser и группу пользователя."
            ),
        }),
        ("Важные даты", {"fields": ("last_login", "date_joined")}),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("username", "full_name", "email", "email_confirmed", "phone", "role", "password1", "password2"),
        }),
    )

    readonly_fields = ("last_login", "date_joined")

    def get_readonly_fields(self, request, obj=None):
        readonly = list(super().get_readonly_fields(request, obj))
        if not getattr(request.user, "can_manage_users", False) and not request.user.is_superuser:
            readonly.extend(["role", "is_staff", "is_superuser", "groups", "user_permissions"])
        return tuple(readonly)

    def has_module_permission(self, request):
        return getattr(request.user, "can_manage_users", False) or request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return getattr(request.user, "can_manage_users", False) or request.user.is_superuser

    def has_add_permission(self, request):
        return getattr(request.user, "can_manage_users", False) or request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return getattr(request.user, "can_manage_users", False) or request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return getattr(request.user, "can_manage_users", False) or request.user.is_superuser
