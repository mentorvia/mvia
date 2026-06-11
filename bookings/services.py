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
    Mark a booking's payment successful and move it to confirmed. Re-checks slot
    availability under lock to be safe. Returns the Booking.
    """
    booking = Booking.objects.select_for_update().select_related("slot").get(pk=booking_id)

    if booking.status != Booking.STATUS_PENDING_PAYMENT:
        raise BookingError("This booking is no longer awaiting payment.")
    if not booking.can_transition_to(Booking.STATUS_CONFIRMED):
        raise BookingError("This booking can't be confirmed.")

    # Final guard: ensure no other confirmed booking grabbed this slot.
    clash = Booking.objects.filter(
        slot=booking.slot,
        status__in=[Booking.STATUS_CONFIRMED, Booking.STATUS_COMPLETED],
    ).exclude(pk=booking.pk).exists()
    if clash:
        raise BookingError("That slot was confirmed by someone else first.")

    payment = booking.payments.order_by("-created_at").first()
    if payment:
        payment.is_simulated = simulated
        payment.razorpay_payment_id = razorpay_payment_id
        payment.razorpay_signature = razorpay_signature
        payment.mark_paid()

    booking.status = Booking.STATUS_CONFIRMED
    booking.confirmed_at = timezone.now()
    try:
        booking.save(update_fields=["status", "confirmed_at"])
    except IntegrityError:
        # The unique constraint caught a concurrent confirm — treat as clash.
        raise BookingError("That slot was confirmed by someone else first.")
    return booking


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
