"""
Admin audit log (requirement 4.10 / 9.2).

An append-only record of admin actions that change data: who did it, what they
did, when, the target, and an optional reason. We never edit or delete entries.
Reused across the app — mentor approvals now, settings/payouts/promo codes later.
"""

from django.conf import settings
from django.db import models


class AdminAuditLog(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
        related_name="audit_actions",
        help_text="The staff user who performed the action.")
    action = models.CharField(max_length=80, help_text="e.g. 'mentor.approve'")
    target = models.CharField(
        max_length=255, blank=True,
        help_text="Human-readable description of what was acted on.")
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    @classmethod
    def record(cls, *, actor, action, target="", reason=""):
        return cls.objects.create(actor=actor, action=action, target=target, reason=reason)

    def __str__(self):
        who = self.actor.email if self.actor else "system"
        return f"{who} · {self.action} · {self.target}"
