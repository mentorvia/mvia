"""
Payment records (requirement 4.6 / 4.7).

Each payment attempt for a booking is recorded here. Until Razorpay is
configured, payments run in SIMULATION mode: a record is created and marked
'paid' without charging a card, and is_simulated=True flags it clearly.
When real Razorpay keys are added, real order/payment IDs are stored instead.
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


class Payment(models.Model):
    STATUS_CREATED = "created"
    STATUS_PAID = "paid"
    STATUS_FAILED = "failed"
    STATUS_REFUNDED = "refunded"
    STATUS_CHOICES = [
        (STATUS_CREATED, "Created"),
        (STATUS_PAID, "Paid"),
        (STATUS_FAILED, "Failed"),
        (STATUS_REFUNDED, "Refunded"),
    ]

    booking = models.ForeignKey(
        "bookings.Booking", on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_CREATED)

    is_simulated = models.BooleanField(
        default=True, help_text="True until real Razorpay payments are live.")

    # Razorpay identifiers (populated only for real payments).
    razorpay_order_id = models.CharField(max_length=120, blank=True)
    razorpay_payment_id = models.CharField(max_length=120, blank=True)
    razorpay_signature = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def mark_paid(self):
        self.status = self.STATUS_PAID
        self.paid_at = timezone.now()
        self.save(update_fields=["status", "paid_at"])

    def __str__(self):
        tag = "SIM" if self.is_simulated else "LIVE"
        return f"Payment #{self.pk} [{tag}] {self.get_status_display()} ₹{self.amount}"
