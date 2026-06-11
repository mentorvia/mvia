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


class AvailabilitySlot(models.Model):
    mentor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="availability_slots")
    start = models.DateTimeField()
    end = models.DateTimeField()
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
        """A slot is taken if it has a confirmed (or completed) booking."""
        return self.bookings.filter(
            status__in=[Booking.STATUS_CONFIRMED, Booking.STATUS_COMPLETED]
        ).exists()

    @property
    def is_bookable(self):
        return (not self.is_past) and (not self.is_taken)

    def __str__(self):
        return f"{self.mentor.get_short_name()} · {self.start:%d %b %Y %H:%M}"


class Booking(models.Model):
    STATUS_PENDING_PAYMENT = "pending_payment"
    STATUS_CONFIRMED = "confirmed"
    STATUS_COMPLETED = "completed"
    STATUS_CANCELLED = "cancelled"
    STATUS_EXPIRED = "expired"
    STATUS_CHOICES = [
        (STATUS_PENDING_PAYMENT, "Pending payment"),
        (STATUS_CONFIRMED, "Confirmed"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_CANCELLED, "Cancelled"),
        (STATUS_EXPIRED, "Expired"),
    ]

    # Which terminal/next states each state may move to. The state machine
    # enforces this so a booking can never make an illegal jump.
    ALLOWED_TRANSITIONS = {
        STATUS_PENDING_PAYMENT: {STATUS_CONFIRMED, STATUS_EXPIRED, STATUS_CANCELLED},
        STATUS_CONFIRMED: {STATUS_COMPLETED, STATUS_CANCELLED},
        STATUS_COMPLETED: set(),
        STATUS_CANCELLED: set(),
        STATUS_EXPIRED: set(),
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
