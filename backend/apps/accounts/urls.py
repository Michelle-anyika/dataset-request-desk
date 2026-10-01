from django.urls import path

from apps.accounts import views

urlpatterns = [
    path("login/", views.LoginView.as_view(), name="auth-login"),
    path("me/", views.MeView.as_view(), name="auth-me"),
]
