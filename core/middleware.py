"""
Custom middleware for mVia.
"""


class NoCacheForAuthenticatedMiddleware:
    """
    Tell the browser never to store a cached copy of pages served to a
    logged-in user, so pressing Back (or reopening a URL) always re-fetches
    the current state from the server instead of showing a stale snapshot.

    Fixes the class of "Back button shows the old/pending state after an
    action already completed" bugs (e.g. approve a booking, press Back, still
    see it as pending). Only applies to authenticated responses — anonymous,
    cacheable pages (home, marketing) are left alone.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            # no-store: don't cache at all. no-cache + must-revalidate: even if
            # something caches it, revalidate with the server before reuse.
            response["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response["Pragma"] = "no-cache"
            response["Expires"] = "0"
        return response
