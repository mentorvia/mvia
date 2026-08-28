"""Booking and availability views."""
import json
import logging

from django.http import HttpResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from .models import AvailabilitySlot, Booking
from .services import create_booking, confirm_payment, confirm_payment_and_notify, cancel_booking, complete_booking, BookingError
from profiles.models import MentorProfile


# ---------- Mentor: manage availability (weekly pattern + rolling confirm) ----------

@login_required
def my_availability(request):
    if not request.user.is_mentor:
        messages.error(request, "Only approved mentors can set availability.")
        return redirect("dashboard")

    from .models import WeeklyAvailability
    from .services import generate_slots_from_pattern, confirmable_slots

    if request.method == "POST":
        action = request.POST.get("action")

        # 1) Add a weekly pattern entry (weekday + start time).
        if action == "add_pattern":
            weekday = request.POST.get("weekday")
            start_time = request.POST.get("start_time")
            try:
                WeeklyAvailability.objects.get_or_create(
                    mentor=request.user, weekday=int(weekday), start_time=start_time)
                messages.success(request, "Added to your weekly availability.")
            except Exception:
                messages.error(request, "Couldn't add that — check the day and time.")
            return redirect("my_availability")

        # 2) Remove a weekly pattern entry.
        if action == "remove_pattern":
            WeeklyAvailability.objects.filter(
                pk=request.POST.get("pattern_id"), mentor=request.user).delete()
            messages.success(request, "Removed from your weekly availability.")
            return redirect("my_availability")

        # 3) Generate slots for the next 2 weeks from the pattern.
        if action == "generate":
            n = generate_slots_from_pattern(request.user)
            messages.success(request, f"Generated {n} new slot(s) for the next 2 weeks. Confirm the ones you can do below.")
            return redirect("my_availability")

        # 4) Confirm/unconfirm slots (the 2-week checkbox view).
        if action == "confirm_slots":
            confirmed_ids = set(request.POST.getlist("confirm"))
            slots = confirmable_slots(request.user)
            for slot in slots:
                if slot.is_taken:
                    continue  # never touch booked slots
                should_be = str(slot.id) in confirmed_ids
                if slot.is_confirmed != should_be:
                    slot.is_confirmed = should_be
                    slot.save(update_fields=["is_confirmed"])
            messages.success(request, "Your availability for the next 2 weeks is updated.")
            return redirect("my_availability")

    patterns = WeeklyAvailability.objects.filter(mentor=request.user)
    slots = confirmable_slots(request.user)

    # Group slots by date for a clean day-by-day view.
    from itertools import groupby
    slots_by_day = []
    for day, day_slots in groupby(slots, key=lambda s: timezone.localtime(s.start).date()):
        slots_by_day.append((day, list(day_slots)))

    return render(request, "bookings/my_availability.html", {
        "patterns": patterns,
        "weekday_choices": WeeklyAvailability.WEEKDAYS,
        "slots_by_day": slots_by_day,
    })


# ---------- Mentee: book a slot ----------

@login_required
def book_slot(request, slot_id):
    slot = get_object_or_404(AvailabilitySlot, pk=slot_id)

    # Mentee profile must be complete before booking (req 4.2).
    from profiles.views import _get_or_create_mentee_profile
    profile = _get_or_create_mentee_profile(request.user)
    if not profile.is_complete():
        messages.info(request, "Please complete your profile before booking: " +
                      ", ".join(profile.missing_fields()) + ".")
        return redirect("mentee_profile")

    try:
        booking = create_booking(mentee=request.user, slot_id=slot.id)
    except BookingError as e:
        messages.error(request, str(e))
        return redirect("mentor_profile", user_id=slot.mentor_id)
    return redirect("pay_booking", booking_id=booking.id)


@login_required
def pay_booking(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id, mentee=request.user)
    if booking.status != Booking.STATUS_PENDING_PAYMENT:
        messages.info(request, "This booking is already processed.")
        return redirect("my_bookings")

    # SAFE SIMULATION path (only when Razorpay keys are NOT configured).
    if not settings.RAZORPAY_ENABLED:
        if request.method == "POST":
            try:
                confirm_payment_and_notify(booking_id=booking.id, simulated=True)
                messages.success(request, "Payment simulated — your booking is confirmed!")
            except BookingError as e:
                messages.error(request, str(e))
            return redirect("my_bookings")
        return render(request, "bookings/pay.html", {"booking": booking, "simulated": True})

    # LIVE RAZORPAY path.
    from payments.razorpay_client import create_order, verify_payment_signature, mentee_total

    # Callback POST from Razorpay Checkout (contains payment id, order id, signature).
    if request.method == "POST":
        rp_payment_id = request.POST.get("razorpay_payment_id", "")
        rp_order_id = request.POST.get("razorpay_order_id", "")
        rp_signature = request.POST.get("razorpay_signature", "")

        # Verify the payment belongs to THIS booking's order.
        payment = booking.payments.order_by("-created_at").first()
        if not payment or payment.razorpay_order_id != rp_order_id:
            messages.error(request, "Payment could not be matched to your booking. If money was deducted, contact support.")
            return redirect("my_bookings")

        # SECURITY-CRITICAL: verify the signature before confirming anything.
        if not verify_payment_signature(rp_order_id, rp_payment_id, rp_signature):
            payment.status = payment.STATUS_FAILED
            payment.save(update_fields=["status"])
            messages.error(request, "Payment verification failed. If money was deducted, it will be auto-refunded by the bank; please contact support.")
            return redirect("my_bookings")

        try:
            confirm_payment_and_notify(
                booking_id=booking.id, simulated=False,
                razorpay_payment_id=rp_payment_id, razorpay_signature=rp_signature)
            messages.success(request, "Payment successful — your booking is confirmed!")
        except BookingError as e:
            messages.error(request, str(e))
        return redirect("my_bookings")

    # GET: create a Razorpay order and render checkout.
    try:
        order = create_order(booking)
    except Exception as exc:
        import logging
        logging.getLogger("mvia.payments").exception(
            "Razorpay order creation failed for booking %s: %s", booking.id, exc)
        messages.error(request, "Could not start payment right now. Please try again in a moment.")
        return redirect("my_bookings")

    # Save the order id on the payment so we can verify the callback against it.
    payment = booking.payments.order_by("-created_at").first()
    if payment:
        payment.razorpay_order_id = order["id"]
        payment.save(update_fields=["razorpay_order_id"])

    total = mentee_total(booking.amount)
    from decimal import Decimal
    fee_rate = Decimal(str(getattr(settings, "PLATFORM_FEE_RATE", 0.20)))
    fee_amount = (booking.amount * fee_rate).quantize(Decimal("0.01"))
    fee_percent = int(fee_rate * 100)
    return render(request, "bookings/pay.html", {
        "booking": booking, "simulated": False,
        "razorpay_key_id": settings.RAZORPAY_KEY_ID,
        "razorpay_order_id": order["id"],
        "amount_paise": int((total * 100)),
        "total_rupees": total,
        "fee_amount": fee_amount,
        "fee_percent": fee_percent,
    })
@csrf_exempt
@require_POST
def razorpay_webhook(request):
    """
    Server-to-server confirmation from Razorpay. Fires on payment.captured
    regardless of what the mentee's browser did, so a refresh during checkout
    can't leave a paid booking unconfirmed (PAY-018 / BOOK-011).

    Idempotent: confirm_payment's status guard means if the browser callback
    already confirmed this booking, this no-ops safely.
    """
    import hmac
    import hashlib

    secret = getattr(settings, "RAZORPAY_WEBHOOK_SECRET", "")
    if not secret:
        logging.getLogger("mvia.payments").error("Webhook hit but RAZORPAY_WEBHOOK_SECRET not set.")
        return HttpResponse(status=503)

    body = request.body  # raw bytes — must verify against the raw payload
    signature = request.headers.get("X-Razorpay-Signature", "")

    # Verify the webhook signature (HMAC-SHA256 of the raw body with the secret).
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        logging.getLogger("mvia.payments").warning("Razorpay webhook signature mismatch.")
        return HttpResponseBadRequest("bad signature")

    try:
        payload = json.loads(body)
    except ValueError:
        return HttpResponseBadRequest("bad json")

    event = payload.get("event")
    if event != "payment.captured":
        # We only act on captured payments; acknowledge everything else so
        # Razorpay doesn't retry.
        return HttpResponse(status=200)

    # Pull the order + payment ids from the event.
    try:
        entity = payload["payload"]["payment"]["entity"]
        rp_order_id = entity["order_id"]
        rp_payment_id = entity["id"]
    except (KeyError, TypeError):
        return HttpResponseBadRequest("unexpected payload")

    # Find the Payment by order id, then confirm its booking.
    from payments.models import Payment
    payment = Payment.objects.filter(razorpay_order_id=rp_order_id).order_by("-created_at").first()
    if not payment:
        logging.getLogger("mvia.payments").error(
            "Webhook: no Payment for order %s", rp_order_id)
        return HttpResponse(status=200)  # ack — nothing we can do, don't retry forever

    # Already confirmed by the browser callback? confirm_payment's guard will
    # raise BookingError; we treat that as success (idempotent no-op).
    try:
        confirm_payment_and_notify(
            booking_id=payment.booking_id, simulated=False,
            razorpay_payment_id=rp_payment_id, razorpay_signature="")
    except BookingError:
        pass  # already processed — fine
    except Exception:  # noqa: BLE001
        logging.getLogger("mvia.payments").exception(
            "Webhook confirm failed for booking %s", payment.booking_id)
        return HttpResponse(status=500)  # let Razorpay retry

    return HttpResponse(status=200)

# ---------- Both: my bookings ----------

@login_required
def my_bookings(request):
    as_mentee = Booking.objects.filter(mentee=request.user).select_related("mentor", "slot").order_by("-created_at")
    as_mentor = Booking.objects.filter(mentor=request.user).select_related("mentee", "slot").order_by("-created_at") if request.user.is_mentor else None
    return render(request, "bookings/my_bookings.html", {
        "as_mentee": as_mentee, "as_mentor": as_mentor, "now": timezone.now(),
    })


@login_required
def cancel(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id)
    if request.user.id not in (booking.mentee_id, booking.mentor_id):
        messages.error(request, "Not your booking.")
        return redirect("my_bookings")
    if request.method == "POST":
        try:
            cancel_booking(booking_id=booking.id, actor=request.user,
                           reason=request.POST.get("reason", ""))
            messages.success(request, "Booking cancelled.")
        except BookingError as e:
            messages.error(request, str(e))
    return redirect("my_bookings")


@login_required
def complete(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id)
    # Either party can mark complete after the session time.
    if request.user.id not in (booking.mentee_id, booking.mentor_id):
        messages.error(request, "Not your booking.")
        return redirect("my_bookings")
    if request.method == "POST":
        try:
            complete_booking(booking_id=booking.id)
            messages.success(request, "Marked as completed.")
        except BookingError as e:
            messages.error(request, str(e))
    return redirect("my_bookings")


@login_required
def reschedule(request, booking_id):
    """Mentee self-reschedule: pick another open slot of the same mentor."""
    from .services import reschedule_booking, open_slots_for_mentor

    booking = get_object_or_404(Booking, pk=booking_id)
    if request.user.id != booking.mentee_id:
        messages.error(request, "You can only reschedule your own bookings.")
        return redirect("my_bookings")

    if request.method == "POST":
        new_slot_id = request.POST.get("new_slot_id")
        try:
            reschedule_booking(booking_id=booking.id, new_slot_id=new_slot_id, actor=request.user)
            messages.success(request, "Your session has been rescheduled.")
            return redirect("my_bookings")
        except BookingError as e:
            messages.error(request, str(e))
        except Exception:
            messages.error(request, "Could not reschedule. Please pick a valid open slot.")

    slots = open_slots_for_mentor(booking.mentor, exclude_booking=booking)
    return render(request, "bookings/reschedule.html", {
        "booking": booking, "slots": slots,
    })


# ---------- Mentor: approve / decline / suggest ----------

@login_required
def approve(request, booking_id):
    from .services import approve_booking
    booking = get_object_or_404(Booking, pk=booking_id, mentor=request.user)
    if request.method == "POST":
        try:
            approve_booking(booking_id=booking.id, actor=request.user)
            messages.success(request, "Session approved and confirmed.")
        except BookingError as e:
            messages.error(request, str(e))
    return redirect("my_bookings")


@login_required
def decline(request, booking_id):
    from .services import decline_booking
    booking = get_object_or_404(Booking, pk=booking_id, mentor=request.user)
    if request.method == "POST":
        try:
            decline_booking(booking_id=booking.id, actor=request.user,
                            reason=request.POST.get("reason", ""))
            messages.success(request, "Session declined — the mentee will be refunded.")
        except BookingError as e:
            messages.error(request, str(e))
    return redirect("my_bookings")


@login_required
def suggest_time(request, booking_id):
    from .services import suggest_new_slot, open_slots_for_mentor
    booking = get_object_or_404(Booking, pk=booking_id, mentor=request.user)
    if request.method == "POST":
        try:
            suggest_new_slot(booking_id=booking.id,
                             new_slot_id=request.POST.get("new_slot_id"), actor=request.user)
            messages.success(request, "Suggested a new time — the mentee will be notified.")
            return redirect("my_bookings")
        except BookingError as e:
            messages.error(request, str(e))
    slots = open_slots_for_mentor(request.user, exclude_booking=booking)
    return render(request, "bookings/suggest_time.html", {"booking": booking, "slots": slots})


@login_required
def accept_suggestion(request, booking_id):
    from .services import accept_suggested_slot
    booking = get_object_or_404(Booking, pk=booking_id, mentee=request.user)
    if request.method == "POST":
        try:
            accept_suggested_slot(booking_id=booking.id, actor=request.user)
            messages.success(request, "New time accepted — now awaiting mentor confirmation.")
        except BookingError as e:
            messages.error(request, str(e))
    return redirect("my_bookings")


# ---------- Mentor: session wrap-up (meeting link / no-show / recording) ----------

@login_required
def set_link(request, booking_id):
    from .services import set_meet_link
    booking = get_object_or_404(Booking, pk=booking_id, mentor=request.user)
    if request.method == "POST":
        set_meet_link(booking_id=booking.id, link=request.POST.get("meet_link", ""), actor=request.user)
        messages.success(request, "Meeting link saved.")
    return redirect("my_bookings")


@login_required
def no_show(request, booking_id):
    from .services import mark_no_show
    booking = get_object_or_404(Booking, pk=booking_id, mentor=request.user)
    if request.method == "POST":
        try:
            mark_no_show(booking_id=booking.id, actor=request.user)
            messages.success(request, "Marked as a no-show.")
        except BookingError as e:
            messages.error(request, str(e))
    return redirect("my_bookings")


@login_required
def add_recording(request, booking_id):
    from .services import set_recording
    booking = get_object_or_404(Booking, pk=booking_id, mentor=request.user)
    if request.method == "POST":
        try:
            set_recording(
                booking_id=booking.id, actor=request.user,
                recording_url=request.POST.get("recording_url", ""),
                session_notes=request.POST.get("session_notes", ""))
            messages.success(request, "Recording and notes saved.")
        except BookingError as e:
            messages.error(request, str(e))
    return redirect("my_bookings")
