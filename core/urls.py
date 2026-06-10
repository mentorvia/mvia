"""URL routes for the core app."""

from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("healthz/", views.health, name="health"),
]
