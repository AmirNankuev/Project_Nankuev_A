from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

app_name = "users"

urlpatterns = [
    path("register/", views.register_view, name="register"),
    path("login/", views.login_view, name="login"),
    path("logout/", LogoutView.as_view(next_page="home"), name="logout"),
]