"""Member-facing profile URLs."""
from django.urls import path
from . import views

urlpatterns = [
    path("me/", views.mentee_profile, name="mentee_profile"),
    path("become-a-mentor/", views.become_mentor, name="become_mentor"),
]
