"""Public URLs for lead capture."""

from django.urls import path

from . import views

urlpatterns = [
    path("free-consultation/submit/", views.lead_submit, name="lead_submit"),
    path("free-consultation/thanks/", views.lead_thanks, name="lead_thanks"),
]
