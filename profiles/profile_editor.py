"""
Staff-side rich profile editor for mentors.

Three fixed sections give every profile a uniform, modern structure:
  1. About the Mentor  -> MentorProfile.bio (plus headline, photo, links)
  2. Core Industry Expertise -> ProfilePoint(category="expertise")
  3. Mentorship Focus Areas   -> ProfilePoint(category="focus")
Each expertise/focus point is a title + description (like the sample doc).
"""

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import render, redirect, get_object_or_404

from .models import MentorProfile, ProfilePoint


def staff_required(view):
    return user_passes_test(lambda u: u.is_authenticated and u.is_staff, login_url="login")(view)


class MentorRichForm(forms.ModelForm):
    class Meta:
        model = MentorProfile
        fields = [
            "headline", "photo", "photo_url", "bio",
            "current_role", "company", "years_experience",
            "hourly_rate", "gst_note", "linkedin_url", "website_url",
            "is_available",
        ]
        widgets = {
            "bio": forms.Textarea(attrs={"rows": 6}),
            "headline": forms.TextInput(attrs={"placeholder": "e.g. Technology & business leader · 34+ years"}),
        }
        labels = {"bio": "About the Mentor"}


@staff_required
def edit_mentor_profile(request, mentor_id):
    mentor = get_object_or_404(MentorProfile, pk=mentor_id)

    if request.method == "POST":
        action = request.POST.get("action", "save_profile")

        if action == "save_profile":
            form = MentorRichForm(request.POST, request.FILES, instance=mentor)
            if form.is_valid():
                form.save()
                messages.success(request, "Profile saved.")
                return redirect("staff:edit_mentor_profile", mentor_id=mentor.id)

        elif action == "add_point":
            category = request.POST.get("category")
            title = request.POST.get("title", "").strip()
            desc = request.POST.get("description", "").strip()
            if category in ("expertise", "focus") and title:
                last = mentor.points.filter(category=category).order_by("-order").first()
                ProfilePoint.objects.create(
                    mentor=mentor, category=category, title=title, description=desc,
                    order=(last.order + 1) if last else 0)
                messages.success(request, "Point added.")
            return redirect("staff:edit_mentor_profile", mentor_id=mentor.id)

        elif action == "delete_point":
            point = get_object_or_404(ProfilePoint, pk=request.POST.get("point_id"), mentor=mentor)
            point.delete()
            messages.success(request, "Point removed.")
            return redirect("staff:edit_mentor_profile", mentor_id=mentor.id)

    form = MentorRichForm(instance=mentor)
    return render(request, "profiles/staff_edit_profile.html", {
        "mentor": mentor, "form": form,
        "expertise_points": mentor.expertise_points,
        "focus_points": mentor.focus_points,
        "active_nav": "mentors",
    })
