"""Member-facing profile and mentor-application views."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.shortcuts import render, redirect

from .models import MenteeProfile, MentorProfile, MentorApplication
from .forms import MenteeProfileForm, MentorApplicationForm, MentorApplicationPublicForm
from interests.models import Interest, MenteeInterest, MentorInterest


def _get_or_create_mentee_profile(user):
    profile, _ = MenteeProfile.objects.get_or_create(user=user)
    return profile


def _interest_categories():
    """
    Top-level Interest categories for the picker (category cards + optional
    deep-dive expansion). Each entry carries every descendant flattened to a
    single list (any depth - nothing is unreachable, it just moves into the
    "expand" panel), and a live count of approved, available mentors linked
    to the category itself or any of its descendants.
    """
    approved = list(Interest.objects.filter(is_approved=True).order_by("name"))
    by_parent = {}
    for i in approved:
        by_parent.setdefault(i.parent_id, []).append(i)

    def flatten(parent_id):
        rows = []
        for node in by_parent.get(parent_id, []):
            rows.append(node)
            rows.extend(flatten(node.id))
        return rows

    categories = []
    for cat in by_parent.get(None, []):
        descendants = flatten(cat.id)
        all_ids = [cat.id] + [d.id for d in descendants]
        mentor_count = MentorProfile.objects.filter(
            status=MentorProfile.STATUS_APPROVED, is_available=True, user__archived_at__isnull=True,
            user__mentor_interests__interest_id__in=all_ids,
        ).distinct().count()
        categories.append({
            "category": cat, "descendants": descendants, "mentor_count": mentor_count,
        })
    categories.sort(key=lambda entry: entry["category"].name.lower())
    return categories


def _mark_expansion(categories, selected_ids):
    """
    Auto-expand any category card whose subtree already has a selection, so a
    pre-filled sub-interest choice (e.g. a mentor who picked "Machine
    Learning" without ever checking the "Tech" category box) is never hidden
    inside a collapsed panel on an edit page.
    """
    for entry in categories:
        all_ids = {entry["category"].id} | {d.id for d in entry["descendants"]}
        entry["initially_expanded"] = bool(all_ids & selected_ids)
    return categories


@login_required
def mentee_profile(request):
    profile = _get_or_create_mentee_profile(request.user)
    selected_ids = set(request.user.mentee_interests.values_list("interest_id", flat=True))
    categories = _mark_expansion(_interest_categories(), selected_ids)

    if request.method == "POST":
        form = MenteeProfileForm(request.POST, instance=profile)
        chosen = set(int(x) for x in request.POST.getlist("interests"))
        custom = request.POST.get("custom_interest", "").strip()

        # MYPRO-023: a complete profile needs at least one interest. Block the
        # save (rather than silently saving an incomplete profile) when nothing
        # is selected and no custom interest was typed.
        has_any_interest = bool(chosen) or bool(custom)

        if form.is_valid() and not has_any_interest:
            messages.error(request, "Please select at least one interest before saving.")
        elif form.is_valid():
            form.save()
            # Update interest selections.
            MenteeInterest.objects.filter(user=request.user).exclude(interest_id__in=chosen).delete()
            for iid in chosen:
                MenteeInterest.objects.get_or_create(user=request.user, interest_id=iid)

            # Handle an optional custom interest typed by the user.
            if custom:
                obj, created = Interest.objects.get_or_create(
                    name=custom, parent=None,
                    defaults={"is_custom": True, "is_approved": False, "submitted_by": request.user},
                )
                MenteeInterest.objects.get_or_create(user=request.user, interest=obj)
                if created:
                    messages.info(request, f'"{custom}" was submitted for admin review and added to your interests.')

            messages.success(request, "Profile saved.")
            # MYPRO-037: after a successful save, return the user to the dashboard.
            return redirect("dashboard")
        # Re-render the picker with the just-submitted selections on error.
        categories = _mark_expansion(_interest_categories(), chosen or selected_ids)
        selected_ids = chosen or selected_ids
    else:
        form = MenteeProfileForm(instance=profile)

    return render(request, "profiles/mentee_profile.html", {
        "form": form, "categories": categories,
        "selected_ids": selected_ids, "profile": profile,
    })


@login_required
def become_mentor(request):
    # Already a mentor or already applied?
    existing = MentorProfile.objects.filter(user=request.user).first()
    if existing:
        return render(request, "profiles/mentor_status.html", {"mentor": existing})

    categories = _interest_categories()

    if request.method == "POST":
        form = MentorApplicationForm(request.POST)
        chosen = set(int(x) for x in request.POST.getlist("interests"))
        if form.is_valid():
            mentor = form.save(commit=False)
            mentor.user = request.user
            mentor.status = MentorProfile.STATUS_PENDING
            mentor.save()
            for iid in chosen:
                MentorInterest.objects.get_or_create(user=request.user, interest_id=iid)
            messages.success(request, "Your mentor application is submitted and pending review.")
            return redirect("become_mentor")
    else:
        form = MentorApplicationForm()

    return render(request, "profiles/mentor_apply.html", {
        "form": form, "categories": categories, "selected_ids": set(),
    })


# ---------- Public, pre-account mentor application (/become-a-mentor/) ----------

def mentor_application_apply(request):
    """
    The public application form - no login required, doesn't touch the User
    model at all. See MentorApplication's docstring for how this differs from
    become_mentor above.
    """
    if request.method == "POST":
        # Honeypot: a field real visitors never see or fill (hidden via CSS in
        # the template), but a scripted bot filling every input will. Silently
        # redirect to the same "thanks" page as a genuine submission, rather
        # than surfacing a validation error - so the bot's script sees success
        # and doesn't get signal to adapt, while nothing is actually created.
        if request.POST.get("company_site", "").strip():
            return redirect("mentor_application_thanks")

        form = MentorApplicationPublicForm(request.POST)
        if form.is_valid():
            application = form.save()
            _send_application_received_emails(request, application)
            return redirect("mentor_application_thanks")
    else:
        form = MentorApplicationPublicForm()

    return render(request, "profiles/mentor_application_apply.html", {"form": form})


def _send_application_received_emails(request, application):
    from django.urls import reverse
    from accounts.emails import send_email
    from accounts.models import User

    send_email(
        to_email=application.email,
        subject="Application received - mVia",
        template_name="mentor_application_received",
        body=(
            f"Hi {application.name},\n\n"
            f"Thanks for applying to become a mentor at mVia. We've received your "
            f"application and typically respond within 5-7 business days.\n\n"
            f"- The mVia team"
        ),
    )

    review_url = request.build_absolute_uri(
        reverse("staff:mentor_application_review", args=[application.id]))
    for staff_email in User.objects.filter(is_staff=True).values_list("email", flat=True):
        send_email(
            to_email=staff_email,
            subject=f"New mentor application from {application.name}",
            template_name="mentor_application_admin_notify",
            body=(
                f"New mentor application from {application.name} <{application.email}>.\n\n"
                f"Review it here: {review_url}"
            ),
        )


def mentor_application_thanks(request):
    return render(request, "profiles/mentor_application_thanks.html")
