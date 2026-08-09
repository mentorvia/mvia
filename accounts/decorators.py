"""Auth-related view decorators."""

from functools import wraps

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
