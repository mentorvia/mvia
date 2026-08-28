"""Top-level URL routing for the whole project."""

from django.conf import settings
from django.contrib import admin
from django.urls import path, include, re_path
from django.views.static import serve as static_serve

from profiles import views as profile_views

urlpatterns = [
    # Language switcher (Django's built-in view; the dropdown posts here).
    path("i18n/", include("django.conf.urls.i18n")),
    # Our custom, branded staff admin:
    path("staff/", include("dashboard.urls")),
    # Django's built-in admin kept as a raw-data safety net at a less obvious URL:
    path("django-admin/", admin.site.urls),
    path("", include("core.urls")),
    path("accounts/", include("accounts.urls")),
    path("profile/", include("profiles.urls")),
    path("", include("payments.urls")),
    path("", include("directory.urls")),
    path("", include("bookings.urls")),
    path("", include("reviews.urls")),
    # Public, pre-account mentor application — deliberately NOT under /profile/
    # (that prefix is the existing logged-in-mentee upgrade flow).
    path("become-a-mentor/", profile_views.mentor_application_apply, name="mentor_application_apply"),
    path("become-a-mentor/thanks/", profile_views.mentor_application_thanks, name="mentor_application_thanks"),
]

# Custom, friendly error pages (used when DEBUG is off, i.e. in production).
# Redirect-free: they render a branded page with a safe link so a stale or
# cross-account URL never shows a raw 403/404 (BUG-001 / BUG-002 stale tab).
handler404 = "core.views.custom_404"
handler403 = "core.views.custom_403"

# Serve user-uploaded media (mentor photos). Safe here: media is public profile
# imagery. Files live on the persistent disk (MEDIA_ROOT) on Render.
urlpatterns += [
    re_path(r"^media/(?P<path>.*)$", static_serve, {"document_root": settings.MEDIA_ROOT}),
]
