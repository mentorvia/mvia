"""Views for the core app: homepage, health check, and the logged-in dashboard."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.http import JsonResponse


def home(request):
    return render(request, "home.html")


def health(request):
    return JsonResponse({"status": "ok"})


@login_required
def dashboard(request):
    """The signed-in landing area. Grows as we add features."""
    return render(request, "dashboard.html")
