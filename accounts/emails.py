"""
Email sending for mVia.

Provider: Resend (https://resend.com). Sender is info@mvia.in (a domain
verified in Resend).

Modes:
- If RESEND_API_KEY is set (RESEND_ENABLED), real emails send via Resend.
- Otherwise SAFE MODE: emails are not sent, but the full message is logged to
  the server console (visible in Render logs) so flows stay testable.
- Every attempt is recorded in the EmailLog table (recipient, template, status,
  provider message id) — the audit trail the requirements call for.
"""

import logging

from django.conf import settings

logger = logging.getLogger("mvia.email")


def send_email(*, to_email, subject, body, template_name, related_booking=None):
    """
    Send (or, in safe mode, log) a transactional email and record it in the
    email audit log. Returns the EmailLog row created.
    """
    from .models import EmailLog

    # Accept either a Booking object or a raw id; store the id (BigIntegerField).
    booking_id = getattr(related_booking, "id", related_booking)

    log = EmailLog.objects.create(
        recipient=to_email,
        template=template_name,
        subject=subject,
        related_booking=booking_id,
        status=EmailLog.STATUS_PENDING,
    )

    # SAFE MODE: no provider configured — log instead of sending.
    if not settings.RESEND_ENABLED:
        logger.warning(
            "\n===== EMAIL (SAFE MODE — not actually sent) =====\n"
            "To: %s\nSubject: %s\nTemplate: %s\n---\n%s\n"
            "=================================================",
            to_email, subject, template_name, body,
        )
        log.status = EmailLog.STATUS_SAFE_MODE
        log.provider_message_id = "safe-mode-no-send"
        log.save(update_fields=["status", "provider_message_id"])
        return log

    # REAL SEND via Resend.
    try:
        import resend

        resend.api_key = settings.RESEND_API_KEY
        result = resend.Emails.send({
            "from": settings.DEFAULT_FROM_EMAIL,
            "to": [to_email],
            "subject": subject,
            "text": body,
        })
        # Resend returns a dict with an "id" on success.
        message_id = ""
        if isinstance(result, dict):
            message_id = result.get("id", "") or ""
        log.status = EmailLog.STATUS_SENT
        log.provider_message_id = message_id
        log.save(update_fields=["status", "provider_message_id"])
    except Exception as exc:  # noqa: BLE001 — record any failure
        logger.exception("Resend send failed for %s", to_email)
        log.status = EmailLog.STATUS_FAILED
        log.error_detail = str(exc)[:500]
        log.save(update_fields=["status", "error_detail"])

    return log
