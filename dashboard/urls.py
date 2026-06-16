"""URL routes for the custom staff admin."""

from django.urls import path
from . import views
from interests import staff_views as interest_views
from profiles import staff_views as profile_views
from profiles import profile_editor
from bookings import staff_views as booking_views

app_name = "staff"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("users/", views.users_list, name="users"),
    path("users/<int:user_id>/", views.user_detail, name="user_detail"),
    path("emails/", views.email_log, name="emails"),
    # Bookings & money
    path("bookings/", booking_views.bookings_list, name="bookings"),
    path("bookings/<int:booking_id>/", booking_views.booking_detail, name="booking_detail"),
    path("ledger/", booking_views.ledger, name="ledger"),
    path("earnings/", booking_views.mentor_earnings_report, name="earnings_report"),
    path("payouts/", booking_views.payout_history, name="payout_history"),
    # Interests
    path("interests/", interest_views.interests_list, name="interests"),
    path("interests/add/", interest_views.interest_add, name="interest_add"),
    path("interests/<int:interest_id>/edit/", interest_views.interest_edit, name="interest_edit"),
    path("interests/<int:interest_id>/delete/", interest_views.interest_delete, name="interest_delete"),
    path("interests/custom/", interest_views.custom_review, name="custom_review"),
    # Mentors
    path("mentors/", profile_views.mentor_queue, name="mentor_queue"),
    path("mentors/add-placeholder/", profile_views.add_placeholder_mentor, name="add_placeholder_mentor"),
    path("mentors/<int:mentor_id>/", profile_views.mentor_review, name="mentor_review"),
    path("mentors/<int:mentor_id>/edit-profile/", profile_editor.edit_mentor_profile, name="edit_mentor_profile"),
    # Audit log
    path("audit/", profile_views.audit_log, name="audit"),
]
