"""Auth-related view decorators."""

from functools import wraps

from django.contrib import messages
from django.contrib.auth import logout as auth_logout
from django.shortcuts import redirect


def redirect_if_must_change_password(view):
    """
    Send a user with a pending forced password change (see User.must_change_password)
    to the set-password page instead of the wrapped view. Applied to the member
    dashboard entry point so a freshly-activated mentor can't reach it — by
    following a stale link, a browser back button, or typing the URL directly —
    while still holding their system-generated temporary password.
    """
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated and request.user.must_change_password:
            return redirect("force_set_password")
        return view(request, *args, **kwargs)
    return wrapper


def redirect_if_archived(view):
    """
    An archived account shouldn't retain a live session — login itself is
    blocked (accounts.forms.LoginForm), but if an admin archives a user who's
    already logged in, this catches them on their next request to a guarded
    entry point rather than leaving a stale session that can still reach the
    dashboard or the set-password flow. Logs them out outright, since there's
    no valid in-app place for an archived session to land.
    """
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_archived:
            auth_logout(request)
            messages.error(
                request,
                "Your account has been archived. Contact support if this is unexpected.")
            return redirect("login")
        return view(request, *args, **kwargs)
    return wrapper
