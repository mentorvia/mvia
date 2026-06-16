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


class LedgerEntry(models.Model):
    """
    Append-only money ledger. Every financial event writes one or more entries
    here and they are NEVER edited or deleted — corrections are made by adding
    new entries. This gives mVia a trustworthy, auditable record of every rupee.

    mVia does not move money itself: actual collection happens via Razorpay and
    refunds/payouts are performed manually by the ops team. The ledger is the
    system of record that mirrors those real-world money movements.
    """
    TYPE_BOOKING_PAYMENT = "booking_payment"   # mentee paid for a session
    TYPE_PLATFORM_FEE = "platform_fee"          # mVia's share (the add-on fee)
    TYPE_MENTOR_EARNING = "mentor_earning"      # amount owed to the mentor
    TYPE_REFUND = "refund"                       # money returned to a mentee
    TYPE_CHOICES = [
        (TYPE_BOOKING_PAYMENT, "Booking payment (mentee paid)"),
        (TYPE_PLATFORM_FEE, "Platform fee (mVia)"),
        (TYPE_MENTOR_EARNING, "Mentor earning"),
        (TYPE_REFUND, "Refund (to mentee)"),
    ]

    booking = models.ForeignKey(
        "bookings.Booking", on_delete=models.PROTECT, related_name="ledger_entries")
    entry_type = models.CharField(max_length=20, choices=TYPE_CHOICES)

    # Signed amount: positive = money into mVia / owed; negative = money out (refund).
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    note = models.TextField(blank=True)
    # For refunds: the reference number from the Razorpay dashboard, entered by
    # ops AFTER they perform the actual refund there.
    external_reference = models.CharField(max_length=120, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="ledger_entries_created")

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.get_entry_type_display()} ₹{self.amount} (booking #{self.booking_id})"
