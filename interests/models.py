"""
Interests / specializations (requirement 4.4).

Design: a normalized tree. ONE model, self-referencing via `parent`:
- A top-level node (parent = null) is a CATEGORY, e.g. "Tech", "Business".
- A child node is a sub-domain, e.g. "Machine Learning" under "Tech",
  and can itself have children, e.g. "Deep Learning" under "Machine Learning".

Mentees and mentors attach to specific Interest rows through JOIN models
(MenteeInterest / MentorInterest) — never comma-separated tags.

Custom interests typed by users are stored here too, flagged is_custom=True
and is_approved=False, so an admin can later promote them into the managed list.
"""

from django.conf import settings
from django.db import models
from django.utils.text import slugify


class Interest(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="children",
        help_text="Leave empty to make this a top-level category.",
    )

    # Custom-interest handling: users can submit their own; admins promote them.
    is_custom = models.BooleanField(
        default=False, help_text="True if a user submitted this rather than an admin.")
    is_approved = models.BooleanField(
        default=True, help_text="Approved interests are selectable/visible. Custom ones start unapproved.")
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="submitted_interests")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        # No two interests with the same name under the same parent.
        constraints = [
            models.UniqueConstraint(fields=["parent", "name"], name="unique_name_per_parent"),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)
            slug = base
            n = 1
            # Ensure slug uniqueness even if two interests share a name in different branches.
            while Interest.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                n += 1
                slug = f"{base}-{n}"
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def is_category(self):
        """A top-level node (no parent) is a category."""
        return self.parent_id is None

    @property
    def depth(self):
        d, node = 0, self
        while node.parent_id is not None:
            d += 1
            node = node.parent
        return d

    def breadcrumb(self):
        """e.g. 'Tech › Machine Learning › Deep Learning'."""
        parts, node = [], self
        while node is not None:
            parts.append(node.name)
            node = node.parent
        return " › ".join(reversed(parts))

    def __str__(self):
        return self.breadcrumb()


# --- Join models: link users to interests (normalized; never CSV tags) ---

class MenteeInterest(models.Model):
    """A mentee's selected interest."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="mentee_interests")
    interest = models.ForeignKey(Interest, on_delete=models.CASCADE,
                                 related_name="mentee_links")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "interest"], name="unique_mentee_interest"),
        ]

    def __str__(self):
        return f"{self.user.email} → {self.interest.name}"


class MentorInterest(models.Model):
    """A mentor's specialization."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name="mentor_interests")
    interest = models.ForeignKey(Interest, on_delete=models.CASCADE,
                                 related_name="mentor_links")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "interest"], name="unique_mentor_interest"),
        ]

    def __str__(self):
        return f"{self.user.email} → {self.interest.name}"
