"""svederlytics hook: the visitor's Mifgash handle, so the analytics dashboard knows the same person across days."""
from .models import Person


def person_handle(request):
    pid = request.session.get("person_id") if hasattr(request, "session") else None
    if not pid:
        return None
    return Person.objects.filter(pk=pid).values_list("handle", flat=True).first()
