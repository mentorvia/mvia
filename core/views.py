"""Views for the core app: homepage, health check, and the logged-in dashboard."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.http import JsonResponse


def home(request):
    # Show up to 4 real approved, available mentors (with photos preferred) in
    # the "Meet our mentors" section. Falls back gracefully if there are none.
    from profiles.models import MentorProfile
    featured = list(
        MentorProfile.objects.filter(
            status=MentorProfile.STATUS_APPROVED, is_available=True
        ).select_related("user").order_by("-id")[:4]
    )
    return render(request, "home.html", {"featured_mentors": featured})


def health(request):
    return JsonResponse({"status": "ok"})


@login_required
def dashboard(request):
    """The signed-in landing area. Grows as we add features."""
    return render(request, "dashboard.html")
