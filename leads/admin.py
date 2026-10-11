"""Register Lead in Django admin (/django-admin/) as a raw-data safety net."""

from django.contrib import admin

from .models import Lead


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ("name", "priority", "whatsapp", "domain", "quiz_completed", "is_contacted", "created_at")
    list_filter = ("priority", "quiz_completed", "is_contacted", "domain", "created_at")
    search_fields = ("name", "email", "email_or_linkedin", "whatsapp", "q3_challenge")
    readonly_fields = ("created_at", "quiz_completed_at")
