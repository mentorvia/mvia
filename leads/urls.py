"""Public URLs for the free-consultation funnel."""

from django.urls import path

from . import views

urlpatterns = [
    path("free-consultation/", views.consultation_landing, name="consultation_landing"),
    path("free-consultation/quiz/<int:lead_id>/", views.lead_quiz, name="lead_quiz"),
    path("free-consultation/thanks/", views.lead_thanks, name="lead_thanks"),
]
