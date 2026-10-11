"""Register Lead in Django admin (/django-admin/) as a raw-data safety net."""

from django.contrib import admin

from .models import Lead


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "phone", "field_of_interest", "is_contacted", "created_at")
    list_filter = ("is_contacted", "created_at")
    search_fields = ("name", "email", "phone", "field_of_interest", "goal")
    readonly_fields = ("created_at",)
