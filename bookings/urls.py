"""Booking URLs."""
from django.urls import path
from . import views

urlpatterns = [
    path("availability/", views.my_availability, name="my_availability"),
    path("availability/<int:slot_id>/delete/", views.delete_slot, name="delete_slot"),
    path("book/<int:slot_id>/", views.book_slot, name="book_slot"),
    path("pay/<int:booking_id>/", views.pay_booking, name="pay_booking"),
    path("my-bookings/", views.my_bookings, name="my_bookings"),
    path("booking/<int:booking_id>/cancel/", views.cancel, name="cancel_booking"),
    path("booking/<int:booking_id>/complete/", views.complete, name="complete_booking"),
    path("booking/<int:booking_id>/reschedule/", views.reschedule, name="reschedule_booking"),
]
