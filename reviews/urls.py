from django.urls import path
from . import views

urlpatterns = [
    path("review/<int:booking_id>/", views.leave_review, name="leave_review"),
]
