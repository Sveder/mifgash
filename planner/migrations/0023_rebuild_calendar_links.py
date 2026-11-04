"""T192 (M2b): stored outing.final events hold a Google Calendar link with the old place and the old
time zone. This rebuilds every stored google_calendar_url from the plan as it is now (San
Francisco place, America/Los_Angeles). The real models are used on purpose: the link code lives in
planner.calendar. Only payload keys named google_calendar_url change. One way.
"""
from django.db import migrations


def forward(apps, schema_editor):
    if not apps.get_model("planner", "AgentEvent").objects.filter(plan__isnull=False).exists():
        return  # a fresh database: nothing to rebuild, and the real models may be newer than it
    from planner import calendar
    from planner.models import AgentEvent
    for event in AgentEvent.objects.filter(plan__isnull=False).select_related("plan", "person"):
        if "google_calendar_url" not in event.payload:
            continue
        fresh = calendar.links(event.plan, event.person).get("google_calendar_url")
        if fresh and fresh != event.payload["google_calendar_url"]:
            event.payload["google_calendar_url"] = fresh
            AgentEvent.objects.filter(pk=event.pk).update(payload=event.payload)


class Migration(migrations.Migration):
    dependencies = [("planner", "0022_san_francisco_world")]
    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
