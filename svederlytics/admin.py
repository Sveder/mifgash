from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import DailyStat, Hit, Session, Visitor


class ReadOnly(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Visitor)
class VisitorAdmin(ReadOnly):
    list_display = ("__str__", "user_id", "first_seen", "last_seen", "page")
    search_fields = ("user_id", "vid")
    date_hierarchy = "first_seen"

    def page(self, obj):
        return format_html('<a href="{}">open</a>', reverse("svederlytics:visitor", args=[obj.pk]))


@admin.register(Session)
class SessionAdmin(ReadOnly):
    list_display = ("started", "visitor", "entry_path", "referrer", "country", "device", "pageviews", "events", "is_bot", "page")
    list_filter = ("is_bot", "device", "browser", "country")
    date_hierarchy = "started"
    raw_id_fields = ("visitor",)

    def page(self, obj):
        return format_html('<a href="{}">open</a>', reverse("svederlytics:session", args=[obj.pk]))

    def changelist_view(self, request, extra_context=None):
        extra_context = {**(extra_context or {}), "title": format_html(
            'Sessions &middot; <a href="{}">open the analytics dashboard</a>', reverse("svederlytics:dashboard"))}
        return super().changelist_view(request, extra_context)


@admin.register(Hit)
class HitAdmin(ReadOnly):
    list_display = ("ts", "kind", "path", "name", "status", "duration_ms")
    list_filter = ("kind",)
    date_hierarchy = "ts"
    raw_id_fields = ("session",)


@admin.register(DailyStat)
class DailyStatAdmin(ReadOnly):
    list_display = ("day", "visitors", "new_visitors", "sessions", "pageviews", "events", "bounces", "bot_sessions")
