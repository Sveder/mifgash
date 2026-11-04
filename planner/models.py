"""Data model for the Mifgash POC. New hackathon work (28/10/2026)."""
import datetime
import re
import secrets
import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from .crypto import EncryptedTextField, digest

KINDS = [
    ("lunch", "Lunch"),
    ("kids", "With kids"),
    ("evening", "Evening out"),
    ("weekend", "Weekend outing"),
    ("group_dinner", "Group dinner"),  # G1 (T227): dinner with 2-6 friends, one place for all
]
# A group dinner is an evening plan with a group: friends who want evenings fit it (T227).
BASE_KIND = {"group_dinner": "evening"}
GROUP_MIN, GROUP_MAX = 2, 6
PARTS = [
    ("morning", "Morning"),
    ("lunch", "Lunch time"),
    ("afternoon", "Afternoon"),
    ("evening", "Evening"),
]
WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def new_token():
    return secrets.token_urlsafe(12)


class Area(models.Model):
    """A neighbourhood. Matching uses the centre point only, never a home address."""
    name = models.CharField(max_length=80, unique=True)
    city = models.CharField(max_length=40)
    lat = models.FloatField()
    lon = models.FloatField()
    aliases = models.CharField(max_length=200, blank=True, help_text="comma separated words that point here")

    def __str__(self):
        return self.name

    @property
    def map_query(self):
        return map_query(None, self)


HANDLE_RE = re.compile(r"^[a-z0-9_]{2,32}$")


def clean_handle(raw):
    """Lower-case handle, or ValidationError. Letters, digits and underscore, 2 to 32 characters."""
    h = (raw or "").strip().lstrip("@").lower()
    if not HANDLE_RE.match(h):
        raise ValidationError("handle: 2-32 characters, letters, digits and underscore only")
    return h


NAME_MAX = 40
NAME_EXTRA = set(" .'-")


def clean_name(raw):
    """A display name, or ValidationError (T246, docs/SECURITY.md rule 5). Letters, digits, space
    and . ' - only, at most 40 characters, at least one letter. A newline or a control character is
    refused, so a name cannot start a new line inside another person's agent prompt."""
    n = str(raw or "").strip(" ")
    if not n:
        raise ValidationError("name is required")
    if len(n) > NAME_MAX:
        raise ValidationError(f"name: at most {NAME_MAX} characters")
    if any(not (c.isalnum() or c in NAME_EXTRA) for c in n) or not any(c.isalpha() for c in n):
        raise ValidationError("name: letters, digits, spaces and . ' - only")
    return " ".join(n.split())


class Person(models.Model):
    name = models.CharField(max_length=40)
    handle = models.CharField(max_length=32, unique=True,
                              help_text="public user name for friend search: lower case, letters digits and underscore")
    is_owner = models.BooleanField(default=False)
    has_agent = models.BooleanField(default=True)
    home_area = models.ForeignKey(Area, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    work_area = models.ForeignKey(Area, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    city = models.CharField(max_length=40, blank=True, default="",
                            help_text="F3a (T259): 'Main city' from /join/, free text; matching does not use it")
    likes = models.JSONField(default=list, help_text="kinds this person wants: lunch, kids, evening, weekend")
    dislikes = models.JSONField(default=list, help_text="activity tags the agent declines")
    max_km = models.FloatField(default=4.0)
    one_on_one_only = models.BooleanField(default=False)
    kids_ages = models.JSONField(default=list, blank=True)
    token = models.CharField(max_length=32, default=new_token, unique=True)
    # Contact data and agent push settings. Encrypted at rest (planner/crypto.py).
    email = EncryptedTextField(blank=True, default="")
    email_digest = models.CharField(max_length=64, blank=True, default="", db_index=True,
                                    help_text="HMAC of the lower-case email, for lookups")
    phone = EncryptedTextField(blank=True, default="")
    telegram = EncryptedTextField(blank=True, default="", help_text="Telegram handle or chat id")
    webhook_url = EncryptedTextField(blank=True, default="", help_text="where we push to this person's agent")
    webhook_secret = EncryptedTextField(blank=True, default="", help_text="signs our pushes to the agent")
    webhook_format = models.CharField(
        max_length=10, default="mifgash", choices=[("mifgash", "Mifgash JSON, HMAC signed"),
                                                   ("openclaw", "OpenClaw /hooks/wake, Bearer token")],
        help_text="mifgash: signed {event, sent_at, payload}; openclaw: {text, mode:'now'} with the secret as Bearer token")
    last_polled_at = models.DateTimeField(null=True, blank=True,
                                          help_text="last GET /api/v1/events/ by this person's agent (T98 email fallback)")
    # M7a (T178): a quick-demo person from /try/. purge_sandbox deletes it after expires_at.
    is_sandbox = models.BooleanField(default=False, db_index=True)
    expires_at = models.DateTimeField(null=True, blank=True, help_text="sandbox people only: deleted after this time")

    def save(self, *args, **kwargs):
        if not self.handle:
            self.handle = re.sub(r"[^a-z0-9_]", "", self.name.lower())[:32]
        self.handle = clean_handle(self.handle)
        self.email_digest = email_digest(self.email) if self.email else ""
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name

    @classmethod
    def by_email(cls, email):
        return cls.objects.filter(email_digest=email_digest(email)).first()

    @property
    def address(self):
        """Protocol address in the agent log, for example 'agent:alex'."""
        return f"agent:{self.handle}" if self.has_agent else f"human:{self.handle}"


EMAIL_NEEDED = "ask your human for an email; Mifgash uses it only for the login link"


def clean_email(value):
    """F3a (T259): a stripped email, or ValueError. One @, no spaces, at most 254 characters."""
    e = str(value or "").strip()
    if not e or len(e) > 254 or e.count("@") != 1 or any(c.isspace() for c in e):
        raise ValueError("bad email")
    local, domain = e.split("@")
    if not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
        raise ValueError("bad email")
    return e


def email_digest(email):
    return digest("email:" + email.strip().lower())


class AgentKey(models.Model):
    """A bearer key for one agent. Only an HMAC of the key is stored; the plain key is shown once."""
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="agent_keys")
    prefix = models.CharField(max_length=12, help_text="first characters, to tell keys apart in a list")
    key_hash = models.CharField(max_length=64, unique=True)
    label = models.CharField(max_length=60, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    last_used = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    @staticmethod
    def hash(plain):
        return digest("agentkey:" + plain)

    @classmethod
    def issue(cls, person, label=""):
        """Make a key. Returns (row, plain key). Store nothing but the row."""
        plain = "mif_" + secrets.token_urlsafe(32)
        row = cls.objects.create(person=person, prefix=plain[:12], key_hash=cls.hash(plain), label=label)
        return row, plain

    @classmethod
    def authenticate(cls, plain):
        """The live key row for a plain key, or None. Marks the key as used."""
        if not plain or not plain.startswith("mif_"):
            return None
        row = cls.objects.select_related("person").filter(key_hash=cls.hash(plain), revoked_at__isnull=True).first()
        if row:
            row.last_used = timezone.now()
            row.save(update_fields=["last_used"])
        return row

    def revoke(self):
        self.revoked_at = timezone.now()
        self.save(update_fields=["revoked_at"])

    def __str__(self):
        return f"{self.prefix}... ({self.person})"


class MagicLink(models.Model):
    """A one-time dashboard login link. Only an HMAC of the token is stored; the link is built once.
    A link works for TTL after it is issued (T30)."""
    TTL = datetime.timedelta(hours=24)
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="magic_links")
    token_hash = models.CharField(max_length=64, unique=True)
    created = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    used_at = models.DateTimeField(null=True, blank=True)

    @staticmethod
    def hash(plain):
        return digest("magic:" + plain)

    @classmethod
    def issue(cls, person, ttl=None):
        """Make a link token. Returns (row, plain token). ttl: a timedelta, default TTL (24 hours)."""
        plain = secrets.token_urlsafe(24)
        row = cls.objects.create(person=person, token_hash=cls.hash(plain),
                                 expires_at=timezone.now() + (ttl or cls.TTL))
        return row, plain

    @classmethod
    def reissue(cls, person):
        """A fresh link; the person's older unused links stop working."""
        cls.objects.filter(person=person, used_at__isnull=True).update(used_at=timezone.now())
        return cls.issue(person)

    def expired(self):
        end = self.expires_at or (self.created + self.TTL)
        return timezone.now() >= end

    @classmethod
    def find(cls, plain):
        return cls.objects.select_related("person").filter(token_hash=cls.hash(plain or "")).first()


class Invite(models.Model):
    """M11b (T224): a person's reusable invite link, /i/<token>/. The row keeps a random nonce and the
    HMAC of the token. The token itself is an HMAC of the nonce with MIFGASH_HASH_KEY, so a copy of the
    database alone cannot rebuild a working link. A link works for MAX_USES new friends."""
    MAX_USES = 50
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="invites")
    nonce = models.CharField(max_length=32)
    token_hash = models.CharField(max_length=64, unique=True)
    uses = models.PositiveIntegerField(default=0)
    created = models.DateTimeField(auto_now_add=True)

    @staticmethod
    def hash(plain):
        return digest("invite:" + plain)

    @staticmethod
    def plain_for(nonce):
        return digest("invite-token:" + nonce)[:32]

    @property
    def token(self):
        return self.plain_for(self.nonce)

    def used_up(self):
        return self.uses >= self.MAX_USES

    @classmethod
    def current(cls, person):
        """The person's newest invite that still has uses left; a new one when there is none."""
        row = cls.objects.filter(person=person, uses__lt=cls.MAX_USES).order_by("-pk").first()
        if row:
            return row
        nonce = secrets.token_urlsafe(18)[:24]
        return cls.objects.create(person=person, nonce=nonce, token_hash=cls.hash(cls.plain_for(nonce)))

    @classmethod
    def find(cls, plain):
        if not plain or len(plain) > 64:
            return None
        return cls.objects.select_related("person").filter(token_hash=cls.hash(plain)).first()

    def accept(self, visitor):
        """Make visitor and the inviter friends. Returns 'self', 'already' or 'friends'."""
        if visitor.pk == self.person_id:
            return "self"
        if Friendship.exists(visitor, self.person):
            return "already"
        Friendship.link(self.person, visitor, source="invite")
        Invite.objects.filter(pk=self.pk).update(uses=models.F("uses") + 1)
        return "friends"


class Friendship(models.Model):
    """One direction of a friendship. A request is one row A->B with status 'requested'; it
    becomes two rows with status 'friends' when B adds A back or accepts. Only 'friends' rows
    count for matching (friends_of)."""
    SOURCES = [("handle", "Added by handle"), ("facebook", "Facebook import"), ("seed", "Demo seed"), ("sandbox", "Quick demo"),
               ("invite", "Invite link")]
    STATUSES = [("requested", "Requested"), ("friends", "Friends")]
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="friendships")
    friend = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="+")
    source = models.CharField(max_length=10, choices=SOURCES, default="handle")
    status = models.CharField(max_length=10, choices=STATUSES, default="friends")
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("person", "friend")]

    @classmethod
    def exists(cls, a, b):
        """True when a and b are friends (not only a request)."""
        return cls.objects.filter(person=a, friend=b, status="friends").exists()

    @classmethod
    def link(cls, a, b, source="handle"):
        """Make a and b friends both ways. Returns True when a new link was made."""
        new = False
        for x, y in ((a, b), (b, a)):
            row, made = cls.objects.get_or_create(person=x, friend=y, defaults={"source": source})
            if not made and row.status != "friends":
                row.status = "friends"
                row.save(update_fields=["status"])
                made = True
            new = new or made
        return new

    @classmethod
    def request(cls, a, b, source="handle", auto_accept=False):
        """a adds b. Returns 'friends' when b already asked a (or auto_accept), else 'requested'."""
        if auto_accept or cls.objects.filter(person=b, friend=a).exists():
            cls.link(a, b, source=source)
            return "friends"
        cls.objects.get_or_create(person=a, friend=b, defaults={"source": source, "status": "requested"})
        return "requested"

    @classmethod
    def friends_of(cls, person_id):
        return Person.objects.filter(pk__in=cls.objects.filter(person_id=person_id, status="friends")
                                     .values("friend_id"))

    @classmethod
    def requests_to(cls, person_id):
        """People who asked person_id and wait for an answer."""
        return Person.objects.filter(pk__in=cls.objects.filter(friend_id=person_id, status="requested")
                                     .values("person_id"))

    @classmethod
    def requests_from(cls, person_id):
        """People person_id asked who did not answer yet."""
        return Person.objects.filter(pk__in=cls.objects.filter(person_id=person_id, status="requested")
                                     .values("friend_id"))

    def __str__(self):
        return f"{self.person} -> {self.friend} ({self.status})"


class Slot(models.Model):
    """A weekly open slot: 'free for lunch on Sundays'."""
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="slots")
    weekday = models.IntegerField(help_text="0 = Monday ... 6 = Sunday")
    part = models.CharField(max_length=10, choices=PARTS)
    area = models.ForeignKey(Area, on_delete=models.PROTECT, null=True, blank=True,
                             help_text="where the person is at that time; empty = home area")

    class Meta:
        unique_together = [("person", "weekday", "part")]

    def where(self):
        return self.area or self.person.home_area

    def __str__(self):
        return f"{self.person} {WEEKDAYS[self.weekday]} {self.part}"


class Activity(models.Model):
    name = models.CharField(max_length=80)
    kind = models.CharField(max_length=12, choices=KINDS)
    area = models.ForeignKey(Area, on_delete=models.PROTECT)
    address = models.CharField(max_length=120, blank=True)
    parking = models.CharField(max_length=120, blank=True, help_text="one plain line for the calendar invite")
    price = models.IntegerField(default=1, help_text="0 free, 1 cheap, 2 mid, 3 high")
    tags = models.JSONField(default=list)
    note = models.CharField(max_length=160, blank=True)
    url = models.URLField(blank=True)
    source = models.CharField(max_length=20, default="hackathon",
                              help_text="hackathon = written during the event; reused = older data")

    def __str__(self):
        return self.name

    @property
    def map_query(self):
        return map_query(self, self.area)


def map_query(place, area):
    """T370: one search text for the Map button, the calendar Map line and the .ics LOCATION:
    '<place name>, <address or area>, <city>'. The city is added only when the address or area
    text does not hold it, so '1 Ferry Building, San Francisco' is not doubled. No model call."""
    parts = [place.name] if place else []
    where = ((place.address if place else "") or (area.name if area else "")).strip()
    if where and (not place or where.lower() != place.name.lower()):
        parts.append(where)
    city = (area.city if area else "").strip()
    if city and city.lower() not in where.lower():
        parts.append(city)
    return ", ".join(parts)


class Plan(models.Model):
    STATUS = [
        ("draft", "Draft"),
        ("open", "Open, waiting for a match"),  # posted by an agent through the API
        ("asking", "Asking friends"),
        ("joined", "Joined a friend's plan"),  # the owner said yes inside another plan
        ("confirmed", "Confirmed"),
        ("final", "Final: exact time and place agreed"),
        ("no_match", "Did not work out"),
        ("cancelled", "Cancelled"),
    ]
    owner = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="plans")
    # F8a (T260): the public id in every URL (/outing/<uid>/, /plan/<uid>/log/, the .ics path), so a
    # visitor cannot count plans. The API keeps the integer id behind the bearer key.
    uid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    raw_text = models.TextField(blank=True)
    kind = models.CharField(max_length=12, choices=KINDS)
    date = models.DateField()
    part = models.CharField(max_length=10, choices=PARTS)
    # 'I'm open tomorrow' names no part (T79): the part is a default for display, and the plan
    # fits a friend's plan at any part of that date. A match sets the part and clears the flag.
    any_part = models.BooleanField(default=False)
    # False when the person named no kind ('I'm open tomorrow', T112): the kind is only a default
    # from the part of the day, so a human sees 'Morning meetup', not 'Weekend outing'.
    kind_named = models.BooleanField(default=True)
    area = models.ForeignKey(Area, on_delete=models.PROTECT)
    radius_km = models.FloatField(default=3.0)
    group_size = models.IntegerField(default=1, help_text="friends wanted, 1 = one on one")
    min_guests = models.IntegerField(default=1)
    # Group dinner (T227): at this time a group with min_guests yeses confirms, and no new friend
    # is asked. Null = no deadline: the plan fills at group_size or when the queue runs out.
    fill_by = models.DateTimeField(null=True, blank=True)
    # G2 (T228): the people who agreed to the proposed time and place, by id. The proposer is
    # first. The plan is final when every side is in this list (two sides: one agree is enough).
    agreed = models.JSONField(default=list, blank=True)
    options = models.ManyToManyField(Activity, blank=True, related_name="+")
    chosen = models.ForeignKey(Activity, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    # Finalize (planner/finalize.py): one side proposes a time and place, the other side confirms.
    proposed_time = models.TimeField(null=True, blank=True)
    proposed_activity = models.ForeignKey(Activity, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    proposed_by = models.ForeignKey("Person", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    exact_time = models.TimeField(null=True, blank=True, help_text="set when the plan is final")
    # T255: what the owner wants from the place: {food, tastes, likes, dislikes, text}. planner/wants.py.
    wants = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="draft")
    seed = models.IntegerField(default=0, help_text="random seed for the offer order, kept for replay")
    llm_backend = models.CharField(max_length=10, blank=True)
    created = models.DateTimeField(auto_now_add=True)

    PART_TITLES = {"morning": "Morning meetup", "lunch": "Lunch", "afternoon": "Afternoon meetup",
                   "evening": "Evening out"}

    # T321: the card and .ics title per kind. 'With kids' is a form label, not a title ('With kids with Ava').
    KIND_TITLES = {"lunch": "Lunch", "kids": "Playdate", "evening": "Evening out", "weekend": "Weekend outing",
                   "group_dinner": "Group dinner"}

    @property
    def is_dinner(self):
        """T326/T377: an evening plan whose own text says 'dinner'."""
        return self.kind == "evening" and bool(re.search(r"\bdinner\b", (self.raw_text or "").lower()))

    @property
    def title(self):
        """'Playdate' when the person named the kind, else from the part: 'Morning meetup' (T112)."""
        if self.is_dinner:
            return "Dinner"  # T326: a typed 'dinner' is a dinner, not 'Evening out'
        return self.KIND_TITLES[self.kind] if self.kind_named else self.PART_TITLES[self.part]

    def option_list(self):
        """Options: the best fit for the owner's wants first (T255), then nearest to the plan area (M2M
        rows have no order, so the rank is computed again here)."""
        from .matching import km
        from .wants import score
        pick = ((self.wants or {}).get("pick") or {}).get("id")  # T265: the model's pick stays first
        return sorted(self.options.select_related("area"),
                      key=lambda a: (a.pk != pick, -score(a, self.wants), km(a.area, self.area), a.price, a.name))

    def guests(self):
        return [o.person for o in self.offers.filter(status="accepted").select_related("person")]

    def __str__(self):
        return f"#{self.pk} {self.kind} {self.date} {self.part} {self.status}"


class Offer(models.Model):
    """One invite to one friend. Only one offer per plan is pending at a time."""
    STATUS = [
        ("queued", "Queued"),          # in the random order, not sent; the friend never knows
        ("pending", "Sent"),
        ("owner_wait", "Friend said yes, owner to approve"),  # two-step approval (API owners and owners with no agent)
        ("accepted", "Accepted"),
        ("declined", "Declined"),      # private: the owner never sees this
        ("expired", "Expired"),        # private too
        ("not_sent", "Not needed"),    # plan filled before this turn; the friend never knows
        ("closed", "Closed"),          # accepted, but the group did not come together
    ]
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name="offers")
    uid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)  # F8a (T260)
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="offers")
    order = models.IntegerField()
    status = models.CharField(max_length=10, choices=STATUS, default="queued")
    choice = models.ForeignKey(Activity, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    sent_at = models.DateTimeField(null=True, blank=True)
    answered_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    token = models.CharField(max_length=32, default=new_token, unique=True)
    # T78: one sentence 'why this fits', written by the model once when the offer is sent.
    # reason_backend is "" for the fixed fallback sentence, so no model tag shows then.
    reason = models.TextField(blank=True)
    reason_backend = models.CharField(max_length=10, blank=True)

    class Meta:
        ordering = ["order"]


class AgentMessage(models.Model):
    """Agent-to-agent protocol log (mifgash/0.1). Operator and demo view only."""
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name="log", null=True, blank=True)
    sender = models.CharField(max_length=40)
    receiver = models.CharField(max_length=40)
    type = models.CharField(max_length=20)
    payload = models.JSONField(default=dict)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created", "pk"]


class AgentEvent(models.Model):
    """One push event kept for the person's own agent, also when no webhook exists (T93).
    GET /api/v1/events/?after=<id> lists them, so an agent without a public URL can poll."""
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="events")
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, null=True, blank=True, related_name="+")
    event = models.CharField(max_length=30)
    payload = models.JSONField(default=dict)
    created = models.DateTimeField(auto_now_add=True)
    fallback_at = models.DateTimeField(null=True, blank=True, db_index=True,
                                       help_text="when the email fallback handled this event (T98); null = not yet")

    class Meta:
        ordering = ["pk"]


class ChatTurn(models.Model):
    """The owner's chat with the own agent."""
    owner = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="chat")
    role = models.CharField(max_length=10)  # me / agent
    text = models.TextField()
    plan = models.ForeignKey(Plan, null=True, blank=True, on_delete=models.SET_NULL)
    buttons = models.JSONField(default=list, blank=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created", "pk"]
