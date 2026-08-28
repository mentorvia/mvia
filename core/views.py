"""Views for the core app: homepage, health check, and the logged-in dashboard."""

import json
import zoneinfo

from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from accounts.decorators import redirect_if_must_change_password, redirect_if_archived


def home(request):
    # Show up to 4 real approved, available mentors (with photos preferred) in
    # the "Meet our mentors" section. Falls back gracefully if there are none.
    from profiles.models import MentorProfile
    featured = list(
        MentorProfile.objects.filter(
            status=MentorProfile.STATUS_APPROVED, is_available=True, user__archived_at__isnull=True,
        ).select_related("user").order_by("-id")[:4]
    )
    return render(request, "home.html", {"featured_mentors": featured})


def health(request):
    return JsonResponse({"status": "ok"})


@login_required
@redirect_if_archived
@redirect_if_must_change_password
def dashboard(request):
    """The signed-in landing area: routes to the mentee or mentor dashboard."""
    from .dashboard_data import resolve_active_role, mentee_context, mentor_context

    user = request.user
    active_role = resolve_active_role(user, request.session)

    context = {"active_role": active_role, "can_toggle": user.is_mentee and user.is_mentor}
    context.update(mentor_context(user) if active_role == "mentor" else mentee_context(user))

    return render(request, "dashboard.html", context)


@login_required
@require_POST
def set_dashboard_role(request, role):
    """Persist the dual-role user's dashboard toggle choice in their session."""
    user = request.user
    if (role == "mentee" and user.is_mentee) or (role == "mentor" and user.is_mentor):
        request.session["dashboard_role"] = role
    return redirect("dashboard")


@login_required
@require_POST
def set_timezone(request):
    """
    Silently save the browser-detected IANA timezone on first dashboard visit
    (called by a small inline script in dashboard.html).

    Guard: only write while the user is still at the model default
    ("Asia/Kolkata") — never overwrite a value that's already been recorded,
    whether that came from this same auto-detection earlier or a manual
    setting added later. Without this guard, a user's timezone would get
    silently reset on every visit (e.g. while traveling or behind a VPN)
    instead of staying at whatever was last deliberately recorded.
    """
    try:
        data = json.loads(request.body or "{}")
    except ValueError:
        data = {}
    tz_name = (data.get("timezone") or "").strip()

    if tz_name and request.user.timezone == "Asia/Kolkata":
        try:
            zoneinfo.ZoneInfo(tz_name)  # validate it's a real IANA name
        except Exception:
            return JsonResponse({"saved": False}, status=400)
        request.user.timezone = tz_name
        request.user.save(update_fields=["timezone"])
        return JsonResponse({"saved": True})

    return JsonResponse({"saved": False})

   def custom_404(request, exception=None):
       from django.shortcuts import render
       return render(request, "404.html", status=404)


   def custom_403(request, exception=None):
       from django.shortcuts import render
       return render(request, "403.html", status=403)
