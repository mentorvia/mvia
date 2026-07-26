"""Member-facing payment views."""

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.shortcuts import render, redirect
from django.utils import timezone

from .models import LedgerEntry


@login_required
def my_earnings(request):
    """A mentor's own earnings history, grouped by the month each session happened."""
    if not request.user.is_mentor:
        messages.error(request, "Only mentors can view earnings.")
        return redirect("dashboard")

    entries = (
        LedgerEntry.objects.filter(
            booking__mentor=request.user, entry_type=LedgerEntry.TYPE_MENTOR_EARNING)
        .select_related("booking", "booking__mentee", "booking__slot", "payout")
        .order_by("-booking__slot__start")
    )

    groups = {}
    for entry in entries:
        key = timezone.localtime(entry.booking.slot.start).strftime("%B %Y")
        groups.setdefault(key, []).append(entry)

    total_earned = entries.aggregate(s=Sum("amount"))["s"] or Decimal("0")
    total_paid = entries.filter(payout__isnull=False).aggregate(s=Sum("amount"))["s"] or Decimal("0")
    total_pending = total_earned - total_paid

    return render(request, "payments/my_earnings.html", {
        "groups": groups,
        "total_earned": total_earned,
        "total_paid": total_paid,
        "total_pending": total_pending,
    })
