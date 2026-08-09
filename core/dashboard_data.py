"""
Data-fetching helpers for the member-facing dashboard (core.views.dashboard).

Kept separate from core/views.py so the router view itself stays thin. Two
entry points: mentee_context(user) and mentor_context(user).
"""

from datetime import datetime, timedelta
from decimal import Decimal

from django.db.models import Max, Sum
from django.utils import timezone

from bookings.models import AvailabilitySlot, Booking
from interests.models import MentorInterest
from payments.models import LedgerEntry, Payout
from profiles.models import MentorProfile, ProfilePoint

UPCOMING_STATUSES = [
    Booking.STATUS_PENDING_PAYMENT, Booking.STATUS_AWAITING_APPROVAL, Booking.STATUS_CONFIRMED,
]
PAST_STATUSES = [
    Booking.STATUS_COMPLETED, Booking.STATUS_CANCELLED, Booking.STATUS_DECLINED,
    Booking.STATUS_EXPIRED, Booking.STATUS_NO_SHOW,
]

JOIN_WINDOW_MINUTES = 15


def resolve_active_role(user, session):
    """
    Which role's dashboard to show. A single-role user always sees their one
    role. A dual-role user sees whatever they last explicitly toggled to
    (stored in session, set by core.views.set_dashboard_role); if they've
    never toggled, default to whichever side has more recent booking
    activity — ties (including no activity at all yet) go to mentor, since
    pending requests are time-sensitive.
    """
    if user.is_mentee and not user.is_mentor:
        return "mentee"
    if user.is_mentor and not user.is_mentee:
        return "mentor"

    stored = session.get("dashboard_role")
    if stored in ("mentee", "mentor"):
        return stored

    mentee_latest = Booking.objects.filter(mentee=user).aggregate(m=Max("updated_at"))["m"]
    mentor_latest = Booking.objects.filter(mentor=user).aggregate(m=Max("updated_at"))["m"]
    if mentee_latest and (not mentor_latest or mentee_latest > mentor_latest):
        return "mentee"
    return "mentor"


def _joinable(booking, now):
    """True once a confirmed session has a link and is within the join window."""
    if not booking or not booking.meet_link:
        return False
    return booking.slot.start - timedelta(minutes=JOIN_WINDOW_MINUTES) <= now < booking.slot.end


def mentee_context(user):
    now = timezone.now()

    next_session = (
        Booking.objects.filter(mentee=user, status=Booking.STATUS_CONFIRMED, slot__start__gt=now)
        .select_related("mentor", "mentor__mentor_profile", "slot")
        .order_by("slot__start")
        .first()
    )

    next_pending = None
    if not next_session:
        next_pending = (
            Booking.objects.filter(mentee=user, status=Booking.STATUS_AWAITING_APPROVAL)
            .select_related("mentor", "slot")
            .order_by("approval_due_at")
            .first()
        )
        if next_pending and next_pending.approval_due_at:
            remaining = next_pending.approval_due_at - now
            next_pending.hours_remaining = max(0, int(remaining.total_seconds() // 3600))

    bookings_upcoming = list(
        Booking.objects.filter(mentee=user, status__in=UPCOMING_STATUSES)
        .select_related("mentor", "slot")
        .order_by("slot__start")
    )
    bookings_past = list(
        Booking.objects.filter(mentee=user, status__in=PAST_STATUSES)
        .select_related("mentor", "slot")
        .order_by("-slot__start")
    )
    bookings_all = sorted(bookings_upcoming + bookings_past, key=lambda b: b.created_at, reverse=True)

    # Recommended mentors: interest overlap with the mentee's selected interests.
    # Self-contained (not imported from directory.views) so this dashboard
    # doesn't depend on that app's internals.
    my_interest_ids = set(user.mentee_interests.values_list("interest_id", flat=True))
    mentors = list(
        MentorProfile.objects.filter(status=MentorProfile.STATUS_APPROVED, is_available=True)
        .exclude(user=user)
        .select_related("user")
    )
    spec_map = {}
    if mentors:
        for mi in MentorInterest.objects.filter(
                user__in=[m.user_id for m in mentors]).select_related("interest"):
            spec_map.setdefault(mi.user_id, []).append(mi.interest)
    cards = []
    for m in mentors:
        specs = spec_map.get(m.user_id, [])
        overlap = len({s.id for s in specs} & my_interest_ids)
        cards.append({"mentor": m, "specs": specs, "overlap": overlap})
    cards.sort(key=lambda c: (-c["overlap"], c["mentor"].user.full_name))
    recommended = cards[:4]

    # Profile-completion checklist. Note: the brief's "Timezone set" item is
    # dropped here — User.timezone defaults to a non-blank "Asia/Kolkata" and
    # is auto-detected silently in the background (core.views.set_timezone),
    # so there's no reliable signal for "the mentee actually set this," and a
    # default-vs-explicit heuristic would be wrong for most Indian users.
    profile = getattr(user, "mentee_profile", None)
    missing = profile.missing_fields() if profile else ["current role", "career goals", "at least one interest"]
    checklist = [
        {"label": "Current role & career goals", "done": not ({"current role", "career goals"} & set(missing))},
        {"label": "Interests selected", "done": "at least one interest" not in missing},
        {"label": "LinkedIn added", "done": bool(profile and profile.linkedin_url)},
        {"label": "Instagram added", "done": bool(profile and profile.instagram_url)},
        {"label": "Behance added", "done": bool(profile and profile.behance_url)},
    ]
    profile_incomplete = any(not item["done"] for item in checklist)

    return {
        "now": now,
        "next_session": next_session,
        "next_pending": next_pending,
        "can_join_next_session": _joinable(next_session, now),
        "bookings_upcoming": bookings_upcoming,
        "bookings_past": bookings_past,
        "bookings_all": bookings_all,
        "recommended": recommended,
        "profile_checklist": checklist,
        "profile_incomplete": profile_incomplete,
    }


def mentor_context(user):
    now = timezone.now()

    pending_requests = list(
        Booking.objects.filter(mentor=user, status=Booking.STATUS_AWAITING_APPROVAL)
        .select_related("mentee", "slot")
        .order_by("approval_due_at")
    )
    for b in pending_requests:
        remaining = (b.approval_due_at - now) if b.approval_due_at else timedelta(0)
        b.hours_remaining = max(0, int(remaining.total_seconds() // 3600))
        # Urgency bands against the real 48h approval window (services.confirm_payment).
        if b.hours_remaining <= 6:
            b.urgency = "critical"
        elif b.hours_remaining <= 24:
            b.urgency = "high"
        else:
            b.urgency = "normal"

    next_session = (
        Booking.objects.filter(mentor=user, status=Booking.STATUS_CONFIRMED, slot__start__gt=now)
        .select_related("mentee", "slot")
        .order_by("slot__start")
        .first()
    )

    sessions_upcoming = list(
        Booking.objects.filter(mentor=user, status__in=UPCOMING_STATUSES)
        .select_related("mentee", "slot")
        .order_by("slot__start")
    )
    sessions_past = list(
        Booking.objects.filter(mentor=user, status__in=PAST_STATUSES)
        .select_related("mentee", "slot")
        .order_by("-slot__start")
    )
    sessions_all = sorted(sessions_upcoming + sessions_past, key=lambda b: b.created_at, reverse=True)

    # This week's (Mon-Sun) declared slots, for the availability preview.
    today = timezone.localdate()
    tz = timezone.get_current_timezone()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=7)
    week_start_dt = timezone.make_aware(datetime.combine(week_start, datetime.min.time()), tz)
    week_end_dt = timezone.make_aware(datetime.combine(week_end, datetime.min.time()), tz)
    week_slots = list(
        AvailabilitySlot.objects.filter(mentor=user, start__gte=week_start_dt, start__lt=week_end_dt)
        .order_by("start")
    )

    # Earnings: this calendar month's mentor-earning ledger entries.
    month_start_dt = timezone.make_aware(datetime.combine(today.replace(day=1), datetime.min.time()), tz)
    earnings_this_month = (
        LedgerEntry.objects.filter(
            booking__mentor=user, entry_type=LedgerEntry.TYPE_MENTOR_EARNING,
            created_at__gte=month_start_dt,
        ).aggregate(s=Sum("amount"))["s"] or Decimal("0")
    )
    pending_payout = (
        LedgerEntry.objects.filter(
            booking__mentor=user, entry_type=LedgerEntry.TYPE_MENTOR_EARNING, payout__isnull=True,
        ).aggregate(s=Sum("amount"))["s"] or Decimal("0")
    )
    last_payout = Payout.objects.filter(mentor=user).order_by("-created_at").first()

    mentor_profile = getattr(user, "mentor_profile", None)
    profile_status = None
    if mentor_profile:
        if mentor_profile.status == MentorProfile.STATUS_PENDING:
            profile_status = {"kind": "pending", "message": "Your mentor application is awaiting admin review."}
        elif mentor_profile.status == MentorProfile.STATUS_REJECTED:
            profile_status = {
                "kind": "rejected",
                "message": mentor_profile.rejection_reason or "Your application wasn't approved.",
            }
        else:
            nudges = []
            if not mentor_profile.headline:
                nudges.append("a headline")
            if not mentor_profile.display_photo:
                nudges.append("a photo")
            if not mentor_profile.points.exists():
                nudges.append("expertise/focus points")
            if nudges:
                profile_status = {
                    "kind": "nudge",
                    "message": "Add " + ", ".join(nudges) + " to stand out in the directory.",
                }

    # First-login welcome banner: a stricter, more prominent check than the
    # sidebar nudge above. Shows only for an already-approved mentor whose
    # profile is missing something a mentee would actually need to decide
    # whether to book them. Disappears once all four are present, at which
    # point the sidebar nudge (looser criteria, always-on) takes back over.
    needs_welcome_banner = False
    if mentor_profile and mentor_profile.status == MentorProfile.STATUS_APPROVED:
        has_bio = bool(mentor_profile.bio and mentor_profile.bio.strip())
        has_specializations = user.mentor_interests.exists()
        has_photo = bool(mentor_profile.display_photo)
        has_enough_points = mentor_profile.points.filter(
            category=ProfilePoint.CATEGORY_EXPERTISE).count() >= 2
        needs_welcome_banner = not (has_bio and has_specializations and has_photo and has_enough_points)

    return {
        "now": now,
        "pending_requests": pending_requests,
        "pending_count": len(pending_requests),
        "next_session": next_session,
        "can_join_next_session": _joinable(next_session, now),
        "sessions_upcoming": sessions_upcoming,
        "sessions_past": sessions_past,
        "sessions_all": sessions_all,
        "week_slots": week_slots,
        "earnings_this_month": earnings_this_month,
        "pending_payout": pending_payout,
        "last_payout": last_payout,
        "mentor_profile": mentor_profile,
        "profile_status": profile_status,
        "needs_welcome_banner": needs_welcome_banner,
    }
