"""Member-facing profile URLs."""
from django.urls import path
from . import views
from . import member_profile_editor

urlpatterns = [
    path("me/", views.mentee_profile, name="mentee_profile"),
    path("become-a-mentor/", views.become_mentor, name="become_mentor"),
    path("mentor/edit/", member_profile_editor.mentor_profile_edit, name="mentor_profile_edit"),
]
