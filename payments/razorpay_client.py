"""
Razorpay integration helpers.

The mentee pays: mentor rate + platform fee (fee added on top). We create a
Razorpay Order for that total, render Razorpay Checkout, and after payment we
VERIFY the signature server-side before confirming the booking. Signature
verification is what proves the payment is genuine and untampered — never
confirm a booking without it.

Keys come from environment variables (RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET),
never hardcoded.
"""

from decimal import Decimal

from django.conf import settings


def _client():
    import razorpay
    return razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))


def mentee_total(mentor_rate):
    """What the mentee actually pays: rate + platform fee (added on top)."""
    fee_rate = Decimal(str(getattr(settings, "PLATFORM_FEE_RATE", 0.20)))
    fee = (Decimal(mentor_rate) * fee_rate).quantize(Decimal("0.01"))
    return Decimal(mentor_rate) + fee


def create_order(booking):
    """
    Create a Razorpay Order for a booking's total. Returns the order dict.
    Razorpay works in paise (integer), so ₹24.00 -> 2400.
    """
    total = mentee_total(booking.amount)
    amount_paise = int((total * 100).to_integral_value())
    client = _client()
    try:
        order = client.order.create({
            "amount": amount_paise,
            "currency": "INR",
            "receipt": f"booking_{booking.id}",
            "notes": {
                "booking_id": str(booking.id),
                "mentee": booking.mentee.email,
                "mentor": booking.mentor.full_name,
            },
        })
        return order
    except Exception as exc:
        import logging
        logging.getLogger("mvia.payments").error(
            "Razorpay create_order failed (amount_paise=%s, key_id_prefix=%s): %r",
            amount_paise,
            (settings.RAZORPAY_KEY_ID or "")[:12],
            exc,
        )
        raise


def verify_payment_signature(razorpay_order_id, razorpay_payment_id, razorpay_signature):
    """
    Verify the payment signature Razorpay returns after checkout. Returns True
    if genuine, False otherwise. This is the security-critical step.
    """
    client = _client()
    try:
        client.utility.verify_payment_signature({
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": razorpay_payment_id,
            "razorpay_signature": razorpay_signature,
        })
        return True
    except Exception:
        return False
