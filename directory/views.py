"""
Mentor directory (requirement 4.5).

Public-ish discovery of APPROVED, AVAILABLE mentors with:
- keyword search (name, role, company, bio)
- filter by interest
- filter by max rate
- recommendations: if the viewer is a logged-in mentee with interests,
  mentors sharing those interests are surfaced and marked "Recommended".
Plus an individual public mentor profile page.
"""

from django.db.models import Q, Count
from django.shortcuts import render, get_object_or_404

from accounts.models import User
from profiles.models import MentorProfile
from interests.models import Interest, MentorInterest


def directory(request):
    mentors = MentorProfile.objects.filter(
        status=MentorProfile.STATUS_APPROVED, is_available=True
    ).select_related("user")

    query = request.GET.get("q", "").strip()
    interest_id = request.GET.get("interest", "").strip()
    max_rate = request.GET.get("max_rate", "").strip()

    if query:
        mentors = mentors.filter(
            Q(user__full_name__icontains=query) |
            Q(current_role__icontains=query) |
            Q(company__icontains=query) |
            Q(bio__icontains=query)
        )

    if interest_id:
        mentor_user_ids = MentorInterest.objects.filter(
            interest_id=interest_id).values_list("user_id", flat=True)
        mentors = mentors.filter(user_id__in=mentor_user_ids)

    if max_rate:
        try:
            mentors = mentors.filter(hourly_rate__lte=float(max_rate))
        except ValueError:
            pass

    mentors = list(mentors.order_by("user__full_name"))

    # Attach each mentor's specializations for display.
    spec_map = {}
    for mi in MentorInterest.objects.filter(
            user__in=[m.user_id for m in mentors]).select_related("interest"):
        spec_map.setdefault(mi.user_id, []).append(mi.interest)

    # Recommendations: interests shared with the logged-in mentee viewer.
    my_interest_ids = set()
    if request.user.is_authenticated:
        my_interest_ids = set(
            request.user.mentee_interests.values_list("interest_id", flat=True))

    mentor_cards = []
    for m in mentors:
        specs = spec_map.get(m.user_id, [])
        spec_ids = {s.id for s in specs}
        overlap = len(spec_ids & my_interest_ids)
        mentor_cards.append({
            "mentor": m, "specs": specs, "overlap": overlap,
            "recommended": overlap > 0,
        })

    # Sort recommended first (by overlap), then alphabetical.
    mentor_cards.sort(key=lambda c: (-c["overlap"], c["mentor"].user.full_name))

    # Interests that actually have at least one approved mentor (for the filter).
    interests_with_mentors = Interest.objects.filter(
        mentor_links__user__mentor_profile__status=MentorProfile.STATUS_APPROVED
    ).distinct().order_by("name")

    return render(request, "directory/directory.html", {
        "mentor_cards": mentor_cards,
        "query": query,
        "interest_id": interest_id,
        "max_rate": max_rate,
        "interests": interests_with_mentors,
        "has_recommendations": any(c["recommended"] for c in mentor_cards),
    })


def mentor_profile(request, user_id):
    user = get_object_or_404(User, pk=user_id, is_mentor=True)
    mentor = get_object_or_404(
        MentorProfile, user=user, status=MentorProfile.STATUS_APPROVED)
    specs = [mi.interest for mi in
             MentorInterest.objects.filter(user=user).select_related("interest")]
    return render(request, "directory/mentor_profile.html", {
        "mentor": mentor, "mentor_user": user, "specs": specs,
    })
