"""Top-level URL routing for the whole project."""

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    # Our custom, branded staff admin:
    path("staff/", include("dashboard.urls")),
    # Django's built-in admin kept as a raw-data safety net at a less obvious URL:
    path("django-admin/", admin.site.urls),
    path("", include("core.urls")),
    path("accounts/", include("accounts.urls")),
]
