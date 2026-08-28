"""
Shared field validators for the mentor profile editors.

Used by both the staff editor (profiles/profile_editor.py -> MentorRichForm)
and the member editor (profiles/member_profile_editor.py -> PresentationForm /
ContactForm), so the rules are defined in exactly one place.
"""

from urllib.parse import urlparse

from django import forms


# --- Limits ---
BIO_MAX = 1500
URL_MAX = 300
PHOTO_MAX_BYTES = 5 * 1024 * 1024  # 5 MB
PHOTO_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
PHOTO_ALLOWED_EXTS = (".jpg", ".jpeg", ".png", ".webp")


def validate_bio(bio):
    """MEP-017: cap the mentor bio length."""
    bio = (bio or "").strip()
    if len(bio) > BIO_MAX:
        raise forms.ValidationError(
            f"Please keep your bio under {BIO_MAX} characters (currently {len(bio)}).")
    return bio


def validate_linkedin_url(url):
    """
    MEP-046: LinkedIn URL is optional, but if given must be a linkedin.com link
    of a sane length.
    """
    url = (url or "").strip()
    if not url:
        return url  # optional
    if len(url) > URL_MAX:
        raise forms.ValidationError(f"Please keep the URL under {URL_MAX} characters.")
    host = (urlparse(url).netloc or "").lower()
    if not (host == "linkedin.com" or host.endswith(".linkedin.com")):
        raise forms.ValidationError(
            "Please enter a valid LinkedIn URL (e.g. https://linkedin.com/in/your-name).")
    return url


def validate_website_url(url):
    """
    MEP-047: website URL is optional, but if given must use http/https (reject
    unsafe schemes like javascript: or data:) and be of a sane length.
    """
    url = (url or "").strip()
    if not url:
        return url  # optional
    if len(url) > URL_MAX:
        raise forms.ValidationError(f"Please keep the URL under {URL_MAX} characters.")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise forms.ValidationError("Please enter a valid http(s) website URL.")
    if not parsed.netloc:
        raise forms.ValidationError("Please enter a complete website URL, including https://.")
    return url


def validate_photo(photo):
    """
    MEP-015: restrict profile photos to JPG/PNG/WebP and cap the file size. Only
    runs when a NEW file is uploaded; leaving the field untouched keeps the
    existing photo safe.
    """
    # When no new file is uploaded, `photo` is the existing FieldFile (or None).
    # A newly uploaded file exposes `content_type` and `size`; an unchanged
    # existing file does not, so skip validation in that case.
    content_type = getattr(photo, "content_type", None)
    if content_type is None:
        return photo  # no new upload — leave the current photo untouched

    size = getattr(photo, "size", 0)
    if size > PHOTO_MAX_BYTES:
        mb = PHOTO_MAX_BYTES // (1024 * 1024)
        raise forms.ValidationError(f"Image is too large. Please upload a file under {mb} MB.")

    name = (getattr(photo, "name", "") or "").lower()
    type_ok = content_type in PHOTO_ALLOWED_TYPES
    ext_ok = name.endswith(PHOTO_ALLOWED_EXTS)
    if not (type_ok and ext_ok):
        raise forms.ValidationError("Please upload a JPG, PNG or WebP image.")
    return photo
