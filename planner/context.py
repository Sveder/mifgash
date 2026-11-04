from django.conf import settings


def product(request):
    """PRODUCT_NAME, DEMO and REPO_URL (T283, the public source) for every page; AGENTS_URL (F2b, T252) is the absolute agents.md URL that
    the head link, the meta tag and the landing line show, so an AI reading any page knows where to go."""
    return {"PRODUCT_NAME": settings.PRODUCT_NAME, "DEMO": settings.DEMO, "AGENTS_URL": agents_url(request),
            "REPO_URL": settings.REPO_URL}


def agents_url(request):
    """No IP address on a page (T122/T113): a named host gives its own absolute URL, a LAN or loopback
    request gives the MIFGASH_PUBLIC_URL one when that is a name, else the relative path."""
    from .views import guide_host
    host = guide_host(request)
    if not host:
        return "/agents.md"
    if host == request.get_host():
        return request.build_absolute_uri("/agents.md")
    return settings.PUBLIC_URL.rstrip("/") + "/agents.md"
