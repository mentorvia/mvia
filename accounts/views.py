"""Authentication views: signup, email verification, login, logout, password reset."""

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login, logout as auth_logout
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse

from .forms import (
    SignupForm, LoginForm, PasswordResetRequestForm, SetNewPasswordForm,
)
from .models import User, EmailToken
from .emails import send_email


def _absolute_url(request, path):
    """Build a full https URL for email links."""
    return request.build_absolute_uri(path)


def signup(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        form = SignupForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Issue a verification token and email the link.
            token = EmailToken.issue(user, EmailToken.PURPOSE_VERIFY, hours_valid=48)
            link = _absolute_url(request, reverse("verify_email", args=[token.token]))
            send_email(
                to_email=user.email,
                subject="Verify your mVia email",
                template_name="welcome_verify",
                body=(
                    f"Hi {user.get_short_name()},\n\n"
                    f"Welcome to mVia. Please verify your email by visiting:\n{link}\n\n"
                    f"This link expires in 48 hours.\n\n— mVia"
                ),
            )
            messages.success(
                request,
                "Account created! Check your email for a verification link before logging in.",
            )
            # In DEBUG we also show the link on screen so it's testable without email.
            if settings.DEBUG:
                messages.info(request, f"[DEBUG] Verification link: {link}")
            return redirect("login")
    else:
        form = SignupForm()
    return render(request, "accounts/signup.html", {"form": form})


def verify_email(request, token):
    obj = EmailToken.objects.filter(
        token=token, purpose=EmailToken.PURPOSE_VERIFY
    ).first()
    if not obj or not obj.is_valid():
        messages.error(request, "This verification link is invalid or has expired.")
        return redirect("login")
    user = obj.user
    user.is_email_verified = True
    user.save(update_fields=["is_email_verified"])
    obj.mark_used()
    messages.success(request, "Email verified! You can now log in.")
    return redirect("login")


def login_view(request):
    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":
        form = LoginForm(request.POST, request=request)
        if form.is_valid():
            auth_login(request, form.user)
            messages.success(request, f"Welcome back, {form.user.get_short_name()}!")
            # Staff land in the staff console; everyone else in the member dashboard.
            if form.user.is_staff:
                return redirect("staff:overview")
            return redirect("dashboard")
    else:
        form = LoginForm(request=request)
    return render(request, "accounts/login.html", {"form": form})


def logout_view(request):
    auth_logout(request)
    messages.success(request, "You have been logged out.")
    return redirect("home")


def password_reset_request(request):
    if request.method == "POST":
        form = PasswordResetRequestForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"].lower().strip()
            user = User.objects.filter(email=email).first()
            # Always show the same message (don't reveal whether the email exists).
            if user:
                token = EmailToken.issue(user, EmailToken.PURPOSE_RESET, hours_valid=2)
                link = _absolute_url(request, reverse("password_reset_confirm", args=[token.token]))
                send_email(
                    to_email=user.email,
                    subject="Reset your mVia password",
                    template_name="password_reset",
                    body=(
                        f"Hi {user.get_short_name()},\n\n"
                        f"Reset your password by visiting:\n{link}\n\n"
                        f"This link expires in 2 hours. If you didn't request this, ignore it.\n\n— mVia"
                    ),
                )
                if settings.DEBUG:
                    messages.info(request, f"[DEBUG] Reset link: {link}")
            messages.success(
                request,
                "If an account exists for that email, a reset link has been sent.",
            )
            return redirect("login")
    else:
        form = PasswordResetRequestForm()
    return render(request, "accounts/password_reset_request.html", {"form": form})


def password_reset_confirm(request, token):
    obj = EmailToken.objects.filter(
        token=token, purpose=EmailToken.PURPOSE_RESET
    ).first()
    if not obj or not obj.is_valid():
        messages.error(request, "This reset link is invalid or has expired.")
        return redirect("password_reset_request")

    if request.method == "POST":
        form = SetNewPasswordForm(request.POST)
        if form.is_valid():
            user = obj.user
            user.set_password(form.cleaned_data["password"])
            user.save(update_fields=["password"])
            obj.mark_used()
            messages.success(request, "Password updated. You can now log in.")
            return redirect("login")
    else:
        form = SetNewPasswordForm()
    return render(request, "accounts/password_reset_confirm.html", {"form": form})
