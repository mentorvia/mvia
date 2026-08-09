"""URL routes for authentication."""

from django.urls import path
from . import views

urlpatterns = [
    path("signup/", views.signup, name="signup"),
    path("verify/<str:token>/", views.verify_email, name="verify_email"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("password-reset/", views.password_reset_request, name="password_reset_request"),
    path("password-reset/<str:token>/", views.password_reset_confirm, name="password_reset_confirm"),
    path("set-password/", views.force_set_password, name="force_set_password"),
]
