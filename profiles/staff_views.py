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
    from core.pagination import paginate, querystring_without_page, toggle_param_querystring
    from django.db.models import Q

    pending = MentorProfile.objects.filter(
        status=MentorProfile.STATUS_PENDING).select_related("user").order_by("created_at")

    pending_identity_changes = MentorProfile.objects.filter(
        pending_identity_changes__isnull=False
    ).select_related("user").order_by("pending_review_requested_at")

    approved = MentorProfile.objects.filter(
        status=MentorProfile.STATUS_APPROVED).select_related("user").order_by("user__full_name")

    archived_count = MentorProfile.objects.filter(
        status=MentorProfile.STATUS_APPROVED, user__archived_at__isnull=False).count()
    show_archived = request.GET.get("show_archived") == "1"
    if not show_archived:
        approved = approved.filter(user__archived_at__isnull=True)

    q = request.GET.get("q", "").strip()
    only = request.GET.get("only", "").strip()
    if q:
        approved = approved.filter(
            Q(user__full_name__icontains=q) | Q(current_role__icontains=q) |
            Q(company__icontains=q))
    if only == "placeholder":
        approved = approved.filter(user__is_placeholder=True)
    elif only == "live":
        approved = approved.filter(is_available=True)

    only_opts = [
        {"value": "live", "label": "Live only", "selected": only == "live"},
        {"value": "placeholder", "label": "No-email only", "selected": only == "placeholder"},
    ]
    page_obj = paginate(request, approved)
    return render(request, "profiles/staff_mentor_queue.html", {
        "pending": pending, "approved": page_obj, "page_obj": page_obj,
        "pending_identity_changes": pending_identity_changes,
        "qs": querystring_without_page(request),
        "search_value": q, "search_placeholder": "Search name, role, company…",
        "filters": [{"name": "only", "label": "Show", "options": only_opts}],
        "has_active": bool(q or only),
        "active_nav": "mentors",
        "show_archived": show_archived,
        "archived_count": archived_count,
        "show_archived_toggle_qs": toggle_param_querystring(request, "show_archived"),
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
    from core.pagination import paginate, querystring_without_page
    from django.db.models import Q

    logs = AdminAuditLog.objects.select_related("actor").all()
    q = request.GET.get("q", "").strip()
    action = request.GET.get("action", "").strip()
    if q:
        logs = logs.filter(
            Q(actor__full_name__icontains=q) | Q(target__icontains=q) |
            Q(action__icontains=q))
    if action:
        logs = logs.filter(action=action)

    # Distinct actions present, for the filter dropdown.
    actions = AdminAuditLog.objects.values_list("action", flat=True).distinct().order_by("action")
    action_opts = [{"value": a, "label": a, "selected": action == a} for a in actions]

    page_obj = paginate(request, logs)
    return render(request, "profiles/staff_audit_log.html", {
        "page": page_obj, "page_obj": page_obj,
        "qs": querystring_without_page(request),
        "search_value": q, "search_placeholder": "Search actor, target, action…",
        "filters": [{"name": "action", "label": "Action", "options": action_opts}],
        "has_active": bool(q or action),
        "active_nav": "audit",
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


# ---------- Staff: activate login for a placeholder mentor ----------

class ActivateLoginForm(forms.Form):
    email = forms.EmailField(label="Mentor's real email address")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        existing = User.objects.filter(email__iexact=email).first()
        if existing:
            raise forms.ValidationError("That email is already in use by another account.")
        return email


@staff_required
def activate_mentor_login(request, mentor_id):
    import secrets

    from django.urls import reverse

    from accounts.emails import send_email
    from auditlog.models import AdminAuditLog
    from profiles.models import MentorProfile

    profile = get_object_or_404(MentorProfile, pk=mentor_id)
    user = profile.user

    if not user.is_placeholder:
        messages.info(request, "This mentor already has a login.")
        return redirect("staff:edit_mentor_profile", mentor_id=profile.id)

    if request.method == "POST":
        form = ActivateLoginForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            temp_password = secrets.token_urlsafe(12)

            user.activate_login(email, temp_password)
            user.must_change_password = True
            user.save(update_fields=["must_change_password"])

            login_url = request.build_absolute_uri(reverse("login"))
            send_email(
                to_email=email,
                subject="Welcome to mVia — Set up your account",
                template_name="mentor_login_activated",
                body=(
                    f"Hi {user.get_short_name()},\n\n"
                    f"Your mVia mentor account is ready. Here are your login details:\n\n"
                    f"Email: {email}\n"
                    f"Temporary password: {temp_password}\n\n"
                    f"Log in here: {login_url}\n\n"
                    f"You'll be asked to set a new password the first time you log in.\n\n"
                    f"— The mVia team"
                ),
            )

            AdminAuditLog.record(
                actor=request.user, action="mentor.login_activated",
                target=f"{user.full_name} <{email}>")
            messages.success(request, f"Login activated. Welcome email sent to {email}.")
            return redirect("staff:edit_mentor_profile", mentor_id=profile.id)
    else:
        form = ActivateLoginForm()

    return render(request, "profiles/staff_activate_login.html", {
        "form": form, "mentor": profile, "active_nav": "mentors",
    })


# ---------- Staff: review a mentor-submitted identity-field change request ----------

IDENTITY_FIELD_LABELS = [
    ("full_name", "Full name"),
    ("industry", "Industry"),
    ("years_experience", "Years of experience"),
    ("credentials", "Credentials"),
    ("current_role", "Current role"),
    ("company", "Current company"),
]


@staff_required
def review_identity_change(request, mentor_id):
    from profiles.models import MentorProfile

    profile = get_object_or_404(MentorProfile, pk=mentor_id)

    if not profile.pending_identity_changes:
        messages.info(request, "No pending profile change for this mentor.")
        return redirect("staff:mentor_review", mentor_id=profile.id)

    pending = profile.pending_identity_changes
    current = {
        "full_name": profile.user.full_name,
        "industry": profile.industry,
        "years_experience": profile.years_experience,
        "credentials": profile.credentials,
        "current_role": profile.current_role,
        "company": profile.company,
    }
    diff_rows = [
        {"key": key, "label": label, "current": current[key], "proposed": pending.get(key)}
        for key, label in IDENTITY_FIELD_LABELS
    ]

    if request.method == "POST":
        action = request.POST.get("action")
        target = f"{profile.user.full_name} <{profile.user.email}>"

        if action == "approve":
            if pending.get("full_name") and pending["full_name"] != profile.user.full_name:
                profile.user.full_name = pending["full_name"]
                profile.user.save(update_fields=["full_name"])
            profile.industry = pending.get("industry", profile.industry)
            profile.years_experience = pending.get("years_experience", profile.years_experience)
            profile.credentials = pending.get("credentials", profile.credentials)
            profile.current_role = pending.get("current_role", profile.current_role)
            profile.company = pending.get("company", profile.company)
            profile.pending_identity_changes = None
            profile.pending_review_requested_at = None
            profile.save()
            AdminAuditLog.record(
                actor=request.user, action="mentor.identity_change_approved", target=target)
            messages.success(request, f"Approved profile changes for {profile.user.get_short_name()}.")
            return redirect("staff:mentor_queue")

        elif action == "reject":
            reason = request.POST.get("reason", "").strip()
            profile.pending_identity_changes = None
            profile.pending_review_requested_at = None
            profile.save(update_fields=["pending_identity_changes", "pending_review_requested_at"])
            AdminAuditLog.record(
                actor=request.user, action="mentor.identity_change_rejected",
                target=target, reason=reason)
            messages.success(request, f"Rejected profile changes for {profile.user.get_short_name()}.")
            return redirect("staff:mentor_queue")

    return render(request, "profiles/staff_review_identity_change.html", {
        "mentor": profile, "diff_rows": diff_rows, "active_nav": "mentors",
    })


# ---------- Staff: review public mentor applications (/become-a-mentor/) ----------

from .models import MentorApplication
from .forms import MentorApplicationApprovalForm


@staff_required
def mentor_application_queue(request):
    from core.pagination import paginate, querystring_without_page

    status_filter = request.GET.get("status", MentorApplication.STATUS_PENDING)
    applications = MentorApplication.objects.all()
    if status_filter != "all":
        applications = applications.filter(status=status_filter)

    page_obj = paginate(request, applications)
    return render(request, "profiles/staff_mentor_applications.html", {
        "page_obj": page_obj, "status_filter": status_filter,
        "qs": querystring_without_page(request),
        "active_nav": "mentor_applications",
    })


@staff_required
def mentor_application_review(request, application_id):
    from django.urls import reverse

    from accounts.emails import send_email
    from accounts.models import User, EmailToken
    from .views import _interest_categories, _mark_expansion

    application = get_object_or_404(MentorApplication, pk=application_id)
    target = f"{application.name} <{application.email}>"
    approval_form = MentorApplicationApprovalForm()
    selected_ids = set()

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "approve" and application.status == MentorApplication.STATUS_PENDING:
            form = MentorApplicationApprovalForm(request.POST)
            chosen = set(int(x) for x in request.POST.getlist("interests"))
            if form.is_valid() and not chosen:
                form.add_error(None, "Select at least one specialization.")
            if User.objects.filter(email__iexact=application.email).exists():
                form.add_error(None, f"{application.email} is already in use by another account.")
            if form.is_valid() and chosen:
                cd = form.cleaned_data

                # Create the mentor account WITHOUT a password. Instead of a
                # system-generated temp password (clunky first login), we send
                # them a "set your password" link (reusing the reset-token
                # flow). is_email_verified=True because they proved the address
                # via the application and re-confirm it by clicking the link.
                user = User(
                    email=application.email.strip().lower(),
                    full_name=application.name,
                    is_mentee=False, is_mentor=True,
                    is_placeholder=False,
                    is_email_verified=True,
                )
                user.set_unusable_password()
                user.save()

                MentorProfile.objects.create(
                    user=user,
                    current_role=application.current_role,
                    company=application.current_company,
                    years_experience=application.experience_years,
                    bio=application.bio,
                    hourly_rate=cd["hourly_rate"],
                    industry=application.industry,
                    status=MentorProfile.STATUS_APPROVED,
                    is_available=True,
                    reviewed_by=request.user,
                    reviewed_at=timezone.now(),
                )
                for iid in chosen:
                    MentorInterest.objects.get_or_create(user=user, interest_id=iid)

                application.status = MentorApplication.STATUS_APPROVED
                application.reviewed_by = request.user
                application.reviewed_at = timezone.now()
                application.created_user = user
                application.save()

                # Email a "set your password" link (72h). If it expires, the
                # mentor can use "Forgot password" on the login page.
                token = EmailToken.issue(user, EmailToken.PURPOSE_RESET, hours_valid=72)
                set_password_url = request.build_absolute_uri(
                    reverse("password_reset_confirm", args=[token.token])
                )
                send_email(
                    to_email=user.email,
                    subject="Welcome to mVia — set your password",
                    template_name="mentor_welcome_set_password",
                    body=(
                        f"Hi {user.get_short_name()},\n\n"
                        f"Your mentor application was approved — welcome to mVia!\n\n"
                        f"To finish setting up your account, choose your password here:\n"
                        f"{set_password_url}\n\n"
                        f"This link expires in 72 hours. If it expires, you can use "
                        f"“Forgot password” on the login page to get a new one.\n\n"
                        f"— The mVia team"
                    ),
                )
                AdminAuditLog.record(
                    actor=request.user, action="mentor_application.approved", target=target)
                messages.success(request, f"Approved {application.name}. A set-password email was sent to {application.email}.")
                return redirect("staff:mentor_application_review", application_id=application.id)
            approval_form = form
            selected_ids = chosen

        elif action == "reject" and application.status == MentorApplication.STATUS_PENDING:
            reason = request.POST.get("reason", "").strip()
            if len(reason) < 20:
                messages.error(request, "Please provide a more detailed reason (at least 20 characters).")
                return redirect("staff:mentor_application_review", application_id=application.id)

            application.status = MentorApplication.STATUS_REJECTED
            application.reviewed_by = request.user
            application.reviewed_at = timezone.now()
            application.review_notes = reason
            application.save()
            send_email(
                to_email=application.email,
                subject="Update on your mVia mentor application",
                template_name="mentor_application_rejected",
                body=(
                    f"Hi {application.name},\n\n"
                    f"Thank you for taking the time to apply to become a mentor at mVia, "
                    f"and for sharing your experience with us. After careful review, we're "
                    f"not able to move forward with your application at this time.\n\n"
                    f"We appreciate your interest in mVia and wish you the best.\n\n"
                    f"— The mVia team"
                ),
            )
            AdminAuditLog.record(
                actor=request.user, action="mentor_application.rejected",
                target=target, reason=reason)
            messages.success(request, f"Rejected {application.name}'s application.")
            return redirect("staff:mentor_application_queue")

        elif action == "request_more_info" and application.status == MentorApplication.STATUS_PENDING:
            note = request.POST.get("message", "").strip()
            if not note:
                messages.error(request, "Enter a message describing what more you need.")
                return redirect("staff:mentor_application_review", application_id=application.id)

            send_email(
                to_email=application.email,
                subject="A quick follow-up on your mVia mentor application",
                template_name="mentor_application_more_info",
                body=(
                    f"Hi {application.name},\n\n"
                    f"Thanks again for applying to mentor with mVia. Before we can finish "
                    f"reviewing your application, we have a couple of follow-up questions:\n\n"
                    f"{note}\n\n"
                    f"Just reply to this email (or write to info@mvia.in) with your answers, "
                    f"and we'll pick up the review from there.\n\n— The mVia team"
                ),
            )
            AdminAuditLog.record(
                actor=request.user, action="mentor_application.more_info_requested",
                target=target, reason=note)
            messages.success(request, f"Follow-up email sent to {application.name}.")
            return redirect("staff:mentor_application_review", application_id=application.id)

    categories = _mark_expansion(_interest_categories(), selected_ids)
    return render(request, "profiles/staff_mentor_application_review.html", {
        "application": application, "approval_form": approval_form,
        "categories": categories, "selected_ids": selected_ids,
        "active_nav": "mentor_applications",
    })
