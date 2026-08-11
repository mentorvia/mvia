"""Forms for signup, login, and password reset."""

from django import forms
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .models import User


class SignupForm(forms.Form):
    full_name = forms.CharField(max_length=150, label=_("Full name"))
    email = forms.EmailField(label=_("Email"))
    password = forms.CharField(widget=forms.PasswordInput, label=_("Password"))
    password_confirm = forms.CharField(widget=forms.PasswordInput, label=_("Confirm password"))

    def clean_email(self):
        email = self.cleaned_data["email"].lower().strip()
        if User.objects.filter(email=email).exists():
            raise ValidationError("An account with this email already exists.")
        return email

    def clean_password(self):
        password = self.cleaned_data["password"]
        validate_password(password)  # applies Django's strength rules
        return password

    def clean(self):
        cleaned = super().clean()
        pw = cleaned.get("password")
        pw2 = cleaned.get("password_confirm")
        if pw and pw2 and pw != pw2:
            self.add_error("password_confirm", "Passwords do not match.")
        return cleaned

    def save(self):
        return User.objects.create_user(
            email=self.cleaned_data["email"],
            password=self.cleaned_data["password"],
            full_name=self.cleaned_data["full_name"],
        )


class LoginForm(forms.Form):
    email = forms.EmailField(label=_("Email"))
    password = forms.CharField(widget=forms.PasswordInput, label=_("Password"))

    def __init__(self, *args, request=None, **kwargs):
        self.request = request
        self.user = None
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        email = (cleaned.get("email") or "").lower().strip()
        password = cleaned.get("password")
        if email and password:
            user = authenticate(self.request, username=email, password=password)
            if user is None:
                raise ValidationError("Incorrect email or password.")
            # Checked right after a successful password check (not before —
            # revealing account state to an unauthenticated guesser would be
            # a user-enumeration leak) but before anything else happens with
            # this login: no session gets created for an archived account.
            if user.archived_at:
                raise ValidationError(
                    "Your account has been archived. Contact support if this is unexpected."
                )
            if not user.is_email_verified:
                raise ValidationError(
                    "Please verify your email before logging in. "
                    "Check your inbox for the verification link."
                )
            self.user = user
        return cleaned


class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField(label=_("Email"))


class SetNewPasswordForm(forms.Form):
    password = forms.CharField(widget=forms.PasswordInput, label=_("New password"))
    password_confirm = forms.CharField(widget=forms.PasswordInput, label=_("Confirm new password"))

    def clean_password(self):
        password = self.cleaned_data["password"]
        validate_password(password)
        return password

    def clean(self):
        cleaned = super().clean()
        pw = cleaned.get("password")
        pw2 = cleaned.get("password_confirm")
        if pw and pw2 and pw != pw2:
            self.add_error("password_confirm", "Passwords do not match.")
        return cleaned
