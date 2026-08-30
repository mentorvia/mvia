"""Directory URLs."""
from django.urls import path
from . import views

urlpatterns = [
    path("mentors/", views.directory, name="directory"),
    # Legacy numeric URL → 301 redirects to the canonical slug URL.
    path("mentors/<int:user_id>/", views.mentor_profile_legacy, name="mentor_profile_legacy"),
    # Canonical: /mentors/christina-sunil-6/  (id identifies; slug is decoration).
    path("mentors/<slug:name_slug>-<int:user_id>/", views.mentor_profile, name="mentor_profile"),
]
