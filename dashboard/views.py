"""
Custom mVia staff admin.

Access is restricted to staff users (is_staff=True). Everything here is branded
and built to grow: as we add bookings, payouts, promo codes, and audit logs in
later steps, each gets a new section wired into this same shell.

Django's built-in admin still exists at /django-admin/ as a raw-data safety net.
"""

from django.contrib.auth.decorators import user_passes_test
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render, get_object_or_404

from accounts.models import User, EmailLog


def staff_required(view):
    """Allow only logged-in staff. Non-staff get bounced to login."""
    return user_passes_test(lambda u: u.is_authenticated and u.is_staff, login_url="login")(view)


@staff_required
def overview(request):
    """Dashboard home: live summary stats."""
    total_users = User.objects.count()
    total_mentors = User.objects.filter(is_mentor=True).count()
    verified_users = User.objects.filter(is_email_verified=True).count()
    unverified_users = total_users - verified_users
    recent_users = User.objects.order_by("-date_joined")[:5]

    # Stats that depend on features not built yet. Shown as "—" with a note,
    # so the dashboard is honest about what's live vs. coming.
    coming_soon_stats = [
        ("Pending mentor approvals", "Mentor applications (next steps)"),
        ("Total bookings", "Booking system (later step)"),
        ("Completed sessions", "Booking system (later step)"),
        ("Revenue", "Payments (later step)"),
    ]

    context = {
        "total_users": total_users,
        "total_mentors": total_mentors,
        "verified_users": verified_users,
        "unverified_users": unverified_users,
        "recent_users": recent_users,
        "coming_soon_stats": coming_soon_stats,
        "active_nav": "overview",
    }
    return render(request, "dashboard/overview.html", context)


@staff_required
def users_list(request):
    """Searchable, paginated list of all users."""
    query = request.GET.get("q", "").strip()
    users = User.objects.all()
    if query:
        users = users.filter(Q(full_name__icontains=query) | Q(email__icontains=query))
    users = users.order_by("-date_joined")

    paginator = Paginator(users, 25)
    page = paginator.get_page(request.GET.get("page"))

    return render(request, "dashboard/users_list.html", {
        "page": page, "query": query, "active_nav": "users",
    })


@staff_required
def user_detail(request, user_id):
    """Detail view for a single user, including their email history."""
    target = get_object_or_404(User, pk=user_id)
    emails = EmailLog.objects.filter(recipient=target.email).order_by("-created_at")[:20]
    return render(request, "dashboard/user_detail.html", {
        "target": target, "emails": emails, "active_nav": "users",
    })


@staff_required
def email_log(request):
    """The email audit log (requirement 7)."""
    status = request.GET.get("status", "").strip()
    logs = EmailLog.objects.all()
    if status:
        logs = logs.filter(status=status)
    logs = logs.order_by("-created_at")

    paginator = Paginator(logs, 30)
    page = paginator.get_page(request.GET.get("page"))

    return render(request, "dashboard/email_log.html", {
        "page": page, "status": status,
        "status_choices": EmailLog.STATUS_CHOICES, "active_nav": "emails",
    })
