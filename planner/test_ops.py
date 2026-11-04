"""F8c (T262): staff ops page /ops/, its login, and the ops_superuser command."""
import datetime
import io
import os
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.cache import cache
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from .models import AgentMessage, Area, Offer, Person, Plan
from .ops import mask_email
from .testclock import FROZEN, frozen_clock, rate_limits_on


class OpsTests(TestCase):
    def setUp(self):
        area = Area.objects.create(name="Ops area", city="X", lat=37.7, lon=-122.4)
        self.alice = Person.objects.create(name="Alice Ops", handle="alice_ops", email="alice@example.com")
        self.bob = Person.objects.create(name="Bob Ops", handle="bob_ops", email="bob@example.org")
        plan = Plan.objects.create(owner=self.alice, kind="lunch", date=datetime.date(2026, 11, 4),
                                   part="lunch", area=area, status="asking")
        Offer.objects.create(plan=plan, person=self.bob, order=1, status="sent")
        AgentMessage.objects.create(plan=plan, sender="alice_ops", receiver="mifgash", type="availability",
                                    payload={"text": "zz open tomorrow"})
        AgentMessage.objects.create(plan=None, sender="bob_ops", receiver="mifgash", type="ping", payload={})
        U = get_user_model()
        self.staff = U.objects.create_user("staff", password="x" * 20, is_staff=True)
        self.plain = U.objects.create_user("plain", password="x" * 20)

    def test_anonymous_and_non_staff_redirect(self):
        r = self.client.get("/ops/")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r["Location"].startswith("/ops/login/"), r["Location"])
        self.client.force_login(self.plain)
        r = self.client.get("/ops/")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r["Location"].startswith("/ops/login/"))

    def test_staff_sees_five_tables_masked(self):
        self.client.force_login(self.staff)
        r = self.client.get("/ops/")
        self.assertEqual(r.status_code, 200)
        for h in ('id="people"', 'id="plans"', 'id="offers"', 'id="outings"', 'id="log"'):
            self.assertContains(r, h)
        self.assertContains(r, "@alice_ops")
        self.assertContains(r, "a***@example.com")
        self.assertNotContains(r, "alice@example.com")
        self.assertNotContains(r, "bob@example.org")

    def test_search_filters(self):
        self.client.force_login(self.staff)
        r = self.client.get("/ops/?q=zz")
        self.assertContains(r, "zz open tomorrow")
        self.assertNotContains(r, ">ping<")
        self.assertNotContains(r, "@bob_ops")  # no person, plan or offer matches 'zz'
        r = self.client.get("/ops/?q=bob_ops")
        self.assertContains(r, ">ping<")
        self.assertContains(r, "Bob Ops")
        self.assertNotContains(r, "Alice Ops")

    def test_login_page_and_login(self):
        self.assertEqual(self.client.get("/ops/login/").status_code, 200)
        r = self.client.post("/ops/login/", {"username": "staff", "password": "x" * 20})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r["Location"], "/ops/")
        r = self.client.post("/ops/login/", {"username": "staff", "password": "wrong"})
        self.assertContains(r, "wrong")

    def test_admin_lists_planner_models(self):
        U = get_user_model()
        boss = U.objects.create_superuser("boss", password="y" * 20)
        self.client.force_login(boss)
        r = self.client.get("/ops/admin/planner/person/")
        self.assertEqual(r.status_code, 200)
        r = self.client.get(f"/ops/admin/planner/person/{self.alice.pk}/change/")
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, 'name="email"')  # encrypted field is read-only

    def test_mask_email(self):
        self.assertEqual(mask_email("alice@example.com"), "a***@example.com")
        self.assertEqual(mask_email(""), "")

    def test_ops_superuser_idempotent(self):
        with mock.patch.dict(os.environ, {"OPS_PW_T": "p" * 24}):
            call_command("ops_superuser", "--user", "opsboss", "--password-env", "OPS_PW_T", stdout=io.StringIO())
        with mock.patch.dict(os.environ, {"OPS_PW_T": "q" * 24}):
            call_command("ops_superuser", "--user", "opsboss", "--password-env", "OPS_PW_T", stdout=io.StringIO())
        u = get_user_model().objects.get(username="opsboss")
        self.assertTrue(u.is_staff and u.is_superuser)
        self.assertTrue(u.check_password("q" * 24))


class AdminLoginLimitTests(TestCase):
    """T278: /ops/admin/login/ has the same 10-per-10-minutes cap as /ops/login/; no default staff name."""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    @rate_limits_on
    def test_admin_login_eleventh_post_is_429(self):
        self.assertEqual(self.client.get("/ops/admin/login/").status_code, 200)
        for i in range(10):
            r = self.client.post("/ops/admin/login/", {"username": "x", "password": "wrong"})
            self.assertEqual(r.status_code, 200, i)
        r = self.client.post("/ops/admin/login/", {"username": "x", "password": "wrong"})
        self.assertEqual(r.status_code, 429)
        self.assertEqual(self.client.get("/ops/admin/login/").status_code, 200)  # GET is not counted

    @rate_limits_on
    def test_both_doors_share_one_cap(self):
        for _ in range(10):
            self.client.post("/ops/login/", {"username": "x", "password": "wrong"})
        r = self.client.post("/ops/admin/login/", {"username": "x", "password": "wrong"})
        self.assertEqual(r.status_code, 429)

    @override_settings(RATE_LIMITS=True)
    def test_frozen_clock_one_second_before_a_window_edge(self):
        """T352: 11 slow posts at 1 s before a 10-minute edge stay in one window; the 11th is 429.
        With the clock moved past the edge the count starts again (the old random red test)."""
        with frozen_clock(FROZEN + 600 - 1) as clock:
            for i in range(10):
                r = self.client.post("/ops/admin/login/", {"username": "x", "password": "wrong"})
                self.assertEqual(r.status_code, 200, i)
            r = self.client.post("/ops/admin/login/", {"username": "x", "password": "wrong"})
            self.assertEqual(r.status_code, 429)
            self.assertLessEqual(int(r["Retry-After"]), 2)
            clock.now = FROZEN + 600
            r = self.client.post("/ops/admin/login/", {"username": "x", "password": "wrong"})
            self.assertEqual(r.status_code, 200)

    def test_admin_login_still_logs_in(self):
        get_user_model().objects.create_superuser("boss2", password="z" * 20)
        r = self.client.post("/ops/admin/login/?next=/ops/admin/", {"username": "boss2", "password": "z" * 20,
                                                                   "next": "/ops/admin/"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.client.get("/ops/admin/").status_code, 200)

    def test_ops_superuser_needs_user(self):
        with mock.patch.dict(os.environ, {"OPS_PW_T": "p" * 24}):
            with self.assertRaises(CommandError):
                call_command("ops_superuser", "--password-env", "OPS_PW_T", stdout=io.StringIO())

    def test_no_default_staff_name_in_code(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for rel in ("deploy/deploy.sh", "planner/management/commands/ops_superuser.py"):
            with open(os.path.join(root, rel)) as f:
                self.assertNotIn("michael", f.read().lower(), rel)
