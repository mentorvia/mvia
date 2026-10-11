"""
Public free-consultation funnel.

Flow:
  /free-consultation/            → landing: mentor carousel + registration form
      (POST) saves the Lead immediately, emails info@mvia.in, redirects to quiz
  /free-consultation/quiz/<id>/  → the "Navi's Career Navigation Audit" quiz
      (POST) saves answers onto the same lead, computes HOT/WARM/COLD, → thanks
  /free-consultation/thanks/     → thank-you page

Saving after step 1 means we capture the contact even if the person abandons
the quiz. Mirrors the honeypot pattern used by the public mentor-application flow.
Self-contained: touches nothing in the existing apps.
"""

from django.conf import settings
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from .forms import RegistrationForm, QuizForm
from .models import Lead


def _featured_mentors(limit=8):
    """A few approved, available, non-archived mentors for the carousel.
    Self-contained query so this app doesn't depend on another app's view."""
    try:
        from profiles.models import MentorProfile
        return list(
            MentorProfile.objects.filter(
                status=MentorProfile.STATUS_APPROVED, is_available=True,
                user__archived_at__isnull=True,
            ).select_related("user").order_by("-id")[:limit]
        )
    except Exception:  # noqa: BLE001 — carousel is decorative; never break the page
        return []


def consultation_landing(request):
    """Step 1: mentor carousel + registration form."""
    if request.method == "POST":
        # Honeypot: a bot that fills the hidden field gets silent success.
        if request.POST.get("company_site", "").strip():
            return redirect("lead_thanks")

        form = RegistrationForm(request.POST)
        if form.is_valid():
            lead = form.save()
            _notify_team(request, lead)
            return redirect("lead_quiz", lead_id=lead.id)
        messages.error(request, "Please fill in your name to continue.")
    else:
        form = RegistrationForm()

    return render(request, "leads/landing.html", {
        "form": form,
        "mentors": _featured_mentors(),
    })


def lead_quiz(request, lead_id):
    """Step 2: the qualification quiz, saved onto the existing lead."""
    lead = get_object_or_404(Lead, pk=lead_id)

    if request.method == "POST":
        form = QuizForm(request.POST, instance=lead)
        if form.is_valid():
            lead = form.save(commit=False)
            lead.quiz_completed = True
            lead.quiz_completed_at = timezone.now()
            lead.priority = lead.compute_priority()
            lead.save()
            _notify_team_quiz(request, lead)
            return redirect("lead_thanks")
        messages.error(request, "Please review your answers and try again.")
    else:
        form = QuizForm(instance=lead)

    return render(request, "leads/quiz.html", {"form": form, "lead": lead})


def lead_thanks(request):
    return render(request, "leads/thanks.html")


# ---------- Team notifications (never block the save) ----------

def _notify_team(request, lead):
    try:
        from accounts.emails import send_email
        to_email = getattr(settings, "DEFAULT_FROM_EMAIL", "info@mvia.in")
        send_email(
            to_email=to_email,
            subject=f"New lead registered: {lead.name}",
            template_name="lead_registered",
            body=(
                f"A new lead registered on the website (quiz pending):\n\n"
                f"Name: {lead.name}\n"
                f"WhatsApp: {lead.whatsapp or '—'}\n"
                f"Email / LinkedIn: {lead.email_or_linkedin or '—'}\n"
                f"Domain: {lead.get_domain_display() if lead.domain else '—'}"
                f"{' (' + lead.domain_other + ')' if lead.domain_other else ''}\n\n"
                f"— mVia website"
            ),
        )
    except Exception:  # noqa: BLE001
        pass


def _notify_team_quiz(request, lead):
    try:
        from accounts.emails import send_email
        to_email = getattr(settings, "DEFAULT_FROM_EMAIL", "info@mvia.in")
        send_email(
            to_email=to_email,
            subject=f"[{lead.get_priority_display().upper()}] Lead completed quiz: {lead.name}",
            template_name="lead_quiz_completed",
            body=(
                f"{lead.name} completed the Career Navigation Audit.\n\n"
                f"PRIORITY: {lead.get_priority_display()}\n\n"
                f"WhatsApp: {lead.whatsapp or '—'}\n"
                f"Email / LinkedIn: {lead.email_or_linkedin or '—'}\n"
                f"Preferred contact: {lead.q10_contact_pref or '—'}\n\n"
                f"Career stage: {lead.q1_stage or '—'}\n"
                f"Wants help with: {lead.q2_help or '—'}"
                f"{' (' + lead.q2_help_other + ')' if lead.q2_help_other else ''}\n"
                f"Biggest challenge: {lead.q3_challenge or '—'}\n"
                f"Hoping to achieve: {lead.q4_goal or '—'}\n"
                f"Investment intent: {lead.q6_intent or '—'}\n"
                f"Time/week: {lead.q7_time or '—'}\n"
                f"Mentor type wanted: {lead.q8_mentor_type or '—'}\n"
                f"Deciding today via: {lead.q9_decisions or '—'}\n\n"
                f"— mVia website"
            ),
        )
    except Exception:  # noqa: BLE001
        pass
