"""
Staff-side rich profile editor for mentors.

Sections give every profile a uniform, modern structure:
  1. About the Mentor  -> MentorProfile.bio (plus headline, photo, links)
  2. Core Industry Expertise -> ProfilePoint(category="expertise")
  3. Mentorship Focus Areas   -> ProfilePoint(category="focus")
  4. Availability             -> AvailabilitySlot (admin adds/toggles slots on
                                 the mentor's behalf)
Each expertise/focus point is a title + description (like the sample doc).
"""

from datetime import datetime, timedelta

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from .models import MentorProfile, ProfilePoint
from .profile_validators import validate_bio, validate_linkedin_url, validate_website_url, validate_photo


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
            "bio": forms.Textarea(attrs={"rows": 6, "maxlength": "1500"}),
            "headline": forms.TextInput(attrs={"placeholder": "e.g. Technology & business leader · 34+ years"}),
        }
        labels = {"bio": "About the Mentor"}

    def clean_bio(self):
        return validate_bio(self.cleaned_data.get("bio", ""))

    def clean_linkedin_url(self):
        return validate_linkedin_url(self.cleaned_data.get("linkedin_url", ""))

    def clean_website_url(self):
        return validate_website_url(self.cleaned_data.get("website_url", ""))

    def clean_photo(self):
        return validate_photo(self.cleaned_data.get("photo"))

    def clean_years_experience(self):
        years = self.cleaned_data.get("years_experience")
        if years is not None and years > 60:
            raise forms.ValidationError("Please enter a realistic number of years (0-60).")
        return years


@staff_required
def edit_mentor_profile(request, mentor_id):
    from bookings.models import AvailabilitySlot

    mentor = get_object_or_404(MentorProfile, pk=mentor_id)

    if request.method == "POST":
        # Archived accounts are read-only sitewide in the staff console - the
        # form fields are visually disabled, but this is the actual
        # enforcement (defense in depth against a raw POST bypassing that).
        if mentor.user.is_archived:
            messages.error(request, "This account is archived. Unarchive it first to make changes.")
            return redirect("staff:edit_mentor_profile", mentor_id=mentor.id)

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

        elif action == "add_slot":
            # Admin adds a one-off slot on the mentor's behalf. Live immediately
            # (is_confirmed=True). End time is auto-computed from the configured
            # session length, matching how mentor-generated slots work.
            date_str = request.POST.get("slot_date", "").strip()
            time_str = request.POST.get("slot_time", "").strip()
            session_len = getattr(settings, "SESSION_LENGTH_MINUTES", 60)
            try:
                naive_start = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
                start_dt = timezone.make_aware(naive_start, timezone.get_current_timezone())
            except (ValueError, TypeError):
                messages.error(request, "Please enter a valid date and time.")
                return redirect("staff:edit_mentor_profile", mentor_id=mentor.id)

            if start_dt <= timezone.now():
                messages.error(request, "That time is in the past — pick a future slot.")
                return redirect("staff:edit_mentor_profile", mentor_id=mentor.id)

            end_dt = start_dt + timedelta(minutes=session_len)
            slot, created = AvailabilitySlot.objects.get_or_create(
                mentor=mentor.user, start=start_dt,
                defaults={"end": end_dt, "is_confirmed": True})
            if created:
                messages.success(request, f"Slot added for {timezone.localtime(start_dt):%d %b %Y %H:%M}.")
            else:
                # A slot at this exact start already exists (unique constraint).
                if not slot.is_confirmed:
                    slot.is_confirmed = True
                    slot.save(update_fields=["is_confirmed"])
                    messages.success(request, "That slot already existed — marked it available.")
                else:
                    messages.info(request, "A slot already exists at that time.")
            return redirect("staff:edit_mentor_profile", mentor_id=mentor.id)

        elif action == "toggle_slot":
            # Flip a slot between available (is_confirmed=True) and unavailable
            # (False). Booked slots are protected — never toggle one off from
            # under an active booking.
            slot = get_object_or_404(AvailabilitySlot, pk=request.POST.get("slot_id"), mentor=mentor.user)
            if slot.is_taken:
                messages.error(request, "That slot is booked — cancel the booking first if you need to free it.")
            else:
                slot.is_confirmed = not slot.is_confirmed
                slot.save(update_fields=["is_confirmed"])
                messages.success(
                    request,
                    "Slot marked available." if slot.is_confirmed else "Slot marked unavailable.")
            return redirect("staff:edit_mentor_profile", mentor_id=mentor.id)

    from bookings.services import active_bookings_for_user

    form = MentorRichForm(instance=mentor)
    if mentor.user.is_archived:
        for field in form.fields.values():
            field.disabled = True
    active_bookings = None if mentor.user.is_archived else active_bookings_for_user(mentor.user)

    # Upcoming slots for the availability section (future only, soonest first).
    upcoming_slots = AvailabilitySlot.objects.filter(
        mentor=mentor.user, start__gt=timezone.now()).order_by("start")

    return render(request, "profiles/staff_edit_profile.html", {
        "mentor": mentor, "form": form,
        "expertise_points": mentor.expertise_points,
        "focus_points": mentor.focus_points,
        "upcoming_slots": upcoming_slots,
        "active_nav": "mentors",
        "target": mentor.user,
        "active_bookings": active_bookings,
    })
