"""
Email sending for mVia.

IMPORTANT — this runs in SAFE MODE until SendGrid is configured:
- If SENDGRID is not enabled (no API key set), emails are NOT actually sent.
  Instead the message is logged to the server console (visible in Render logs).
  This lets the whole signup / reset flow be fully testable today.
- Every attempt is recorded in the EmailLog table (the audit log the
  requirements call for: recipient, template, status, provider message id).
- The day a real SENDGRID_API_KEY is added, real sending switches on with
  no other code changes needed.
"""

import logging

from django.conf import settings

logger = logging.getLogger("mvia.email")


def send_email(*, to_email, subject, body, template_name, related_booking=None):
    """
    Send (or, in safe mode, log) a transactional email and record it in the
    email audit log. Returns the EmailLog row created.
    """
    # Imported here to avoid a circular import at module load time.
    from .models import EmailLog

    log = EmailLog.objects.create(
        recipient=to_email,
        template=template_name,
        subject=subject,
        related_booking=related_booking,
        status=EmailLog.STATUS_PENDING,
    )

    if not settings.SENDGRID_ENABLED:
        # SAFE MODE: don't send; log to console so links are testable.
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

    # REAL SEND via SendGrid (only reached once an API key is configured).
    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail

        message = Mail(
            from_email=settings.DEFAULT_FROM_EMAIL,
            to_emails=to_email,
            subject=subject,
            plain_text_content=body,
        )
        client = SendGridAPIClient(settings.SENDGRID_API_KEY)
        response = client.send(message)
        log.status = EmailLog.STATUS_SENT
        log.provider_message_id = response.headers.get("X-Message-Id", "") if response.headers else ""
        log.save(update_fields=["status", "provider_message_id"])
    except Exception as exc:  # noqa: BLE001 — we want to record any failure
        logger.exception("SendGrid send failed for %s", to_email)
        log.status = EmailLog.STATUS_FAILED
        log.error_detail = str(exc)[:500]
        log.save(update_fields=["status", "error_detail"])

    return log
