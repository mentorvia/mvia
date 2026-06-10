"""Views for the core app. Right now: a branded homepage and a health check."""

from django.shortcuts import render
from django.http import JsonResponse


def home(request):
    """The public landing page."""
    return render(request, "home.html")


def health(request):
    """A simple endpoint Render can ping to confirm the app is alive."""
    return JsonResponse({"status": "ok"})
