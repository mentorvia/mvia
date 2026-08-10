"""
Member-facing mentor profile editor (/profile/mentor/edit/).

Pattern C: identity fields (full name, industry, years of experience,
credentials, current role & company) are locked. A mentor can only propose
changes to them, staged in MentorProfile.pending_identity_changes until an
admin approves — the live fields (and therefore the public profile) are
untouched until then. Everything else on this page saves immediately.

Mirrors the staff editor's (profiles/profile_editor.py) POST-action dispatch
pattern: each section is its own <form> posting a distinct `action`, and each
action is handled by a form/branch that only ever touches its own section's
fields — so a tampered POST to a freely-editable action can never reach the
locked identity fields.
"""

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from .models import MentorProfile, ProfilePoint
from .views import _interest_categories, _mark_expansion
from interests.models import MentorInterest
from auditlog.models import AdminAuditLog


def mentor_required(view):
    """Only approved mentors may reach this page; everyone else goes to become_mentor
    (which already shows the application form, or a pending/rejected status page)."""
    @login_required
    def wrapper(request, *args, **kwargs):
        profile = MentorProfile.objects.filter(user=request.user).first()
        if not profile or profile.status != MentorProfile.STATUS_APPROVED:
            messages.error(request, "You need an approved mentor profile to edit it.")
            return redirect("become_mentor")
        return view(request, *args, **kwargs)
    return wrapper


class IdentityRequestForm(forms.Form):
    full_name = forms.CharField(max_length=150, label="Full name")
    industry = forms.CharField(max_length=120, required=False)
    years_experience = forms.IntegerField(min_value=0, label="Years of experience")
    credentials = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"rows": 3}),
        help_text="Certifications, degrees, or other credentials.")
    current_role = forms.CharField(max_length=120, label="Current role")
    company = forms.CharField(max_length=120, label="Current company")
    message = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"rows": 2}),
        label="Note to admin (optional)")


class PresentationForm(forms.ModelForm):
    class Meta:
        model = MentorProfile
        fields = ["photo", "headline", "bio"]
        widgets = {
            "bio": forms.Textarea(attrs={"rows": 6}),
            "headline": forms.TextInput(attrs={"placeholder": "e.g. Technology & business leader · 34+ years"}),
        }
        labels = {"bio": "Bio"}


class ContactForm(forms.ModelForm):
    class Meta:
        model = MentorProfile
        fields = ["linkedin_url", "website_url"]


class SessionForm(forms.ModelForm):
    class Meta:
        model = MentorProfile
        fields = ["hourly_rate", "availability_note"]
        widgets = {
            "availability_note": forms.TextInput(attrs={"placeholder": "e.g. Weekday evenings, IST"}),
        }
        labels = {"hourly_rate": "Price per session (₹)"}

    def clean_hourly_rate(self):
        rate = self.cleaned_data["hourly_rate"]
        if rate is not None and rate < 0:
            raise forms.ValidationError("Price can't be negative.")
        return rate


IDENTITY_JSON_FIELDS = (
    "full_name", "industry", "years_experience", "credentials", "current_role", "company",
)


@mentor_required
def mentor_profile_edit(request):
    profile = request.user.mentor_profile

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "request_review":
            form = IdentityRequestForm(request.POST)
            if form.is_valid():
                cd = form.cleaned_data
                note = cd.get("message", "").strip()
                profile.pending_identity_changes = {
                    "full_name": cd["full_name"].strip(),
                    "industry": cd["industry"].strip(),
                    "years_experience": cd["years_experience"],
                    "credentials": cd["credentials"].strip(),
                    "current_role": cd["current_role"].strip(),
                    "company": cd["company"].strip(),
                }
                profile.pending_review_requested_at = timezone.now()
                profile.save(update_fields=["pending_identity_changes", "pending_review_requested_at"])
                AdminAuditLog.record(
                    actor=request.user, action="mentor.identity_change_requested",
                    target=f"{request.user.full_name} <{request.user.email}>", reason=note)
                messages.success(
                    request,
                    "Your changes are under review. Your public profile stays visible "
                    "with previous values until approved.")
            else:
                messages.error(request, "Please fix the errors below.")
                return _render(request, profile, identity_form=form, reveal_identity=True)
            return redirect("mentor_profile_edit")

        elif action == "cancel_pending_review":
            profile.pending_identity_changes = None
            profile.pending_review_requested_at = None
            profile.save(update_fields=["pending_identity_changes", "pending_review_requested_at"])
            messages.success(request, "Pending review request cancelled.")
            return redirect("mentor_profile_edit")

        elif action == "save_presentation":
            pform = PresentationForm(request.POST, request.FILES, instance=profile)
            chosen = set(int(x) for x in request.POST.getlist("interests"))
            if pform.is_valid():
                pform.save()
                MentorInterest.objects.filter(user=request.user).exclude(interest_id__in=chosen).delete()
                for iid in chosen:
                    MentorInterest.objects.get_or_create(user=request.user, interest_id=iid)
                messages.success(request, "Profile updated.")
                return redirect("mentor_profile_edit")
            messages.error(request, "Please fix the errors below.")
            return _render(request, profile, presentation_form=pform)

        elif action == "save_contact":
            cform = ContactForm(request.POST, instance=profile)
            if cform.is_valid():
                cform.save()
                messages.success(request, "Contact details updated.")
                return redirect("mentor_profile_edit")
            messages.error(request, "Please fix the errors below.")
            return _render(request, profile, contact_form=cform)

        elif action == "save_session":
            sform = SessionForm(request.POST, instance=profile)
            if sform.is_valid():
                sform.save()
                messages.success(request, "Session settings updated.")
                return redirect("mentor_profile_edit")
            messages.error(request, "Please fix the errors below.")
            return _render(request, profile, session_form=sform)

        elif action == "add_point":
            title = request.POST.get("title", "").strip()
            description = request.POST.get("description", "").strip()
            if title:
                last = profile.points.filter(
                    category=ProfilePoint.CATEGORY_EXPERTISE).order_by("-order").first()
                ProfilePoint.objects.create(
                    mentor=profile, category=ProfilePoint.CATEGORY_EXPERTISE,
                    title=title, description=description, order=(last.order + 1) if last else 0)
                messages.success(request, "Point added.")
            return redirect("mentor_profile_edit")

        elif action == "edit_point":
            point = get_object_or_404(
                ProfilePoint, pk=request.POST.get("point_id"),
                mentor=profile, category=ProfilePoint.CATEGORY_EXPERTISE)
            title = request.POST.get("title", "").strip()
            if title:
                point.title = title
                point.description = request.POST.get("description", "").strip()
                point.save(update_fields=["title", "description"])
                messages.success(request, "Point updated.")
            return redirect("mentor_profile_edit")

        elif action == "delete_point":
            point = get_object_or_404(
                ProfilePoint, pk=request.POST.get("point_id"),
                mentor=profile, category=ProfilePoint.CATEGORY_EXPERTISE)
            point.delete()
            messages.success(request, "Point removed.")
            return redirect("mentor_profile_edit")

        elif action == "move_point":
            point = get_object_or_404(
                ProfilePoint, pk=request.POST.get("point_id"),
                mentor=profile, category=ProfilePoint.CATEGORY_EXPERTISE)
            siblings = list(
                profile.points.filter(category=ProfilePoint.CATEGORY_EXPERTISE).order_by("order", "id"))
            idx = next(i for i, p in enumerate(siblings) if p.id == point.id)
            swap_idx = idx - 1 if request.POST.get("direction") == "up" else idx + 1
            if 0 <= swap_idx < len(siblings):
                other = siblings[swap_idx]
                point.order, other.order = other.order, point.order
                point.save(update_fields=["order"])
                other.save(update_fields=["order"])
            return redirect("mentor_profile_edit")

        return redirect("mentor_profile_edit")

    return _render(request, profile)


def _render(request, profile, identity_form=None, presentation_form=None,
            contact_form=None, session_form=None, reveal_identity=False):
    if identity_form is None:
        identity_form = IdentityRequestForm(initial={
            "full_name": request.user.full_name,
            "industry": profile.industry,
            "years_experience": profile.years_experience,
            "credentials": profile.credentials,
            "current_role": profile.current_role,
            "company": profile.company,
        })
    if presentation_form is None:
        presentation_form = PresentationForm(instance=profile)
    if contact_form is None:
        contact_form = ContactForm(instance=profile)
    if session_form is None:
        session_form = SessionForm(instance=profile)

    return render(request, "profiles/mentor_profile_edit.html", {
        "profile": profile,
        "identity_form": identity_form,
        "presentation_form": presentation_form,
        "contact_form": contact_form,
        "session_form": session_form,
        "reveal_identity": reveal_identity,
        "categories": _mark_expansion(
            _interest_categories(),
            set(request.user.mentor_interests.values_list("interest_id", flat=True)),
        ),
        "selected_ids": set(request.user.mentor_interests.values_list("interest_id", flat=True)),
        "expertise_points": profile.points.filter(category=ProfilePoint.CATEGORY_EXPERTISE),
    })
