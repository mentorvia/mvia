"""URL routes for the custom staff admin."""

from django.urls import path
from . import views

app_name = "staff"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("users/", views.users_list, name="users"),
    path("users/<int:user_id>/", views.user_detail, name="user_detail"),
    path("emails/", views.email_log, name="emails"),
]
