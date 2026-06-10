"""
Mentee and Mentor profiles (requirements 4.2, 4.3).

One account can be BOTH. A user starts with a MenteeProfile (created on demand);
they can apply for a MentorProfile, which starts PENDING until an admin approves.
"""

from decimal import Decimal

from django.conf import settings
from django.db import models


class MenteeProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mentee_profile")
    current_role = models.CharField(max_length=120, blank=True)
    company = models.CharField(max_length=120, blank=True)
    years_experience = models.PositiveIntegerField(null=True, blank=True)
    career_goals = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def is_complete(self):
        """
        'Reasonably complete' gate before booking (req 4.2). Our defined minimum:
        a current role, career goals, and at least one interest selected.
        """
        has_basics = bool(self.current_role.strip()) and bool(self.career_goals.strip())
        has_interest = self.user.mentee_interests.exists()
        return has_basics and has_interest

    def missing_fields(self):
        missing = []
        if not self.current_role.strip():
            missing.append("current role")
        if not self.career_goals.strip():
            missing.append("career goals")
        if not self.user.mentee_interests.exists():
            missing.append("at least one interest")
        return missing

    def __str__(self):
        return f"Mentee: {self.user.email}"


class MentorProfile(models.Model):
    STATUS_PENDING = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending review"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mentor_profile")
    current_role = models.CharField(max_length=120)
    company = models.CharField(max_length=120)
    years_experience = models.PositiveIntegerField()
    bio = models.TextField()
    hourly_rate = models.DecimalField(
        max_digits=10, decimal_places=2,
        help_text="Mentor's rate per session, in INR.")

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_PENDING)
    is_available = models.BooleanField(
        default=True, help_text="Mentor can toggle this to pause new bookings.")

    # Review metadata
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="mentor_reviews")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def is_listable(self):
        """Appears in the directory only if approved and available."""
        return self.status == self.STATUS_APPROVED and self.is_available

    def __str__(self):
        return f"Mentor: {self.user.email} ({self.status})"
