"""Booking and availability views."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from .models import AvailabilitySlot, Booking
from .forms import SlotForm
from .services import create_booking, confirm_payment, cancel_booking, complete_booking, BookingError
from profiles.models import MentorProfile


# ---------- Mentor: manage availability ----------

@login_required
def my_availability(request):
    if not request.user.is_mentor:
        messages.error(request, "Only approved mentors can set availability.")
        return redirect("dashboard")

    if request.method == "POST":
        form = SlotForm(request.POST)
        if form.is_valid():
            try:
                AvailabilitySlot.objects.create(
                    mentor=request.user,
                    start=form.cleaned_data["start_dt"],
                    end=form.cleaned_data["end_dt"],
                )
                messages.success(request, "Slot added.")
            except Exception:
                messages.error(request, "You already have a slot at that time.")
            return redirect("my_availability")
    else:
        form = SlotForm()

    upcoming = request.user.availability_slots.filter(start__gt=timezone.now()).order_by("start")
    return render(request, "bookings/my_availability.html", {
        "form": form, "slots": upcoming,
    })


@login_required
def delete_slot(request, slot_id):
    slot = get_object_or_404(AvailabilitySlot, pk=slot_id, mentor=request.user)
    if request.method == "POST":
        if slot.is_taken:
            messages.error(request, "Can't delete — this slot is booked.")
        else:
            slot.delete()
            messages.success(request, "Slot removed.")
    return redirect("my_availability")


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
                confirm_payment(booking_id=booking.id, simulated=True)
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
            confirm_payment(
                booking_id=booking.id, simulated=False,
                razorpay_payment_id=rp_payment_id, razorpay_signature=rp_signature)
            messages.success(request, "Payment successful — your booking is confirmed!")
        except BookingError as e:
            messages.error(request, str(e))
        return redirect("my_bookings")

    # GET: create a Razorpay order and render checkout.
    try:
        order = create_order(booking)
    except Exception:
        messages.error(request, "Could not start payment right now. Please try again in a moment.")
        return redirect("my_bookings")

    # Save the order id on the payment so we can verify the callback against it.
    payment = booking.payments.order_by("-created_at").first()
    if payment:
        payment.razorpay_order_id = order["id"]
        payment.save(update_fields=["razorpay_order_id"])

    total = mentee_total(booking.amount)
    return render(request, "bookings/pay.html", {
        "booking": booking, "simulated": False,
        "razorpay_key_id": settings.RAZORPAY_KEY_ID,
        "razorpay_order_id": order["id"],
        "amount_paise": int((total * 100)),
        "total_rupees": total,
    })


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
