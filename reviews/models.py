"""
Post-session reviews (requirement: feedback/ratings feeding the directory).

A mentee who completed a session can rate the mentor (1–5 stars), optionally
write a public-eligible review, and optionally leave a private note for admins.
One review per booking. Written reviews are admin-only for now; only the
aggregate rating is shown publicly.
"""

from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models


class Review(models.Model):
    booking = models.OneToOneField(
        "bookings.Booking", on_delete=models.CASCADE, related_name="review")
    mentee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews_given")
    mentor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews_received")

    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)])
    review_text = models.TextField(
        blank=True, help_text="Optional written feedback (admin-only display for now).")
    private_note = models.TextField(
        blank=True, help_text="Private note to admins. Never shown publicly.")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.rating}★ for {self.mentor.get_short_name()} (booking #{self.booking_id})"
