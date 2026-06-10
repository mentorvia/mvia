"""Staff-console views: mentor approval queue and audit log viewer."""

from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.core.paginator import Paginator
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from .models import MentorProfile
from auditlog.models import AdminAuditLog


def staff_required(view):
    return user_passes_test(lambda u: u.is_authenticated and u.is_staff, login_url="login")(view)


@staff_required
def mentor_queue(request):
    pending = MentorProfile.objects.filter(status=MentorProfile.STATUS_PENDING).select_related("user").order_by("created_at")
    return render(request, "profiles/staff_mentor_queue.html", {
        "pending": pending, "active_nav": "mentors",
    })


@staff_required
def mentor_review(request, mentor_id):
    mentor = get_object_or_404(MentorProfile, pk=mentor_id)
    specializations = mentor.user.mentor_interests.select_related("interest")

    if request.method == "POST":
        action = request.POST.get("action")
        reason = request.POST.get("reason", "").strip()

        if action == "approve":
            mentor.status = MentorProfile.STATUS_APPROVED
            mentor.reviewed_by = request.user
            mentor.reviewed_at = timezone.now()
            mentor.save()
            # Flip the user's mentor flag on.
            mentor.user.is_mentor = True
            mentor.user.save(update_fields=["is_mentor"])
            AdminAuditLog.record(
                actor=request.user, action="mentor.approve",
                target=f"{mentor.user.full_name} <{mentor.user.email}>")
            messages.success(request, f"Approved {mentor.user.get_short_name()} as a mentor.")
            return redirect("staff:mentor_queue")

        elif action == "reject":
            mentor.status = MentorProfile.STATUS_REJECTED
            mentor.reviewed_by = request.user
            mentor.reviewed_at = timezone.now()
            mentor.rejection_reason = reason
            mentor.save()
            AdminAuditLog.record(
                actor=request.user, action="mentor.reject",
                target=f"{mentor.user.full_name} <{mentor.user.email}>", reason=reason)
            messages.success(request, f"Rejected {mentor.user.get_short_name()}'s application.")
            return redirect("staff:mentor_queue")

    return render(request, "profiles/staff_mentor_review.html", {
        "mentor": mentor, "specializations": specializations, "active_nav": "mentors",
    })


@staff_required
def audit_log(request):
    logs = AdminAuditLog.objects.select_related("actor").all()
    paginator = Paginator(logs, 40)
    page = paginator.get_page(request.GET.get("page"))
    return render(request, "profiles/staff_audit_log.html", {
        "page": page, "active_nav": "audit",
    })
