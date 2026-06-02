from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect


def _staff_redirect_name(user):
    if getattr(user, "can_manage_shop", False):
        return "users:staff_dashboard"
    return "home"


def customer_required(view_func):
    @login_required
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if getattr(request.user, "is_customer_role", False):
            return view_func(request, *args, **kwargs)

        messages.error(request, "Это действие доступно только покупателю.")
        return redirect(_staff_redirect_name(request.user))

    return wrapper


def manager_required(view_func):
    @login_required
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if getattr(request.user, "can_manage_shop", False):
            return view_func(request, *args, **kwargs)

        messages.error(request, "Раздел доступен только менеджеру или администратору.")
        return redirect("home")

    return wrapper
