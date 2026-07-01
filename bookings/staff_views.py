"""Staff console: bookings overview, refunds, and the money ledger."""

from decimal import Decimal
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Sum
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from .models import Booking
from .services import record_refund, BookingError
from payments.models import LedgerEntry, Payout


def staff_required(view):
    return user_passes_test(lambda u: u.is_authenticated and u.is_staff, login_url="login")(view)


@staff_required
def bookings_list(request):
    from core.pagination import paginate, querystring_without_page
    from django.db.models import Q

    bookings = Booking.objects.select_related("mentee", "mentor", "slot").order_by("-created_at")

    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    if q:
        bookings = bookings.filter(
            Q(mentee__full_name__icontains=q) | Q(mentor__full_name__icontains=q))
    if status == "refunded":
        bookings = bookings.filter(is_refunded=True)
    elif status:
        bookings = bookings.filter(status=status)

    status_opts = [{"value": v, "label": l, "selected": status == v}
                   for v, l in Booking.STATUS_CHOICES]
    status_opts.append({"value": "refunded", "label": "Refunded", "selected": status == "refunded"})

    page_obj = paginate(request, bookings)
    return render(request, "bookings/staff_bookings.html", {
        "bookings": page_obj, "page_obj": page_obj,
        "qs": querystring_without_page(request),
        "search_value": q, "search_placeholder": "Search mentee or mentor…",
        "filters": [{"name": "status", "label": "Status", "options": status_opts}],
        "has_active": bool(q or status),
        "active_nav": "bookings",
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

    if request.method == "POST" and request.POST.get("action") == "reschedule":
        from .services import reschedule_booking
        try:
            reschedule_booking(
                booking_id=booking.id,
                new_slot_id=request.POST.get("new_slot_id"),
                actor=request.user)
            messages.success(request, "Booking rescheduled.")
        except BookingError as e:
            messages.error(request, str(e))
        except Exception:
            messages.error(request, "Could not reschedule — pick a valid open slot.")
        return redirect("staff:booking_detail", booking_id=booking.id)

    from .services import open_slots_for_mentor
    reschedule_slots = (
        open_slots_for_mentor(booking.mentor, exclude_booking=booking)
        if booking.status == Booking.STATUS_CONFIRMED else None)

    return render(request, "bookings/staff_booking_detail.html", {
        "reschedule_slots": reschedule_slots,
        "booking": booking, "ledger": booking.ledger_entries.all(), "active_nav": "bookings",
    })


@staff_required
def ledger(request):
    from core.pagination import paginate, querystring_without_page
    from django.db.models import Q

    entries = LedgerEntry.objects.select_related("booking", "booking__mentee", "booking__mentor").all()

    q = request.GET.get("q", "").strip()
    etype = request.GET.get("type", "").strip()
    if q:
        entries = entries.filter(
            Q(booking__mentor__full_name__icontains=q) |
            Q(booking__mentee__full_name__icontains=q) |
            Q(external_reference__icontains=q))
    if etype:
        entries = entries.filter(entry_type=etype)

    # Summary totals (over ALL entries, not just current filter/page).
    def total(t):
        return LedgerEntry.objects.filter(entry_type=t).aggregate(s=Sum("amount"))["s"] or Decimal("0")

    summary = {
        "collected": total(LedgerEntry.TYPE_BOOKING_PAYMENT),
        "platform_fee": total(LedgerEntry.TYPE_PLATFORM_FEE),
        "mentor_earning": total(LedgerEntry.TYPE_MENTOR_EARNING),
        "refunded": total(LedgerEntry.TYPE_REFUND),
    }
    summary["net_revenue"] = summary["platform_fee"] + summary["refunded"]

    type_opts = [{"value": v, "label": l, "selected": etype == v}
                 for v, l in LedgerEntry.TYPE_CHOICES]
    page_obj = paginate(request, entries)
    return render(request, "bookings/staff_ledger.html", {
        "entries": page_obj, "page_obj": page_obj, "summary": summary,
        "qs": querystring_without_page(request),
        "search_value": q, "search_placeholder": "Search mentor, mentee, or reference…",
        "filters": [{"name": "type", "label": "Type", "options": type_opts}],
        "has_active": bool(q or etype),
        "active_nav": "ledger",
    })


def _unpaid_earnings_qs():
    """Mentor-earning ledger entries that are: from COMPLETED sessions,
    not refunded, and not yet part of a payout."""
    return LedgerEntry.objects.filter(
        entry_type=LedgerEntry.TYPE_MENTOR_EARNING,
        payout__isnull=True,
        booking__is_refunded=False,
        booking__status=Booking.STATUS_COMPLETED,
    ).select_related("booking", "booking__mentor")


def _build_earnings_rows(qs):
    rows = {}
    for e in qs:
        mentor = e.booking.mentor
        r = rows.setdefault(mentor.id, {
            "mentor": mentor, "sessions": 0, "total": Decimal("0"),
            "earliest": e.created_at, "latest": e.created_at})
        r["sessions"] += 1
        r["total"] += e.amount
        r["earliest"] = min(r["earliest"], e.created_at)
        r["latest"] = max(r["latest"], e.created_at)
    return sorted(rows.values(), key=lambda r: r["total"], reverse=True)


@staff_required
def mentor_earnings_report(request):
    """Weekly payout report: UNPAID earnings from completed, non-refunded
    sessions, per mentor. Ops ticks mentors, pays them, marks them paid."""
    import csv
    from django.http import HttpResponse

    qs = _unpaid_earnings_qs()

    # CSV export of the current unpaid report.
    if request.GET.get("export") == "csv":
        report = _build_earnings_rows(qs)
        resp = HttpResponse(content_type="text/csv")
        resp["Content-Disposition"] = f'attachment; filename="mentor_earnings_{timezone.now():%Y%m%d}.csv"'
        w = csv.writer(resp)
        w.writerow(["Mentor", "Email", "Sessions", "Amount (INR)", "Earliest", "Latest"])
        for r in report:
            w.writerow([r["mentor"].full_name, r["mentor"].email if r["mentor"].has_real_email() else "",
                        r["sessions"], r["total"],
                        r["earliest"].strftime("%Y-%m-%d"), r["latest"].strftime("%Y-%m-%d")])
        return resp

    # Mark selected mentors as paid -> create payout runs.
    if request.method == "POST" and request.POST.get("action") == "mark_paid":
        mentor_ids = request.POST.getlist("mentor_ids")
        reference = request.POST.get("reference", "").strip()
        paid_count = 0
        for mid in mentor_ids:
            entries = list(_unpaid_earnings_qs().filter(booking__mentor_id=mid))
            if not entries:
                continue
            total = sum((e.amount for e in entries), Decimal("0"))
            dates = [e.created_at.date() for e in entries]
            payout = Payout.objects.create(
                mentor_id=mid, amount=total, sessions_count=len(entries),
                period_start=min(dates), period_end=max(dates),
                reference=reference, created_by=request.user)
            # Link those specific entries to this payout (marks them paid).
            LedgerEntry.objects.filter(id__in=[e.id for e in entries]).update(payout=payout)
            paid_count += 1
            from auditlog.models import AdminAuditLog
            AdminAuditLog.record(
                actor=request.user, action="mentor.payout_recorded",
                target=f"₹{total} to mentor #{mid} ({len(entries)} sessions)")
        if paid_count:
            messages.success(request, f"Recorded payout for {paid_count} mentor(s). They're cleared from the report.")
        else:
            messages.info(request, "No mentors selected (or nothing unpaid).")
        return redirect("staff:earnings_report")

    report = _build_earnings_rows(qs)
    grand_total = sum((r["total"] for r in report), Decimal("0"))
    # Overall date span of unpaid earnings, for sanity-checking the week.
    span_start = min((r["earliest"] for r in report), default=None)
    span_end = max((r["latest"] for r in report), default=None)
    return render(request, "bookings/staff_earnings_report.html", {
        "report": report, "grand_total": grand_total,
        "span_start": span_start, "span_end": span_end,
        "active_nav": "ledger",
    })


@staff_required
def payout_history(request):
    """Past payout runs, for the record."""
    from core.pagination import paginate, querystring_without_page
    payouts = Payout.objects.select_related("mentor", "created_by").all()
    page_obj = paginate(request, payouts)
    return render(request, "bookings/staff_payout_history.html", {
        "payouts": page_obj, "page_obj": page_obj,
        "qs": querystring_without_page(request), "active_nav": "ledger",
    })
