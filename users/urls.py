from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

app_name = "users"

urlpatterns = [
    path("register/", views.register_view, name="register"),
    path("confirm/sent/", views.email_confirmation_sent_view, name="email_confirmation_sent"),
    path("confirm/<uidb64>/<token>/", views.email_confirm_view, name="email_confirm"),
    path("login/", views.login_view, name="login"),
    path("profile/", views.profile_view, name="profile"),
    path("password/change/", views.EmailPasswordChangeView.as_view(), name="password_change"),
    path("password/reset/", views.EmailPasswordResetView.as_view(), name="password_reset"),
    path("password/reset/done/", views.EmailPasswordResetDoneView.as_view(), name="password_reset_done"),
    path("password/reset/<uidb64>/<token>/", views.EmailPasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("password/reset/complete/", views.EmailPasswordResetCompleteView.as_view(), name="password_reset_complete"),
    path("staff/", views.staff_dashboard, name="staff_dashboard"),
    path("staff/orders/", views.staff_orders, name="staff_orders"),
    path("staff/orders/<int:order_id>/", views.staff_order_detail, name="staff_order_detail"),
    path("staff/returns/", views.staff_returns, name="staff_returns"),
    path("staff/returns/<int:return_id>/", views.staff_return_detail, name="staff_return_detail"),
    path("logout/", LogoutView.as_view(next_page="home"), name="logout"),
]
