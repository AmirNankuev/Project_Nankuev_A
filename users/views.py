from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Prefetch
from django.shortcuts import render, redirect

from catalog.models import ProductImage
from main.models import CustomerProfile, Order, OrderItem

from .forms import RegisterForm, LoginForm, ProfileForm


def _sync_customer_profile(user):
    profile, created = CustomerProfile.objects.get_or_create(
        user=user,
        defaults={
            "phone": user.phone,
            "account_status": "active",
        },
    )

    if not created and profile.phone != user.phone:
        profile.phone = user.phone
        profile.save(update_fields=["phone"])

    return profile


def register_view(request):
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        form = RegisterForm(request.POST)

        if form.is_valid():
            with transaction.atomic():
                user = form.save()
                CustomerProfile.objects.get_or_create(
                    user=user,
                    defaults={
                        "phone": user.phone,
                        "account_status": "active",
                    },
                )
            login(request, user)
            return redirect("users:profile")
    else:
        form = RegisterForm()

    return render(request, "registration/register.html", {
        "form": form
    })


def login_view(request):
    if request.user.is_authenticated:
        return redirect("home")

    if request.method == "POST":
        form = LoginForm(request, data=request.POST)

        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect("home")
    else:
        form = LoginForm()

    return render(request, "registration/login.html", {
        "form": form
    })


@login_required
def profile_view(request):
    profile = _sync_customer_profile(request.user)

    if request.method == "POST":
        form = ProfileForm(request.POST, instance=request.user)

        if form.is_valid():
            with transaction.atomic():
                user = form.save()
                profile.phone = user.phone
                profile.save(update_fields=["phone"])
            messages.success(request, "Данные личного кабинета обновлены.")
            return redirect("users:profile")
    else:
        form = ProfileForm(instance=request.user)

    order_items_queryset = (
        OrderItem.objects
        .select_related("product_variant", "product_variant__product", "product_variant__color")
        .prefetch_related(
            Prefetch(
                "product_variant__product__images",
                queryset=ProductImage.objects.filter(is_main=True).order_by("sort_order", "id"),
                to_attr="profile_main_images",
            )
        )
    )

    orders = (
        Order.objects
        .filter(customer=request.user)
        .prefetch_related(Prefetch("items", queryset=order_items_queryset))
        .order_by("-created_at")
    )

    return render(request, "registration/profile.html", {
        "form": form,
        "profile": profile,
        "orders": orders,
    })
