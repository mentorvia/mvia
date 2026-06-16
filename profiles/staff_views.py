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


# ---------- Staff: add a placeholder (display-only) mentor ----------

from django import forms
from accounts.models import User
from interests.models import Interest, MentorInterest


class PlaceholderMentorForm(forms.Form):
    full_name = forms.CharField(max_length=150)
    current_role = forms.CharField(max_length=120)
    company = forms.CharField(max_length=120)
    years_experience = forms.IntegerField(min_value=0)
    bio = forms.CharField(widget=forms.Textarea(attrs={"rows": 4}))
    hourly_rate = forms.DecimalField(min_value=0, decimal_places=2, max_digits=10,
                                     label="Rate per session (₹)")

    def clean_hourly_rate(self):
        r = self.cleaned_data["hourly_rate"]
        if r < 0:
            raise forms.ValidationError("Rate can't be negative.")
        return r


@staff_required
def add_placeholder_mentor(request):
    from profiles.models import MentorProfile
    from django.utils import timezone

    interests = Interest.objects.filter(is_approved=True).order_by("name")

    if request.method == "POST":
        form = PlaceholderMentorForm(request.POST)
        chosen = set(int(x) for x in request.POST.getlist("interests"))
        if form.is_valid() and not chosen:
            form.add_error(None, "Select at least one specialization.")
        if form.is_valid() and chosen:
            cd = form.cleaned_data
            user = User.objects.create_placeholder_mentor(full_name=cd["full_name"])
            MentorProfile.objects.create(
                user=user,
                current_role=cd["current_role"],
                company=cd["company"],
                years_experience=cd["years_experience"],
                bio=cd["bio"],
                hourly_rate=cd["hourly_rate"],
                status=MentorProfile.STATUS_APPROVED,   # admin-added → directly approved
                is_available=True,
                reviewed_by=request.user,
                reviewed_at=timezone.now(),
            )
            for iid in chosen:
                MentorInterest.objects.get_or_create(user=user, interest_id=iid)

            from auditlog.models import AdminAuditLog
            AdminAuditLog.record(
                actor=request.user, action="mentor.placeholder_add",
                target=f"{cd['full_name']} (placeholder, no email)")
            messages.success(request, f"Added placeholder mentor “{cd['full_name']}”. They appear in the directory now; add their email later to enable login.")
            return redirect("staff:mentor_queue")
    else:
        form = PlaceholderMentorForm()

    return render(request, "profiles/staff_add_placeholder.html", {
        "form": form, "interests": interests, "active_nav": "mentors",
    })
