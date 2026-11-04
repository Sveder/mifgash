from django.db import models


class Visitor(models.Model):
    """One browser. The ID is a random cookie value, so it stays the same across days."""
    vid = models.CharField(max_length=32, unique=True)
    user_id = models.CharField(max_length=64, blank=True, db_index=True)
    first_seen = models.DateTimeField(db_index=True)
    last_seen = models.DateTimeField()

    def __str__(self):
        return self.user_id or self.vid[:8]


class Session(models.Model):
    """A run of hits with no gap over SESSION_GAP_MIN minutes."""
    visitor = models.ForeignKey(Visitor, on_delete=models.CASCADE, related_name="sessions")
    started = models.DateTimeField(db_index=True)
    last_seen = models.DateTimeField(db_index=True)
    entry_path = models.CharField(max_length=500)
    current_path = models.CharField(max_length=500)
    referrer = models.CharField(max_length=255, blank=True)  # host only
    utm_source = models.CharField(max_length=100, blank=True)
    utm_medium = models.CharField(max_length=100, blank=True)
    utm_campaign = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=2, blank=True)
    browser = models.CharField(max_length=20, blank=True)
    os = models.CharField(max_length=20, blank=True)
    device = models.CharField(max_length=10, blank=True)
    is_bot = models.BooleanField(default=False, db_index=True)
    pageviews = models.PositiveIntegerField(default=0)
    events = models.PositiveIntegerField(default=0)

    class Meta:
        indexes = [models.Index(fields=["visitor", "-last_seen"])]

    @property
    def duration_s(self):
        return int((self.last_seen - self.started).total_seconds())


class Hit(models.Model):
    PAGE, EVENT = "page", "event"
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name="hits")
    ts = models.DateTimeField(db_index=True)
    kind = models.CharField(max_length=5, choices=[(PAGE, PAGE), (EVENT, EVENT)], default=PAGE)
    path = models.CharField(max_length=500)
    name = models.CharField(max_length=64, blank=True)  # event name
    props = models.JSONField(default=dict, blank=True)
    status = models.PositiveSmallIntegerField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)  # time on page, from the heartbeat

    class Meta:
        indexes = [models.Index(fields=["kind", "ts"]), models.Index(fields=["session", "ts"])]


class DailyStat(models.Model):
    """Daily totals, written by `manage.py svederlytics_rollup`. Source for the later unified dashboard."""
    day = models.DateField(unique=True)
    visitors = models.PositiveIntegerField(default=0)
    new_visitors = models.PositiveIntegerField(default=0)
    sessions = models.PositiveIntegerField(default=0)
    pageviews = models.PositiveIntegerField(default=0)
    events = models.PositiveIntegerField(default=0)
    bounces = models.PositiveIntegerField(default=0)
    duration_s = models.PositiveBigIntegerField(default=0)
    bot_sessions = models.PositiveIntegerField(default=0)
