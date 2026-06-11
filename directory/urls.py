"""Directory URLs."""
from django.urls import path
from . import views

urlpatterns = [
    path("mentors/", views.directory, name="directory"),
    path("mentors/<int:user_id>/", views.mentor_profile, name="mentor_profile"),
]
