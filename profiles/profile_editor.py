"""
Staff-side rich profile editor for mentors.

One page to edit the mentor's headline, photo, about/bio, links, GST note, price,
and to manage flexible content sections (e.g. "Core Industry Expertise") each with
title+description items. Designed to be easy to update and to drive a modern
public profile page.
"""

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import render, redirect, get_object_or_404

from .models import MentorProfile, ProfileSection, ProfileSectionItem


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


@staff_required
def edit_mentor_profile(request, mentor_id):
    mentor = get_object_or_404(MentorProfile, pk=mentor_id)

    if request.method == "POST":
        action = request.POST.get("action", "save_profile")

        # --- Save the main profile fields ---
        if action == "save_profile":
            form = MentorRichForm(request.POST, request.FILES, instance=mentor)
            if form.is_valid():
                form.save()
                messages.success(request, "Profile updated.")
                return redirect("staff:edit_mentor_profile", mentor_id=mentor.id)

        # --- Add a new section ---
        elif action == "add_section":
            heading = request.POST.get("heading", "").strip()
            intro = request.POST.get("intro", "").strip()
            if heading:
                last = mentor.sections.order_by("-order").first()
                ProfileSection.objects.create(
                    mentor=mentor, heading=heading, intro=intro,
                    order=(last.order + 1) if last else 0)
                messages.success(request, f"Section “{heading}” added.")
            return redirect("staff:edit_mentor_profile", mentor_id=mentor.id)

        # --- Delete a section ---
        elif action == "delete_section":
            sec = get_object_or_404(ProfileSection, pk=request.POST.get("section_id"), mentor=mentor)
            sec.delete()
            messages.success(request, "Section removed.")
            return redirect("staff:edit_mentor_profile", mentor_id=mentor.id)

        # --- Add an item to a section ---
        elif action == "add_item":
            sec = get_object_or_404(ProfileSection, pk=request.POST.get("section_id"), mentor=mentor)
            title = request.POST.get("title", "").strip()
            desc = request.POST.get("description", "").strip()
            if title:
                last = sec.items.order_by("-order").first()
                ProfileSectionItem.objects.create(
                    section=sec, title=title, description=desc,
                    order=(last.order + 1) if last else 0)
                messages.success(request, "Point added.")
            return redirect("staff:edit_mentor_profile", mentor_id=mentor.id)

        # --- Delete an item ---
        elif action == "delete_item":
            item = get_object_or_404(ProfileSectionItem, pk=request.POST.get("item_id"),
                                     section__mentor=mentor)
            item.delete()
            messages.success(request, "Point removed.")
            return redirect("staff:edit_mentor_profile", mentor_id=mentor.id)

    form = MentorRichForm(instance=mentor)
    sections = mentor.sections.prefetch_related("items")
    return render(request, "profiles/staff_edit_profile.html", {
        "mentor": mentor, "form": form, "sections": sections, "active_nav": "mentors",
    })
