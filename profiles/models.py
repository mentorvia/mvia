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

    # Social links, shown on the dashboard's profile-completion checklist.
    linkedin_url = models.URLField(blank=True)
    instagram_url = models.URLField(blank=True)
    behance_url = models.URLField(blank=True)

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
        help_text="Mentor's rate per session, in INR (exclusive of GST).")

    # --- Rich profile content (for the modern public profile page) ---
    headline = models.CharField(
        max_length=200, blank=True,
        help_text="Short tagline shown under the name, e.g. 'Technology & business leader, 34+ years'.")
    photo = models.ImageField(
        upload_to="mentor_photos/", blank=True, null=True,
        help_text="Profile photo. (On free hosting, prefer photo_url until persistent storage is set up.)")
    photo_url = models.URLField(
        blank=True,
        help_text="Alternative: a hosted image link. Used if no uploaded photo is present.")
    linkedin_url = models.URLField(blank=True)
    website_url = models.URLField(blank=True)
    gst_note = models.CharField(
        max_length=120, blank=True, default="Exclusive of 18% GST",
        help_text="Shown next to the price, e.g. 'Exclusive of 18% GST'.")

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

    @property
    def display_photo(self):
        """Prefer an uploaded photo, fall back to a pasted URL, else None."""
        if self.photo:
            try:
                return self.photo.url
            except ValueError:
                pass
        return self.photo_url or None

    @property
    def expertise_points(self):
        return self.points.filter(category="expertise")

    @property
    def focus_points(self):
        return self.points.filter(category="focus")

    @property
    def rating_summary(self):
        """Average rating + count for this mentor. Cached on the instance."""
        if not hasattr(self, "_rating_summary"):
            from django.db.models import Avg, Count
            agg = self.user.reviews_received.aggregate(
                avg=Avg("rating"), n=Count("id"))
            self._rating_summary = (agg["avg"], agg["n"] or 0)
        return self._rating_summary

    @property
    def avg_rating(self):
        return self.rating_summary[0]

    @property
    def review_count(self):
        return self.rating_summary[1]

    @property
    def rating_display(self):
        """'New' for unrated mentors, else a one-decimal average."""
        avg, n = self.rating_summary
        if not n:
            return "New"
        return f"{avg:.1f}"

    def __str__(self):
        return f"Mentor: {self.user.email} ({self.status})"


class ProfilePoint(models.Model):
    """
    A single title+description point belonging to one of the two fixed profile
    sections: Core Industry Expertise, or Mentorship Focus Areas. (The "About"
    section is the MentorProfile.bio field.) This gives every mentor profile a
    uniform, modern structure.
    """
    CATEGORY_EXPERTISE = "expertise"
    CATEGORY_FOCUS = "focus"
    CATEGORY_CHOICES = [
        (CATEGORY_EXPERTISE, "Core Industry Expertise"),
        (CATEGORY_FOCUS, "Mentorship Focus Areas"),
    ]

    mentor = models.ForeignKey(
        MentorProfile, on_delete=models.CASCADE, related_name="points")
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0, help_text="Lower numbers show first.")

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.get_category_display()}: {self.title}"
