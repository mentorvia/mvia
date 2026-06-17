"""Top-level URL routing for the whole project."""

from django.conf import settings
from django.contrib import admin
from django.urls import path, include, re_path
from django.views.static import serve as static_serve

urlpatterns = [
    # Our custom, branded staff admin:
    path("staff/", include("dashboard.urls")),
    # Django's built-in admin kept as a raw-data safety net at a less obvious URL:
    path("django-admin/", admin.site.urls),
    path("", include("core.urls")),
    path("accounts/", include("accounts.urls")),
    path("profile/", include("profiles.urls")),
    path("", include("directory.urls")),
    path("", include("bookings.urls")),
    path("", include("reviews.urls")),
]

# Serve user-uploaded media (mentor photos). Safe here: media is public profile
# imagery. Files live on the persistent disk (MEDIA_ROOT) on Render.
urlpatterns += [
    re_path(r"^media/(?P<path>.*)$", static_serve, {"document_root": settings.MEDIA_ROOT}),
]
