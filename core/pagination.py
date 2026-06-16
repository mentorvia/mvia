"""Shared helpers for staff list pages: pagination + querystring preservation."""

from django.core.paginator import Paginator

PER_PAGE = 25


def paginate(request, queryset, per_page=PER_PAGE):
    """
    Paginate a queryset using the ?page= param. Returns the Page object.
    Out-of-range or invalid pages fall back to a valid page.
    """
    paginator = Paginator(queryset, per_page)
    page_number = request.GET.get("page") or 1
    try:
        page_number = int(page_number)
    except (TypeError, ValueError):
        page_number = 1
    if page_number < 1:
        page_number = 1
    if page_number > paginator.num_pages:
        page_number = paginator.num_pages
    return paginator.get_page(page_number)


def querystring_without_page(request):
    """
    Return the current querystring (search/filter params) without 'page',
    so pagination links can preserve active filters.
    """
    params = request.GET.copy()
    params.pop("page", None)
    encoded = params.urlencode()
    return ("&" + encoded) if encoded else ""
