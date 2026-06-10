"""Makes the pending-mentor count available to all staff templates for the nav badge."""

from profiles.models import MentorProfile


def staff_badges(request):
    if request.user.is_authenticated and request.user.is_staff:
        return {"pending_mentor_count": MentorProfile.objects.filter(
            status=MentorProfile.STATUS_PENDING).count()}
    return {}
