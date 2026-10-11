"""
Lead capture (free-consultation funnel).

A Lead is a prospective mentee who went through the public "free consultation"
funnel: a short registration (step 1) followed by the "Navi's Career Navigation
Audit" quiz (step 2). It is deliberately NOT tied to the User model — a lead is
a pre-account enquiry, like MentorApplication is for mentors. Ops follows up
manually and ticks the lead as contacted in the staff console.

The lead is saved after step 1 (registration) so we capture the contact even
if the person abandons the quiz. Quiz answers + the HOT/WARM/COLD priority tag
are filled in on step 2.

This app is self-contained: it adds one new table and touches nothing in the
existing accounts / bookings / payments / profiles apps.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


class Lead(models.Model):
    # ---------- Step 1: registration (basic info) ----------
    name = models.CharField(max_length=150)
    whatsapp = models.CharField(max_length=30, blank=True)
    # "Work Email / LinkedIn link" — one free field, since the person may give either.
    email_or_linkedin = models.CharField(max_length=255, blank=True)
    # Kept so the staff list / admin can still filter by a real email when given one.
    email = models.EmailField(blank=True)

    DOMAIN_CHOICES = [
        ("technology", "Technology / IT"),
        ("engineering", "Engineering"),
        ("finance", "Finance"),
        ("consulting", "Consulting"),
        ("product", "Product"),
        ("operations", "Operations"),
        ("marketing", "Marketing"),
        ("healthcare", "Healthcare"),
        ("other", "Other"),
    ]
    domain = models.CharField(max_length=30, choices=DOMAIN_CHOICES, blank=True)
    domain_other = models.CharField(max_length=120, blank=True)

    # ---------- Step 2: the quiz ("Navi's Career Navigation Audit") ----------
    quiz_completed = models.BooleanField(default=False)

    # Q1 — career stage
    q1_stage = models.CharField(max_length=80, blank=True)
    # Q2 — what they want help with
    q2_help = models.CharField(max_length=120, blank=True)
    q2_help_other = models.CharField(max_length=160, blank=True)
    # Q3 — biggest career question/challenge (open)
    q3_challenge = models.TextField(blank=True)
    # Q4 — what they hope to achieve (open)
    q4_goal = models.TextField(blank=True)
    # Q6 — actively looking to invest in next 30 days
    q6_intent = models.CharField(max_length=60, blank=True)
    # Q7 — time per week
    q7_time = models.CharField(max_length=40, blank=True)
    # Q8 — kind of mentor
    q8_mentor_type = models.CharField(max_length=120, blank=True)
    # Q9 — how they make decisions today
    q9_decisions = models.CharField(max_length=120, blank=True)
    # Q10 — best way to connect
    q10_contact_pref = models.CharField(max_length=40, blank=True)

    # ---------- Priority tag (auto-computed from the quiz) ----------
    TAG_HOT = "hot"
    TAG_WARM = "warm"
    TAG_COLD = "cold"
    TAG_NEW = "new"  # registered but quiz not done yet
    TAG_CHOICES = [
        (TAG_HOT, "Hot"),
        (TAG_WARM, "Warm"),
        (TAG_COLD, "Cold"),
        (TAG_NEW, "New (quiz pending)"),
    ]
    priority = models.CharField(max_length=10, choices=TAG_CHOICES, default=TAG_NEW)

    # ---------- Ops follow-up tracking ----------
    is_contacted = models.BooleanField(default=False)
    contacted_at = models.DateTimeField(null=True, blank=True)
    contacted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="leads_contacted")
    notes = models.TextField(blank=True, help_text="Internal ops notes.")

    created_at = models.DateTimeField(default=timezone.now)
    quiz_completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.get_priority_display()})"

    def compute_priority(self):
        """
        Auto-tag from the quiz answers:
          HOT  = actively looking (Q6) + 3+ hrs/week (Q7) + a real challenge written (Q3)
          WARM = "maybe" (Q6) + a challenge written (Q3)
          COLD = "no, just free" (Q6)
        Anything else falls back to WARM if they finished the quiz, else NEW.
        """
        q6 = (self.q6_intent or "").lower()
        has_challenge = bool((self.q3_challenge or "").strip())
        strong_time = self.q7_time in ("3-4 hours/week", "6+ hours/week")

        if not self.quiz_completed:
            return self.TAG_NEW
        if q6.startswith("yes") and strong_time and has_challenge:
            return self.TAG_HOT
        if q6.startswith("maybe") and has_challenge:
            return self.TAG_WARM
        if q6.startswith("no"):
            return self.TAG_COLD
        return self.TAG_WARM
