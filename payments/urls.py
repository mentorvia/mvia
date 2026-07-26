"""Member-facing payment URLs."""
from django.urls import path
from . import views

urlpatterns = [
    path("my-earnings/", views.my_earnings, name="my_earnings"),
]
