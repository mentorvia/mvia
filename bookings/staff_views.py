"""Staff console: bookings overview, refunds, and the money ledger."""

from decimal import Decimal
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Sum
from django.shortcuts import render, redirect, get_object_or_404

from .models import Booking
from .services import record_refund, BookingError
from payments.models import LedgerEntry


def staff_required(view):
    return user_passes_test(lambda u: u.is_authenticated and u.is_staff, login_url="login")(view)


@staff_required
def bookings_list(request):
    bookings = Booking.objects.select_related("mentee", "mentor", "slot").order_by("-created_at")
    return render(request, "bookings/staff_bookings.html", {
        "bookings": bookings, "active_nav": "bookings",
    })


@staff_required
def booking_detail(request, booking_id):
    booking = get_object_or_404(
        Booking.objects.select_related("mentee", "mentor", "slot"), pk=booking_id)

    if request.method == "POST" and request.POST.get("action") == "record_refund":
        try:
            record_refund(
                booking_id=booking.id, actor=request.user,
                reason=request.POST.get("reason", ""),
                reference=request.POST.get("reference", ""))
            from auditlog.models import AdminAuditLog
            AdminAuditLog.record(
                actor=request.user, action="booking.refund_recorded",
                target=f"Booking #{booking.id} ({booking.mentee.full_name})")
            messages.success(request, "Refund recorded. Remember to process the actual refund in Razorpay if not already done.")
        except BookingError as e:
            messages.error(request, str(e))
        return redirect("staff:booking_detail", booking_id=booking.id)

    return render(request, "bookings/staff_booking_detail.html", {
        "booking": booking, "ledger": booking.ledger_entries.all(), "active_nav": "bookings",
    })


@staff_required
def ledger(request):
    entries = LedgerEntry.objects.select_related("booking", "booking__mentee", "booking__mentor").all()

    # Summary totals.
    def total(t):
        return LedgerEntry.objects.filter(entry_type=t).aggregate(s=Sum("amount"))["s"] or Decimal("0")

    summary = {
        "collected": total(LedgerEntry.TYPE_BOOKING_PAYMENT),
        "platform_fee": total(LedgerEntry.TYPE_PLATFORM_FEE),
        "mentor_earning": total(LedgerEntry.TYPE_MENTOR_EARNING),
        "refunded": total(LedgerEntry.TYPE_REFUND),  # negative
    }
    summary["net_revenue"] = summary["platform_fee"] + summary["refunded"]

    return render(request, "bookings/staff_ledger.html", {
        "entries": entries, "summary": summary, "active_nav": "ledger",
    })


@staff_required
def mentor_earnings_report(request):
    """Per-mentor earnings from completed/confirmed, non-refunded bookings — the
    report the ops team uses to pay mentors manually."""
    rows = {}
    qs = LedgerEntry.objects.filter(
        entry_type=LedgerEntry.TYPE_MENTOR_EARNING,
        booking__is_refunded=False,
    ).select_related("booking", "booking__mentor")

    for e in qs:
        mentor = e.booking.mentor
        r = rows.setdefault(mentor.id, {
            "mentor": mentor, "sessions": 0, "total": Decimal("0")})
        r["sessions"] += 1
        r["total"] += e.amount

    report = sorted(rows.values(), key=lambda r: r["total"], reverse=True)
    grand_total = sum((r["total"] for r in report), Decimal("0"))
    return render(request, "bookings/staff_earnings_report.html", {
        "report": report, "grand_total": grand_total, "active_nav": "ledger",
    })
