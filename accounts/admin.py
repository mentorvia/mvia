"""Admin registration for accounts, so mVia staff can manage users."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserChangeForm, UserCreationForm

from .models import User, EmailToken, EmailLog


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ["-date_joined"]
    list_display = ["email", "full_name", "is_mentee", "is_mentor",
                    "is_email_verified", "is_staff", "date_joined"]
    list_filter = ["is_mentor", "is_email_verified", "is_staff", "is_active"]
    search_fields = ["email", "full_name"]
    readonly_fields = ["date_joined", "last_login"]

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal", {"fields": ("full_name",)}),
        ("Roles", {"fields": ("is_mentee", "is_mentor", "is_email_verified")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser",
                                    "groups", "user_permissions")}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "full_name", "password1", "password2"),
        }),
    )


@admin.register(EmailToken)
class EmailTokenAdmin(admin.ModelAdmin):
    list_display = ["user", "purpose", "created_at", "expires_at", "used_at"]
    list_filter = ["purpose"]
    search_fields = ["user__email"]


@admin.register(EmailLog)
class EmailLogAdmin(admin.ModelAdmin):
    list_display = ["recipient", "template", "status", "created_at"]
    list_filter = ["status", "template"]
    search_fields = ["recipient", "subject"]
    readonly_fields = ["recipient", "template", "subject", "status",
                       "provider_message_id", "error_detail", "related_booking", "created_at"]
