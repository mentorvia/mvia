"""
Booking service layer — the ONLY place booking state changes.

Centralizing transitions here (rather than scattering them across views) keeps
the state machine enforceable and the double-booking guard reliable. All slot
contention is handled inside DB transactions with row locking.
"""

from django.conf import settings
from django.db import transaction, IntegrityError
from django.utils import timezone

from .models import AvailabilitySlot, Booking
from payments.models import Payment


class BookingError(Exception):
    """Raised when a booking action isn't allowed (e.g. slot taken)."""


# Statuses where the booking is still "live" — someone owes an action, a
# payment is outstanding, or a session hasn't happened yet. Same partition
# core.dashboard_data uses for "upcoming" vs. "past" (UPCOMING_STATUSES /
# PAST_STATUSES) — kept as an independent constant here rather than importing
# from core, since bookings is a lower-level domain app and core sits above it.
ACTIVE_BOOKING_STATUSES = [
    Booking.STATUS_PENDING_PAYMENT, Booking.STATUS_AWAITING_APPROVAL, Booking.STATUS_CONFIRMED,
]


def active_bookings_for_user(user):
    """
    Bookings where this user — as mentor OR mentee — has an unresolved
    booking. Used to gate account archiving: a mentor or mentee with any
    active booking can't be archived until it's cancelled or resolved.
    """
    from django.db.models import Q
    return Booking.objects.filter(
        Q(mentor=user) | Q(mentee=user), status__in=ACTIVE_BOOKING_STATUSES,
    ).select_related("mentor", "mentee", "slot")


@transaction.atomic
def create_booking(*, mentee, slot_id):
    """
    Create a pending_payment booking for a slot, locking the slot row so two
    mentees can't grab it simultaneously. Returns the Booking.
    """
    # Lock the slot row for the duration of this transaction.
    slot = AvailabilitySlot.objects.select_for_update().select_related("mentor").get(pk=slot_id)

    if slot.is_past:
        raise BookingError("That time slot is in the past.")
    if slot.mentor_id == mentee.id:
        raise BookingError("You can't book your own slot.")
    if getattr(slot.mentor, "is_placeholder", False):
        raise BookingError("This mentor isn't accepting bookings yet.")
    if getattr(slot.mentor, "is_archived", False):
        raise BookingError("This mentor is no longer active on mVia.")
    if slot.is_taken:
        raise BookingError("Sorry, that slot was just booked by someone else.")

    # Mentor's current rate becomes the fixed amount for this booking.
    from profiles.models import MentorProfile
    mentor_profile = MentorProfile.objects.get(user=slot.mentor)
    amount = mentor_profile.hourly_rate

    booking = Booking.objects.create(
        mentee=mentee, mentor=slot.mentor, slot=slot,
        status=Booking.STATUS_PENDING_PAYMENT, amount=amount,
    )
    Payment.objects.create(
        booking=booking, amount=amount,
        is_simulated=not settings.RAZORPAY_ENABLED,
        status=Payment.STATUS_CREATED,
    )
    return booking


@transaction.atomic
def confirm_payment(*, booking_id, simulated=True, razorpay_payment_id="", razorpay_signature=""):
    """
    Mark a booking's payment successful. Money is captured now, but the booking
    moves to AWAITING_APPROVAL (not confirmed) — the mentor must approve within
    48 hours. Re-checks slot availability under lock. Returns the Booking.

    Note: notification email is sent by the caller AFTER this commits, so email
    problems can never roll back a payment. Use confirm_payment_and_notify for
    the combined behaviour.
    """
    from datetime import timedelta

    booking = Booking.objects.select_for_update().select_related("slot").get(pk=booking_id)

    if booking.status != Booking.STATUS_PENDING_PAYMENT:
        raise BookingError("This booking is no longer awaiting payment.")
    if not booking.can_transition_to(Booking.STATUS_AWAITING_APPROVAL):
        raise BookingError("This booking can't move to approval.")

    # Final guard: the slot is HELD while awaiting approval, so awaiting_approval
    # counts as taken too.
    clash = Booking.objects.filter(
        slot=booking.slot,
        status__in=[Booking.STATUS_AWAITING_APPROVAL, Booking.STATUS_CONFIRMED, Booking.STATUS_COMPLETED],
    ).exclude(pk=booking.pk).exists()
    if clash:
        raise BookingError("That slot was just taken by someone else.")

    payment = booking.payments.order_by("-created_at").first()
    if payment:
        payment.is_simulated = simulated
        payment.razorpay_payment_id = razorpay_payment_id
        payment.razorpay_signature = razorpay_signature
        payment.save(update_fields=["is_simulated", "razorpay_payment_id", "razorpay_signature"])
        payment.mark_paid()

    booking.status = Booking.STATUS_AWAITING_APPROVAL
    booking.approval_due_at = timezone.now() + timedelta(hours=48)
    try:
        booking.save(update_fields=["status", "approval_due_at"])
    except IntegrityError:
        raise BookingError("That slot was just taken by someone else.")

    # Write the money ledger entries now (payment captured).
    _write_booking_ledger(booking)
    return booking


def confirm_payment_and_notify(*, booking_id, simulated=True, razorpay_payment_id="", razorpay_signature=""):
    """confirm_payment + send the mentor the 'awaiting approval' email AFTER commit."""
    booking = confirm_payment(
        booking_id=booking_id, simulated=simulated,
        razorpay_payment_id=razorpay_payment_id, razorpay_signature=razorpay_signature)
    try:
        when = timezone.localtime(booking.slot.start).strftime("%d %b %Y at %I:%M %p")
        _notify(
            booking.mentor.email, "Action needed: approve your mVia session",
            (f"Hi {booking.mentor.get_short_name()},\n\n"
             f"{booking.mentee.full_name} has booked and paid for a session with you:\n\n"
             f"When: {when}\n\n"
             f"Please approve or decline within 48 hours in your mVia dashboard. "
             f"If you can't make it, you can suggest a new time.\n\n— mVia"),
            "booking_awaiting_approval", booking)
    except Exception:  # noqa: BLE001
        pass
    return booking


def _write_booking_ledger(booking):
    """
    Append the immutable money entries for a confirmed booking.
    mentor rate = booking.amount; platform fee = 20% added on top;
    mentee paid = rate + fee.
    """
    from payments.models import LedgerEntry
    from decimal import Decimal

    fee_rate = Decimal(str(getattr(settings, "PLATFORM_FEE_RATE", 0.20)))
    mentor_earning = booking.amount
    platform_fee = (mentor_earning * fee_rate).quantize(Decimal("0.01"))
    mentee_paid = mentor_earning + platform_fee

    LedgerEntry.objects.create(
        booking=booking, entry_type=LedgerEntry.TYPE_BOOKING_PAYMENT,
        amount=mentee_paid, note="Mentee payment received (booking confirmed).")
    LedgerEntry.objects.create(
        booking=booking, entry_type=LedgerEntry.TYPE_PLATFORM_FEE,
        amount=platform_fee, note="mVia platform fee.")
    LedgerEntry.objects.create(
        booking=booking, entry_type=LedgerEntry.TYPE_MENTOR_EARNING,
        amount=mentor_earning, note="Amount owed to mentor.")


@transaction.atomic
def cancel_booking(*, booking_id, actor, reason=""):
    booking = Booking.objects.select_for_update().get(pk=booking_id)
    if not booking.can_transition_to(Booking.STATUS_CANCELLED):
        raise BookingError("This booking can't be cancelled.")
    booking.status = Booking.STATUS_CANCELLED
    booking.cancelled_by = actor
    booking.cancellation_reason = reason
    booking.cancelled_at = timezone.now()
    booking.save(update_fields=["status", "cancelled_by", "cancellation_reason", "cancelled_at"])
    # NOTE: refund handling hooks in here in a later step.
    return booking


@transaction.atomic
def complete_booking(*, booking_id):
    booking = Booking.objects.select_for_update().get(pk=booking_id)
    if not booking.can_transition_to(Booking.STATUS_COMPLETED):
        raise BookingError("This booking can't be completed.")
    booking.status = Booking.STATUS_COMPLETED
    booking.completed_at = timezone.now()
    booking.save(update_fields=["status", "completed_at"])
    return booking


@transaction.atomic
def record_refund(*, booking_id, actor, reason, reference=""):
    """
    Record a refund for a paid booking. This does NOT move money — the ops team
    performs the actual refund in the Razorpay dashboard. This writes the refund
    to the ledger and marks the booking, with an optional Razorpay reference.

    Allowed only on confirmed or completed bookings (where money was collected).
    """
    from payments.models import LedgerEntry
    from decimal import Decimal

    booking = Booking.objects.select_for_update().get(pk=booking_id)

    if booking.status not in (Booking.STATUS_AWAITING_APPROVAL, Booking.STATUS_CONFIRMED, Booking.STATUS_COMPLETED):
        raise BookingError("Refunds apply only to paid bookings.")
    if booking.is_refunded:
        raise BookingError("This booking has already been refunded.")
    if not reason.strip():
        raise BookingError("A refund reason is required.")

    fee_rate = Decimal(str(getattr(settings, "PLATFORM_FEE_RATE", 0.20)))
    mentee_paid = booking.amount + (booking.amount * fee_rate).quantize(Decimal("0.01"))

    # Negative amount = money out of mVia's books (returned to mentee).
    LedgerEntry.objects.create(
        booking=booking, entry_type=LedgerEntry.TYPE_REFUND,
        amount=-mentee_paid, note=f"Refund: {reason.strip()}",
        external_reference=reference.strip(), created_by=actor)

    booking.is_refunded = True
    booking.refund_reason = reason.strip()
    booking.refund_reference = reference.strip()
    booking.refunded_at = timezone.now()
    booking.refunded_by = actor
    booking.save(update_fields=["is_refunded", "refund_reason", "refund_reference",
                                "refunded_at", "refunded_by"])
    return booking


# ──────────────────────────────────────────────────────────────────────────
# Scheduled / background tasks
# These are designed to be IDEMPOTENT: safe to run repeatedly (e.g. every 15
# min from a Render Cron Job) without double-acting. Each returns a count so
# the command can report what it did.
# ──────────────────────────────────────────────────────────────────────────

def expire_unpaid_bookings():
    """
    Expire pending_payment bookings older than BOOKING_EXPIRY_MINUTES, freeing
    the slot for others. Returns the number expired.
    """
    from datetime import timedelta

    minutes = getattr(settings, "BOOKING_EXPIRY_MINUTES", 30)
    cutoff = timezone.now() - timedelta(minutes=minutes)
    stale = Booking.objects.filter(
        status=Booking.STATUS_PENDING_PAYMENT, created_at__lt=cutoff)

    count = 0
    for booking in stale:
        # Use a transaction per booking so one failure doesn't block the rest.
        try:
            with transaction.atomic():
                b = Booking.objects.select_for_update().get(pk=booking.pk)
                if b.status != Booking.STATUS_PENDING_PAYMENT:
                    continue
                b.status = Booking.STATUS_EXPIRED
                b.save(update_fields=["status"])
                count += 1
        except Exception:  # noqa: BLE001 — never let one bad row stop the sweep
            continue
    return count


def auto_complete_past_sessions():
    """
    Mark confirmed bookings whose session end time has passed as completed.
    This is what feeds the payout report and enables reviews. Idempotent.
    Returns the number completed.
    """
    now = timezone.now()
    due = Booking.objects.filter(
        status=Booking.STATUS_CONFIRMED, slot__end__lt=now).select_related("slot")

    count = 0
    for booking in due:
        try:
            with transaction.atomic():
                b = Booking.objects.select_for_update().get(pk=booking.pk)
                if b.status != Booking.STATUS_CONFIRMED:
                    continue
                b.status = Booking.STATUS_COMPLETED
                b.completed_at = now
                b.save(update_fields=["status", "completed_at"])
                count += 1
        except Exception:  # noqa: BLE001
            continue
    return count


def send_due_reminders():
    """
    Send 24-hour and 1-hour reminder emails for upcoming confirmed sessions.
    Each reminder is sent at most once (tracked on the booking). Idempotent.
    Returns a dict with counts.
    """
    from datetime import timedelta
    from accounts.emails import send_email

    now = timezone.now()
    sent_24h = 0
    sent_1h = 0

    # 24h reminder: session starts within the next 24h, not already sent.
    window_24h = now + timedelta(hours=24)
    upcoming_24h = Booking.objects.filter(
        status=Booking.STATUS_CONFIRMED,
        reminder_24h_sent_at__isnull=True,
        slot__start__gt=now,
        slot__start__lte=window_24h,
    ).select_related("slot", "mentee", "mentor")

    for b in upcoming_24h:
        _send_reminder(b, "24 hours", "booking_reminder_24h")
        b.reminder_24h_sent_at = now
        b.save(update_fields=["reminder_24h_sent_at"])
        sent_24h += 1

    # 1h reminder: session starts within the next 1h, not already sent.
    window_1h = now + timedelta(hours=1)
    upcoming_1h = Booking.objects.filter(
        status=Booking.STATUS_CONFIRMED,
        reminder_1h_sent_at__isnull=True,
        slot__start__gt=now,
        slot__start__lte=window_1h,
    ).select_related("slot", "mentee", "mentor")

    for b in upcoming_1h:
        _send_reminder(b, "1 hour", "booking_reminder_1h")
        b.reminder_1h_sent_at = now
        b.save(update_fields=["reminder_1h_sent_at"])
        sent_1h += 1

    return {"sent_24h": sent_24h, "sent_1h": sent_1h}


def _send_reminder(booking, when_label, template_name):
    """Send one reminder email to the mentee (and record it in EmailLog)."""
    from accounts.emails import send_email

    when = timezone.localtime(booking.slot.start).strftime("%d %b %Y at %I:%M %p")
    subject = f"Reminder: your mVia session is in {when_label}"
    body = (
        f"Hi {booking.mentee.get_short_name()},\n\n"
        f"This is a reminder that your mentorship session with "
        f"{booking.mentor.full_name} is coming up in {when_label}.\n\n"
        f"When: {when}\n\n"
        f"See you there!\n— The mVia team"
    )
    send_email(
        to_email=booking.mentee.email, subject=subject, body=body,
        template_name=template_name, related_booking=booking)


def run_scheduled_tasks():
    """Run all scheduled maintenance tasks. Returns a summary dict."""
    expired = expire_unpaid_bookings()
    auto_declined = auto_decline_expired_approvals()
    completed = auto_complete_past_sessions()
    reminders = send_due_reminders()
    return {
        "expired_unpaid": expired,
        "auto_declined": auto_declined,
        "auto_completed": completed,
        "reminders_24h": reminders["sent_24h"],
        "reminders_1h": reminders["sent_1h"],
    }


# ──────────────────────────────────────────────────────────────────────────
# Rescheduling
# ──────────────────────────────────────────────────────────────────────────

MAX_RESCHEDULES = 2
RESCHEDULE_CUTOFF_HOURS = 24


def reschedule_booking(*, booking_id, new_slot_id, actor):
    """
    Move a confirmed booking to a different open slot of the SAME mentor.
    No new payment — the paid session simply moves. Rules:
      - booking must be confirmed (not completed/cancelled/expired)
      - at least RESCHEDULE_CUTOFF_HOURS before the CURRENT session start
      - new slot belongs to the same mentor, is in the future, and is free
      - at most MAX_RESCHEDULES times
    `actor` is the user performing it (mentee or staff) — used for audit only.
    """
    from datetime import timedelta

    with transaction.atomic():
        booking = Booking.objects.select_for_update().select_related("slot", "mentor").get(pk=booking_id)

        if booking.status != Booking.STATUS_CONFIRMED:
            raise BookingError("Only confirmed bookings can be rescheduled.")
        if getattr(booking.mentor, "is_archived", False):
            raise BookingError("This mentor is no longer active on mVia — rescheduling isn't available.")
        if booking.reschedule_count >= MAX_RESCHEDULES:
            raise BookingError(f"This booking has already been rescheduled {MAX_RESCHEDULES} times (the limit).")

        now = timezone.now()
        cutoff = booking.slot.start - timedelta(hours=RESCHEDULE_CUTOFF_HOURS)
        if now >= cutoff:
            raise BookingError(
                f"Rescheduling must be done at least {RESCHEDULE_CUTOFF_HOURS} hours before the session.")

        new_slot = AvailabilitySlot.objects.select_for_update().get(pk=new_slot_id)

        if new_slot.mentor_id != booking.mentor_id:
            raise BookingError("The new slot must belong to the same mentor.")
        if new_slot.pk == booking.slot_id:
            raise BookingError("That's the same slot the booking is already on.")
        if new_slot.start <= now:
            raise BookingError("The new slot is in the past.")

        # New slot must be free (no confirmed/completed booking on it).
        taken = Booking.objects.filter(
            slot=new_slot,
            status__in=[Booking.STATUS_CONFIRMED, Booking.STATUS_COMPLETED],
        ).exclude(pk=booking.pk).exists()
        if taken:
            raise BookingError("That slot is no longer available.")

        old_slot_start = booking.slot.start
        booking.slot = new_slot
        booking.reschedule_count += 1
        # Reset reminders so they fire correctly for the new time.
        booking.reminder_24h_sent_at = None
        booking.reminder_1h_sent_at = None
        try:
            booking.save(update_fields=[
                "slot", "reschedule_count", "reminder_24h_sent_at", "reminder_1h_sent_at"])
        except IntegrityError:
            raise BookingError("That slot was just taken by someone else.")

        # Audit trail.
        try:
            from auditlog.models import AdminAuditLog
            AdminAuditLog.record(
                actor=actor, action="booking.rescheduled",
                target=f"Booking #{booking.id}: {old_slot_start:%d %b %H:%M} → {new_slot.start:%d %b %H:%M}")
        except Exception:  # noqa: BLE001 — audit failure shouldn't block the reschedule
            pass

    # Notify the mentee (outside the transaction).
    try:
        from accounts.emails import send_email
        when = timezone.localtime(new_slot.start).strftime("%d %b %Y at %I:%M %p")
        send_email(
            to_email=booking.mentee.email,
            subject="Your mVia session has been rescheduled",
            body=(f"Hi {booking.mentee.get_short_name()},\n\n"
                  f"Your session with {booking.mentor.full_name} has been rescheduled.\n\n"
                  f"New time: {when}\n\n— The mVia team"),
            template_name="booking_rescheduled", related_booking=booking)
    except Exception:  # noqa: BLE001
        pass

    return booking


def open_slots_for_mentor(mentor, exclude_booking=None):
    """Future, confirmed, un-booked slots for a mentor — the choices when rescheduling."""
    now = timezone.now()
    # A slot is unavailable if it has a booking that's awaiting approval,
    # confirmed, or completed (matches AvailabilitySlot.is_taken).
    taken_slot_ids = Booking.objects.filter(
        mentor=mentor,
        status__in=[Booking.STATUS_AWAITING_APPROVAL, Booking.STATUS_CONFIRMED, Booking.STATUS_COMPLETED],
    ).values_list("slot_id", flat=True)
    # Only future AND mentor-confirmed slots are offered (RS-004: unconfirmed
    # slots must never be shown to mentees).
    qs = AvailabilitySlot.objects.filter(
        mentor=mentor, start__gt=now, is_confirmed=True
    ).exclude(pk__in=list(taken_slot_ids)).order_by("start")
    return qs


# ──────────────────────────────────────────────────────────────────────────
# Weekly availability → generated slots (Calendly-style)
# ──────────────────────────────────────────────────────────────────────────

def generate_slots_from_pattern(mentor, days=None):
    """
    For each WeeklyAvailability entry, ensure a concrete AvailabilitySlot exists
    for every matching date in the rolling window. Newly generated slots start
    UNCONFIRMED (the mentor confirms them in the 2-week view). Existing slots
    (confirmed or booked) are left untouched. Idempotent.
    """
    from datetime import timedelta, datetime
    from django.conf import settings
    from .models import WeeklyAvailability, AvailabilitySlot

    days = days or getattr(settings, "BOOKING_WINDOW_DAYS", 14)
    session_len = getattr(settings, "SESSION_LENGTH_MINUTES", 60)
    patterns = list(WeeklyAvailability.objects.filter(mentor=mentor))
    if not patterns:
        return 0

    now = timezone.now()
    today = timezone.localdate()
    created = 0

    for offset in range(days + 1):
        the_date = today + timedelta(days=offset)
        weekday = the_date.weekday()  # Mon=0 .. Sun=6
        for pat in patterns:
            if pat.weekday != weekday:
                continue
            # Build a timezone-aware start datetime for this date + pattern time.
            naive_start = datetime.combine(the_date, pat.start_time)
            start_dt = timezone.make_aware(naive_start, timezone.get_current_timezone())
            if start_dt <= now:
                continue  # don't generate past slots
            end_dt = start_dt + timedelta(minutes=session_len)
            # Create only if a slot at this exact start doesn't already exist.
            slot, was_created = AvailabilitySlot.objects.get_or_create(
                mentor=mentor, start=start_dt,
                defaults={"end": end_dt, "is_confirmed": False})
            if was_created:
                created += 1
    return created


def confirmable_slots(mentor, days=None):
    """
    The slots shown in the mentor's rolling confirmation view: all future slots
    within the window, whether confirmed or not, that aren't already booked.
    """
    from datetime import timedelta
    from django.conf import settings
    from .models import AvailabilitySlot

    days = days or getattr(settings, "BOOKING_WINDOW_DAYS", 14)
    now = timezone.now()
    horizon = now + timedelta(days=days + 1)
    return AvailabilitySlot.objects.filter(
        mentor=mentor, start__gt=now, start__lte=horizon
    ).order_by("start")


# ──────────────────────────────────────────────────────────────────────────
# Mentor approval flow (session must be approved after payment)
# ──────────────────────────────────────────────────────────────────────────

def approve_booking(*, booking_id, actor):
    """Mentor approves a paid, awaiting-approval booking -> confirmed."""
    with transaction.atomic():
        booking = Booking.objects.select_for_update().select_related("slot", "mentee", "mentor").get(pk=booking_id)
        if booking.status != Booking.STATUS_AWAITING_APPROVAL:
            raise BookingError("This booking is not awaiting approval.")
        booking.status = Booking.STATUS_CONFIRMED
        booking.confirmed_at = timezone.now()
        booking.approved_at = timezone.now()
        booking.save(update_fields=["status", "confirmed_at", "approved_at"])

    _notify(booking.mentee.email, "Your mVia session is confirmed!",
            f"Hi {booking.mentee.get_short_name()},\n\nGood news — {booking.mentor.full_name} has "
            f"approved your session on "
            f"{timezone.localtime(booking.slot.start):%d %b %Y at %I:%M %p}.\n\n"
            f"{'Join link: ' + booking.meet_link if booking.meet_link else 'The meeting link will be shared soon.'}"
            f"\n\n— mVia", "booking_approved", booking)
    return booking


def decline_booking(*, booking_id, actor, reason=""):
    """
    Mentor declines a paid booking -> declined. Records a refund ledger entry
    (ops still returns the money via Razorpay and enters the reference later).
    Frees the slot.
    """
    from decimal import Decimal
    from payments.models import LedgerEntry

    with transaction.atomic():
        booking = Booking.objects.select_for_update().select_related("slot", "mentee", "mentor").get(pk=booking_id)
        if booking.status != Booking.STATUS_AWAITING_APPROVAL:
            raise BookingError("This booking is not awaiting approval.")

        booking.status = Booking.STATUS_DECLINED
        booking.declined_at = timezone.now()
        booking.decline_reason = (reason or "").strip()
        booking.save(update_fields=["status", "declined_at", "decline_reason"])

        # Record the refund owed to the mentee (negative = money out of mVia).
        fee_rate = Decimal(str(getattr(settings, "PLATFORM_FEE_RATE", 0.20)))
        mentee_paid = booking.amount + (booking.amount * fee_rate).quantize(Decimal("0.01"))
        LedgerEntry.objects.create(
            booking=booking, entry_type=LedgerEntry.TYPE_REFUND,
            amount=-mentee_paid, note=f"Mentor declined: {booking.decline_reason or 'no reason given'}",
            created_by=actor)
        booking.is_refunded = True
        booking.refund_reason = f"Mentor declined: {booking.decline_reason}"
        booking.save(update_fields=["is_refunded", "refund_reason"])

    _notify(booking.mentee.email, "Update on your mVia session request",
            f"Hi {booking.mentee.get_short_name()},\n\nUnfortunately {booking.mentor.full_name} "
            f"couldn't confirm your requested session"
            f"{(' — ' + booking.decline_reason) if booking.decline_reason else ''}.\n\n"
            f"A full refund is being processed. We're sorry for the inconvenience.\n\n— mVia",
            "booking_declined", booking)
    return booking


def suggest_new_slot(*, booking_id, new_slot_id, actor):
    """
    Instead of declining, the mentor suggests a different open slot. The booking
    stays awaiting-approval; the mentee can accept (moves the booking) or the
    booking can later be declined/refunded.
    """
    with transaction.atomic():
        booking = Booking.objects.select_for_update().select_related("mentor", "mentee").get(pk=booking_id)
        if booking.status != Booking.STATUS_AWAITING_APPROVAL:
            raise BookingError("This booking is not awaiting approval.")
        new_slot = AvailabilitySlot.objects.select_for_update().get(pk=new_slot_id)
        if new_slot.mentor_id != booking.mentor_id:
            raise BookingError("Suggested slot must be the same mentor's.")
        if not new_slot.is_bookable:
            raise BookingError("That slot isn't available.")
        booking.suggested_slot = new_slot
        booking.save(update_fields=["suggested_slot"])

    _notify(booking.mentee.email, "Your mentor suggested a new time",
            f"Hi {booking.mentee.get_short_name()},\n\n{booking.mentor.full_name} can't make your "
            f"original time but suggested a new one: "
            f"{timezone.localtime(new_slot.start):%d %b %Y at %I:%M %p}.\n\n"
            f"Open mVia to accept the new time or request a refund.\n\n— mVia",
            "booking_suggested", booking)
    return booking


def accept_suggested_slot(*, booking_id, actor):
    """Mentee accepts the mentor's suggested slot; the booking moves to it."""
    with transaction.atomic():
        booking = Booking.objects.select_for_update().select_related("suggested_slot").get(pk=booking_id)
        if booking.mentee_id != actor.id:
            raise BookingError("Only the mentee can accept.")
        if not booking.suggested_slot:
            raise BookingError("No suggested slot to accept.")
        new_slot = AvailabilitySlot.objects.select_for_update().get(pk=booking.suggested_slot_id)
        if not new_slot.is_bookable:
            raise BookingError("That slot is no longer available.")
        booking.slot = new_slot
        booking.suggested_slot = None
        booking.reminder_24h_sent_at = None
        booking.reminder_1h_sent_at = None
        booking.save(update_fields=["slot", "suggested_slot", "reminder_24h_sent_at", "reminder_1h_sent_at"])
    return booking


def set_meet_link(*, booking_id, link, actor):
    """Admin sets/updates the Google Meet link on a booking."""
    booking = Booking.objects.get(pk=booking_id)
    booking.meet_link = (link or "").strip()
    booking.save(update_fields=["meet_link"])
    return booking


# ──────────────────────────────────────────────────────────────────────────
# Mentor session wrap-up: no-shows and recordings
# ──────────────────────────────────────────────────────────────────────────

def mark_no_show(*, booking_id, actor):
    """
    Mentor marks a confirmed booking as a no-show (the mentee didn't attend).
    Only allowed once the session's scheduled end time has passed — mirrors
    auto_complete_past_sessions' own timing check, so a mentor can't pre-empt
    a session that hasn't happened yet.
    """
    with transaction.atomic():
        booking = Booking.objects.select_for_update().select_related(
            "slot", "mentee", "mentor").get(pk=booking_id)
        if not booking.can_transition_to(Booking.STATUS_NO_SHOW):
            raise BookingError("This booking can't be marked as a no-show.")
        if booking.slot.end > timezone.now():
            raise BookingError("You can only mark a no-show after the session's scheduled time.")

        booking.status = Booking.STATUS_NO_SHOW
        booking.save(update_fields=["status"])

        try:
            from auditlog.models import AdminAuditLog
            AdminAuditLog.record(
                actor=actor, action="booking.no_show",
                target=f"Booking #{booking.id}: {booking.mentee.get_short_name()} marked as "
                       f"no-show by {booking.mentor.get_short_name()}")
        except Exception:  # noqa: BLE001 — audit failure shouldn't block the update
            pass
    return booking


def set_recording(*, booking_id, actor, recording_url="", session_notes=""):
    """
    Mentor attaches a recording link and/or notes to a session that has
    happened. Allowed on confirmed (already past) or completed bookings only.
    """
    with transaction.atomic():
        booking = Booking.objects.select_for_update().select_related(
            "mentee", "mentor").get(pk=booking_id)
        if booking.status not in (Booking.STATUS_CONFIRMED, Booking.STATUS_COMPLETED):
            raise BookingError("Recordings and notes can only be added to confirmed or completed sessions.")

        booking.recording_url = (recording_url or "").strip()
        booking.session_notes = (session_notes or "").strip()
        booking.save(update_fields=["recording_url", "session_notes"])

        try:
            from auditlog.models import AdminAuditLog
            AdminAuditLog.record(
                actor=actor, action="booking.recording_added",
                target=f"Booking #{booking.id}: recording/notes updated by {booking.mentor.get_short_name()}")
        except Exception:  # noqa: BLE001 — audit failure shouldn't block the update
            pass
    return booking


def auto_decline_expired_approvals():
    """
    Auto-decline (and refund) bookings whose 48h approval window passed without
    the mentor acting. Idempotent; intended for the scheduler.
    """
    now = timezone.now()
    overdue = Booking.objects.filter(
        status=Booking.STATUS_AWAITING_APPROVAL, approval_due_at__lt=now)
    count = 0
    for b in overdue:
        try:
            decline_booking(booking_id=b.id, actor=None,
                            reason="Auto-declined: mentor did not respond within 48 hours.")
            count += 1
        except Exception:  # noqa: BLE001
            continue
    return count


def _notify(to_email, subject, body, template_name, booking):
    try:
        from accounts.emails import send_email
        send_email(to_email=to_email, subject=subject, body=body,
                   template_name=template_name, related_booking=booking)
    except Exception:  # noqa: BLE001
        pass
