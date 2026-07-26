"""
Availability slots and bookings (requirement 4.6).

Scheduling model (per product decision):
- A mentor publishes specific AvailabilitySlots (date + start/end time).
- A mentee books a slot. Payment happens at booking time.

Booking lifecycle:
    pending_payment ──pay──▶ confirmed ──(after session)──▶ completed
          │                      │
          └──expire──▶ expired   └──cancel──▶ cancelled

Double-booking is prevented at the DB level: a slot has a OneToOne link to its
confirmed booking, so two confirmed bookings can never share a slot.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


class WeeklyAvailability(models.Model):
    """
    A mentor's recurring weekly availability pattern: for a given weekday, a
    start time at which a fixed-length session can begin. The mentor sets these
    once; the system uses them to pre-fill the rolling 2-week confirmation view,
    from which concrete AvailabilitySlots are generated.

    Example: (mentor=Arjun, weekday=2 [Wed], start_time=18:00) means "Arjun is
    generally free Wednesdays at 6pm."
    """
    WEEKDAYS = [
        (0, "Monday"), (1, "Tuesday"), (2, "Wednesday"), (3, "Thursday"),
        (4, "Friday"), (5, "Saturday"), (6, "Sunday"),
    ]
    mentor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="weekly_availability")
    weekday = models.IntegerField(choices=WEEKDAYS)
    start_time = models.TimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["weekday", "start_time"]
        constraints = [
            models.UniqueConstraint(
                fields=["mentor", "weekday", "start_time"],
                name="unique_mentor_weekday_time"),
        ]

    def __str__(self):
        return f"{self.mentor.get_short_name()} · {self.get_weekday_display()} {self.start_time:%H:%M}"


class AvailabilitySlot(models.Model):
    mentor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="availability_slots")
    start = models.DateTimeField()
    end = models.DateTimeField()
    # In the weekly-pattern model, generated slots must be CONFIRMED by the
    # mentor (in the 2-week view) before mentees can see/book them. Slots the
    # mentor unchecks (travel/holiday) simply aren't confirmed.
    is_confirmed = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["start"]
        constraints = [
            # A mentor can't have two slots with the exact same start time.
            models.UniqueConstraint(fields=["mentor", "start"], name="unique_mentor_slot_start"),
        ]

    @property
    def is_past(self):
        return self.start <= timezone.now()

    @property
    def is_taken(self):
        """A slot is taken if it has an awaiting-approval, confirmed, or completed booking."""
        return self.bookings.filter(
            status__in=[Booking.STATUS_AWAITING_APPROVAL, Booking.STATUS_CONFIRMED, Booking.STATUS_COMPLETED]
        ).exists()

    @property
    def is_bookable(self):
        return (not self.is_past) and (not self.is_taken) and self.is_confirmed

    def __str__(self):
        return f"{self.mentor.get_short_name()} · {self.start:%d %b %Y %H:%M}"


class Booking(models.Model):
    STATUS_PENDING_PAYMENT = "pending_payment"
    STATUS_AWAITING_APPROVAL = "awaiting_approval"
    STATUS_CONFIRMED = "confirmed"
    STATUS_COMPLETED = "completed"
    STATUS_CANCELLED = "cancelled"
    STATUS_EXPIRED = "expired"
    STATUS_DECLINED = "declined"
    STATUS_NO_SHOW = "no_show"
    STATUS_CHOICES = [
        (STATUS_PENDING_PAYMENT, "Pending payment"),
        (STATUS_AWAITING_APPROVAL, "Awaiting mentor approval"),
        (STATUS_CONFIRMED, "Confirmed"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_CANCELLED, "Cancelled"),
        (STATUS_EXPIRED, "Expired"),
        (STATUS_DECLINED, "Declined by mentor"),
        (STATUS_NO_SHOW, "No-show"),
    ]

    # Which terminal/next states each state may move to. The state machine
    # enforces this so a booking can never make an illegal jump.
    ALLOWED_TRANSITIONS = {
        # After payment, a booking awaits mentor approval (not instantly confirmed).
        STATUS_PENDING_PAYMENT: {STATUS_AWAITING_APPROVAL, STATUS_CONFIRMED, STATUS_EXPIRED, STATUS_CANCELLED},
        # Mentor approves -> confirmed; declines -> declined; or it can be cancelled.
        STATUS_AWAITING_APPROVAL: {STATUS_CONFIRMED, STATUS_DECLINED, STATUS_CANCELLED},
        STATUS_CONFIRMED: {STATUS_COMPLETED, STATUS_CANCELLED, STATUS_NO_SHOW},
        STATUS_COMPLETED: set(),
        STATUS_CANCELLED: set(),
        STATUS_EXPIRED: set(),
        STATUS_DECLINED: set(),
        STATUS_NO_SHOW: set(),
    }

    mentee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bookings_as_mentee")
    mentor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bookings_as_mentor")
    slot = models.ForeignKey(
        AvailabilitySlot, on_delete=models.PROTECT, related_name="bookings")

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING_PAYMENT)

    # Money snapshot at booking time (mentor's rate can change later; this is fixed).
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="bookings_cancelled")
    cancellation_reason = models.TextField(blank=True)

    # Refund tracking. mVia records the refund; the actual money is returned by
    # ops via the Razorpay dashboard, then the reference is entered here.
    is_refunded = models.BooleanField(default=False)
    refund_reason = models.TextField(blank=True)
    refund_reference = models.CharField(
        max_length=120, blank=True, help_text="Razorpay refund reference, entered after refunding there.")
    refunded_at = models.DateTimeField(null=True, blank=True)
    refunded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="bookings_refunded")

    # Reminder tracking — so the scheduler never sends the same reminder twice.
    reminder_24h_sent_at = models.DateTimeField(null=True, blank=True)
    reminder_1h_sent_at = models.DateTimeField(null=True, blank=True)

    # How many times this booking has been rescheduled (capped in services).
    reschedule_count = models.PositiveSmallIntegerField(default=0)

    # Google Meet (or other video) link for the session. Added by admin; visible
    # to admin, mentor, and mentee once set.
    meet_link = models.URLField(blank=True)

    # Post-session recording + mentor notes, added from the mentor dashboard.
    recording_url = models.URLField(blank=True)
    session_notes = models.TextField(blank=True)

    # Mentor approval flow (session must be approved after payment).
    approved_at = models.DateTimeField(null=True, blank=True)
    declined_at = models.DateTimeField(null=True, blank=True)
    decline_reason = models.TextField(blank=True)
    # When the awaiting-approval window opened (for the 48h timeout).
    approval_due_at = models.DateTimeField(null=True, blank=True)
    # Mentor's suggested alternative slot (instead of a flat decline).
    suggested_slot = models.ForeignKey(
        "AvailabilitySlot", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="suggested_for_bookings")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # At most ONE confirmed/completed booking per slot (prevents double-booking).
            models.UniqueConstraint(
                fields=["slot"],
                condition=models.Q(status__in=["confirmed", "completed"]),
                name="one_active_booking_per_slot",
            ),
        ]

    def can_transition_to(self, new_status):
        return new_status in self.ALLOWED_TRANSITIONS.get(self.status, set())

    def __str__(self):
        return f"Booking #{self.pk}: {self.mentee.get_short_name()} → {self.mentor.get_short_name()} ({self.status})"
