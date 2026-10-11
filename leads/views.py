"""
Public lead-capture submit view.

Saves a Lead and emails the team at info@mvia.in (reusing the existing
accounts.emails.send_email helper). Mirrors the honeypot + "thanks" pattern
already used by the public mentor-application flow.

Stage 1: this view handles the POST and shows a simple thank-you page. The
pretty bottom-strip survey and mentor carousel are wired in Stage 2; this view
already supports both a normal POST (renders thanks) so it works on its own.
"""

from django.conf import settings
from django.contrib import messages
from django.shortcuts import render, redirect

from .forms import LeadForm


def lead_submit(request):
    """Handle the free-consultation survey submission."""
    if request.method != "POST":
        # Nothing to show on GET — send people to the home page.
        return redirect("home")

    # Honeypot: a bot that fills the hidden field gets a silent success (we
    # create nothing), so its script sees no error to adapt to.
    if request.POST.get("company_site", "").strip():
        return redirect("lead_thanks")

    form = LeadForm(request.POST)
    if form.is_valid():
        lead = form.save()
        _notify_team(request, lead)
        return redirect("lead_thanks")

    # If the form is invalid, bounce back home with a message. (Stage 2's inline
    # strip will show field errors in place; for Stage 1 this keeps it simple.)
    messages.error(request, "Please check the form and try again.")
    return redirect("home")


def lead_thanks(request):
    """Simple thank-you page shown after a successful submission."""
    return render(request, "leads/thanks.html")


def _notify_team(request, lead):
    """Email the mVia team that a new lead came in. Never blocks the save."""
    try:
        from accounts.emails import send_email

        to_email = getattr(settings, "DEFAULT_FROM_EMAIL", "info@mvia.in")
        body = (
            f"New free-consultation lead from the website:\n\n"
            f"Name: {lead.name}\n"
            f"Email: {lead.email}\n"
            f"Phone: {lead.phone or '—'}\n"
            f"Current role/status: {lead.current_role or '—'}\n"
            f"Field of interest: {lead.field_of_interest or '—'}\n"
            f"Wants help with: {lead.goal or '—'}\n\n"
            f"Follow up with them to guide on the right mentor.\n\n— mVia website"
        )
        send_email(
            to_email=to_email,
            subject=f"New lead: {lead.name}",
            template_name="lead_received",
            body=body,
        )
    except Exception:  # noqa: BLE001 — a mail hiccup must never lose the lead
        pass
