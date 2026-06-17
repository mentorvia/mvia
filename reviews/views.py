"""Mentee review submission for completed sessions."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect, get_object_or_404

from bookings.models import Booking
from .models import Review
from .forms import ReviewForm


@login_required
def leave_review(request, booking_id):
    booking = get_object_or_404(Booking, pk=booking_id)

    # Only the mentee on a COMPLETED booking can review, once.
    if booking.mentee_id != request.user.id:
        messages.error(request, "You can only review your own sessions.")
        return redirect("my_bookings")
    if booking.status != Booking.STATUS_COMPLETED:
        messages.info(request, "You can review a session after it's completed.")
        return redirect("my_bookings")
    if hasattr(booking, "review"):
        messages.info(request, "You've already reviewed this session.")
        return redirect("my_bookings")

    if request.method == "POST":
        form = ReviewForm(request.POST)
        if form.is_valid():
            review = form.save(commit=False)
            review.booking = booking
            review.mentee = request.user
            review.mentor = booking.mentor
            review.save()
            messages.success(request, "Thanks for your feedback!")
            return redirect("my_bookings")
    else:
        form = ReviewForm()

    return render(request, "reviews/leave_review.html", {
        "booking": booking, "form": form,
    })
