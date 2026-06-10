"""
User account model for mVia.

Key design decisions (from the requirements):
- Login is by EMAIL, not a username. Email must be unique.
- A single account can be BOTH a mentee and a mentor. Everyone starts as a
  mentee; they may later apply to become a mentor on the same account.
- Passwords are hashed by Django automatically (never stored in plaintext).
- We track email verification explicitly and block login until verified.
"""

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    """Tells Django how to create users and superusers using email (not username)."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        # Normalize lowercases the domain part so emails compare consistently.
        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra_fields)
        user.set_password(password)  # hashes the password
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        # Admin users (mVia staff) created via the command line.
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_email_verified", True)  # admins skip verification
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """The core account. One per person."""

    full_name = models.CharField(max_length=150)
    email = models.EmailField(unique=True)

    # Role flags. Everyone is a mentee; is_mentor flips on after approval.
    is_mentee = models.BooleanField(default=True)
    is_mentor = models.BooleanField(default=False)

    # Email verification. Login is blocked until this is True.
    is_email_verified = models.BooleanField(default=False)

    # Django admin / permissions plumbing.
    is_active = models.BooleanField(default=True)   # set False to disable an account
    is_staff = models.BooleanField(default=False)   # can access Django admin

    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"          # log in with email
    REQUIRED_FIELDS = ["full_name"]   # prompted when creating a superuser

    class Meta:
        ordering = ["-date_joined"]

    def __str__(self):
        return f"{self.full_name} <{self.email}>"

    def get_short_name(self):
        return self.full_name.split(" ")[0] if self.full_name else self.email


import secrets


def _make_token():
    """Generate a long, unguessable random token for email links."""
    return secrets.token_urlsafe(32)


class EmailToken(models.Model):
    """
    A one-time token sent in an email link, for either verifying an email
    address or resetting a password. Tokens expire and can only be used once.
    """

    PURPOSE_VERIFY = "verify"
    PURPOSE_RESET = "reset"
    PURPOSE_CHOICES = [
        (PURPOSE_VERIFY, "Email verification"),
        (PURPOSE_RESET, "Password reset"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="email_tokens")
    purpose = models.CharField(max_length=10, choices=PURPOSE_CHOICES)
    token = models.CharField(max_length=64, unique=True, default=_make_token)
    created_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["token"])]

    def is_valid(self):
        """A token is valid if it hasn't been used and hasn't expired."""
        return self.used_at is None and timezone.now() < self.expires_at

    def mark_used(self):
        self.used_at = timezone.now()
        self.save(update_fields=["used_at"])

    @classmethod
    def issue(cls, user, purpose, hours_valid=24):
        """Create a fresh token for a user, invalidating older unused ones."""
        # Invalidate any prior unused tokens of the same purpose.
        cls.objects.filter(user=user, purpose=purpose, used_at__isnull=True).update(
            used_at=timezone.now()
        )
        return cls.objects.create(
            user=user,
            purpose=purpose,
            expires_at=timezone.now() + timezone.timedelta(hours=hours_valid),
        )

    def __str__(self):
        return f"{self.get_purpose_display()} for {self.user.email}"


class EmailLog(models.Model):
    """
    Audit log of every email the system attempts to send (requirement 7).
    Records recipient, which template, status, and the provider message id.
    """

    STATUS_PENDING = "pending"
    STATUS_SENT = "sent"
    STATUS_FAILED = "failed"
    STATUS_SAFE_MODE = "safe_mode"  # logged but not sent (SendGrid not configured)
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_SENT, "Sent"),
        (STATUS_FAILED, "Failed"),
        (STATUS_SAFE_MODE, "Safe mode (not sent)"),
    ]

    recipient = models.EmailField()
    template = models.CharField(max_length=80)
    subject = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    provider_message_id = models.CharField(max_length=255, blank=True)
    error_detail = models.TextField(blank=True)
    # Loosely linked to a booking later (kept as a nullable id so accounts app
    # doesn't need to import the bookings app). Wired up properly when bookings exist.
    related_booking = models.BigIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.template} -> {self.recipient} ({self.status})"
