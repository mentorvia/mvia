"""Member-facing profile and mentor-application views."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.shortcuts import render, redirect

from .models import MenteeProfile, MentorProfile
from .forms import MenteeProfileForm, MentorApplicationForm
from interests.models import Interest, MenteeInterest, MentorInterest


def _get_or_create_mentee_profile(user):
    profile, _ = MenteeProfile.objects.get_or_create(user=user)
    return profile


def _interest_tree():
    """Approved interests as a (category, [descendants]) structure for selection UIs."""
    approved = list(Interest.objects.filter(is_approved=True).order_by("name"))
    by_parent = {}
    for i in approved:
        by_parent.setdefault(i.parent_id, []).append(i)

    def flatten(parent_id, depth=0):
        rows = []
        for node in by_parent.get(parent_id, []):
            rows.append({"node": node, "depth": depth})
            rows.extend(flatten(node.id, depth + 1))
        return rows

    return flatten(None)


@login_required
def mentee_profile(request):
    profile = _get_or_create_mentee_profile(request.user)
    interest_rows = _interest_tree()
    selected_ids = set(request.user.mentee_interests.values_list("interest_id", flat=True))

    if request.method == "POST":
        form = MenteeProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            # Update interest selections.
            chosen = set(int(x) for x in request.POST.getlist("interests"))
            MenteeInterest.objects.filter(user=request.user).exclude(interest_id__in=chosen).delete()
            for iid in chosen:
                MenteeInterest.objects.get_or_create(user=request.user, interest_id=iid)

            # Handle an optional custom interest typed by the user.
            custom = request.POST.get("custom_interest", "").strip()
            if custom:
                obj, created = Interest.objects.get_or_create(
                    name=custom, parent=None,
                    defaults={"is_custom": True, "is_approved": False, "submitted_by": request.user},
                )
                MenteeInterest.objects.get_or_create(user=request.user, interest=obj)
                if created:
                    messages.info(request, f"“{custom}” was submitted for admin review and added to your interests.")

            messages.success(request, "Profile saved.")
            return redirect("mentee_profile")
    else:
        form = MenteeProfileForm(instance=profile)

    return render(request, "profiles/mentee_profile.html", {
        "form": form, "interest_rows": interest_rows,
        "selected_ids": selected_ids, "profile": profile,
    })


@login_required
def become_mentor(request):
    # Already a mentor or already applied?
    existing = MentorProfile.objects.filter(user=request.user).first()
    if existing:
        return render(request, "profiles/mentor_status.html", {"mentor": existing})

    interest_rows = _interest_tree()

    if request.method == "POST":
        form = MentorApplicationForm(request.POST)
        chosen = set(int(x) for x in request.POST.getlist("interests"))
        if form.is_valid() and not chosen:
            form.add_error(None, "Select at least one specialization.")
        if form.is_valid() and chosen:
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
        "form": form, "interest_rows": interest_rows,
    })
