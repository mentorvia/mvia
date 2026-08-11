"""
Custom mVia staff admin.

Access is restricted to staff users (is_staff=True). Everything here is branded
and built to grow: as we add bookings, payouts, promo codes, and audit logs in
later steps, each gets a new section wired into this same shell.

Django's built-in admin still exists at /django-admin/ as a raw-data safety net.
"""

from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import User, EmailLog


def staff_required(view):
    """Allow only logged-in staff. Non-staff get bounced to login."""
    return user_passes_test(lambda u: u.is_authenticated and u.is_staff, login_url="login")(view)


@staff_required
def overview(request):
    """Dashboard home: live summary stats."""
    from decimal import Decimal
    from django.db.models import Sum
    from profiles.models import MentorProfile
    from bookings.models import Booking
    from payments.models import LedgerEntry

    total_users = User.objects.count()
    total_mentors = User.objects.filter(is_mentor=True).count()
    verified_users = User.objects.filter(is_email_verified=True).count()
    unverified_users = total_users - verified_users
    recent_users = User.objects.order_by("-date_joined")[:5]

    # Real operational numbers (now that bookings + payments are live).
    pending_approvals = MentorProfile.objects.filter(
        status=MentorProfile.STATUS_PENDING).count()
    # "Total bookings" = real paid bookings (confirmed or completed only).
    total_bookings = Booking.objects.filter(
        status__in=[Booking.STATUS_CONFIRMED, Booking.STATUS_COMPLETED]).count()
    completed_sessions = Booking.objects.filter(
        status=Booking.STATUS_COMPLETED).count()
    # mVia revenue = platform fees collected, net of refunds.
    fees = LedgerEntry.objects.filter(
        entry_type=LedgerEntry.TYPE_PLATFORM_FEE).aggregate(s=Sum("amount"))["s"] or Decimal("0")
    refunds = LedgerEntry.objects.filter(
        entry_type=LedgerEntry.TYPE_REFUND).aggregate(s=Sum("amount"))["s"] or Decimal("0")
    revenue = fees + refunds  # refunds are negative

    live_stats = [
        ("Pending mentor approvals", pending_approvals),
        ("Total bookings", total_bookings),
        ("Completed sessions", completed_sessions),
        ("Revenue (₹)", revenue),
    ]

    context = {
        "total_users": total_users,
        "total_mentors": total_mentors,
        "verified_users": verified_users,
        "unverified_users": unverified_users,
        "recent_users": recent_users,
        "live_stats": live_stats,
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
@require_POST
def archive_user(request, user_id):
    """
    Archive a mentor or mentee account (the "danger zone" action). Gated on
    zero active bookings — see bookings.services.active_bookings_for_user —
    so an admin must cancel or wait out every pending_payment/
    awaiting_approval/confirmed booking first. Enforced here, not just in the
    UI, so the rule holds even if this endpoint is reached some other way.
    """
    from auditlog.models import AdminAuditLog
    from bookings.services import active_bookings_for_user

    target = get_object_or_404(User, pk=user_id)

    if target.is_archived:
        messages.info(request, f"{target.full_name} is already archived.")
        return redirect("staff:user_detail", user_id=target.id)

    active = active_bookings_for_user(target)
    if active.exists():
        messages.error(
            request,
            f"Cannot archive — {target.full_name} has {active.count()} active "
            f"booking(s). Cancel or resolve them first.")
        return redirect("staff:user_detail", user_id=target.id)

    reason = request.POST.get("reason", "").strip()
    if not reason:
        messages.error(request, "A reason is required to archive an account.")
        return redirect("staff:user_detail", user_id=target.id)

    target.archived_at = timezone.now()
    target.archived_by = request.user
    target.archive_reason = reason
    target.save(update_fields=["archived_at", "archived_by", "archive_reason"])

    AdminAuditLog.record(
        actor=request.user, action="user.archived",
        target=f"{target.full_name} <{target.email}>", reason=reason)
    messages.success(request, f"{target.full_name} has been archived.")
    return redirect("staff:user_detail", user_id=target.id)


@staff_required
@require_POST
def unarchive_user(request, user_id):
    """
    Clear archived_at only. archived_by and archive_reason are deliberately
    left in place — the "this account was archived once" history survives
    the unarchive, and each archive/unarchive cycle gets its own
    AdminAuditLog entry regardless.
    """
    from auditlog.models import AdminAuditLog

    target = get_object_or_404(User, pk=user_id)

    if not target.is_archived:
        messages.info(request, f"{target.full_name} is not archived.")
        return redirect("staff:user_detail", user_id=target.id)

    target.archived_at = None
    target.save(update_fields=["archived_at"])

    AdminAuditLog.record(
        actor=request.user, action="user.unarchived",
        target=f"{target.full_name} <{target.email}>")
    messages.success(request, f"{target.full_name} has been unarchived.")
    return redirect("staff:user_detail", user_id=target.id)


@staff_required
def email_log(request):
    """The email audit log (requirement 7)."""
    from core.pagination import paginate, querystring_without_page
    from django.db.models import Q

    status = request.GET.get("status", "").strip()
    q = request.GET.get("q", "").strip()
    logs = EmailLog.objects.all()
    if q:
        logs = logs.filter(Q(recipient__icontains=q) | Q(subject__icontains=q))
    if status:
        logs = logs.filter(status=status)
    logs = logs.order_by("-created_at")

    status_opts = [{"value": v, "label": l, "selected": status == v}
                   for v, l in EmailLog.STATUS_CHOICES]
    page_obj = paginate(request, logs)
    return render(request, "dashboard/email_log.html", {
        "page": page_obj, "page_obj": page_obj, "status": status,
        "qs": querystring_without_page(request),
        "search_value": q, "search_placeholder": "Search recipient or subject…",
        "filters": [{"name": "status", "label": "Status", "options": status_opts}],
        "has_active": bool(q or status),
        "status_choices": EmailLog.STATUS_CHOICES, "active_nav": "emails",
    })
