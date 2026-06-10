"""URL routes for the custom staff admin."""

from django.urls import path
from . import views
from interests import staff_views as interest_views

app_name = "staff"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("users/", views.users_list, name="users"),
    path("users/<int:user_id>/", views.user_detail, name="user_detail"),
    path("emails/", views.email_log, name="emails"),
    # Interests management
    path("interests/", interest_views.interests_list, name="interests"),
    path("interests/add/", interest_views.interest_add, name="interest_add"),
    path("interests/<int:interest_id>/edit/", interest_views.interest_edit, name="interest_edit"),
    path("interests/<int:interest_id>/delete/", interest_views.interest_delete, name="interest_delete"),
    path("interests/custom/", interest_views.custom_review, name="custom_review"),
]
