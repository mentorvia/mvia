"""
Lead capture (free-consultation survey).

A Lead is a prospective mentee who filled the short "get a free consultation"
survey on the public site. It is deliberately NOT tied to the User model — a
lead is a pre-account enquiry, exactly like MentorApplication is for mentors.
The ops team follows up manually (call / email) and ticks the lead as
contacted in the staff console.

This app is self-contained: it adds one new table and touches nothing in the
existing accounts / bookings / payments / profiles apps.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


class Lead(models.Model):
    # What the visitor fills in.
    name = models.CharField(max_length=150)
    email = models.EmailField()
    phone = models.CharField(max_length=30, blank=True)

    # Optional guiding questions (all blank-able so a short form still works).
    current_role = models.CharField(
        max_length=160, blank=True,
        help_text="e.g. Final-year student, Working professional, Career switcher.")
    goal = models.TextField(
        blank=True, help_text="What the person wants help with.")
    field_of_interest = models.CharField(
        max_length=160, blank=True,
        help_text="Free text — the area they're interested in.")

    # Ops follow-up tracking.
    is_contacted = models.BooleanField(default=False)
    contacted_at = models.DateTimeField(null=True, blank=True)
    contacted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="leads_contacted")
    notes = models.TextField(blank=True, help_text="Internal ops notes.")

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} <{self.email}> ({'contacted' if self.is_contacted else 'new'})"
