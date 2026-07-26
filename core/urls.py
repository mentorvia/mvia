"""URL routes for the core app."""

from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("healthz/", views.health, name="health"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("dashboard/view-as/<str:role>/", views.set_dashboard_role, name="dashboard_set_role"),
    path("dashboard/set-timezone/", views.set_timezone, name="dashboard_set_timezone"),
]
