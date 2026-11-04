"""'How this meetup came together' Sankey (Michael 4/11): layout, privacy, pages."""
import json
import re

from django.core.cache import cache
from django.test import override_settings

from . import story
from .models import Friendship, MagicLink, Offer, Person, Plan
from .tests import SUNDAY, Base, area


class LayoutTests(Base):
    def test_tree_layout_keeps_band_thickness_and_order(self):
        kids = [story.Node("a", "A", 3), story.Node("b", "B", 1), story.Node("z", "Zero", 0)]
        root = story.Node("r", "Root", 4, children=kids)
        lay = story.layout(root, width=600, max_h=100, min_h=4)
        self.assertEqual([n.key for n in lay["nodes"]], ["r", "a", "b"])  # a 0 value is no node
        r, a, b = lay["nodes"]
        self.assertAlmostEqual(r.h, a.h + b.h)  # the bands leave the parent at full thickness
        self.assertLessEqual(r.h, 100.001)
        self.assertGreater(a.h, b.h)
        self.assertLess(a.y + a.h, b.y + 0.001)  # tree order, no overlap
        self.assertEqual((r.x, a.depth, b.depth), (0, 1, 1))
        self.assertEqual(len(lay["links"]), 2)
        self.assertTrue(all(ln["d"].startswith("M") for ln in lay["links"]))

    def test_tiny_leaf_still_shows(self):
        root = story.Node("r", "R", 301, children=[story.Node("big", "Big", 300), story.Node("one", "One", 1)])
        lay = story.layout(root, max_h=120, min_h=4)
        one = next(n for n in lay["nodes"] if n.key == "one")
        self.assertGreaterEqual(one.h, 4)
        self.assertLessEqual(lay["nodes"][0].h, 120.001)

    def test_svg_escapes_labels_and_draws_in(self):
        root = story.Node("r", "<b>x</b>", 2, children=[story.Node("a", "A & B", 2, "yes")])
        out = story.svg(story.layout(root), "t")
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", out)
        self.assertIn("A &amp; B", out)
        self.assertIn('pathLength="1"', out)
        self.assertIn("--d:0", out)


class StoryPageBase(Base):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.alex = Person.objects.create(name="Alexandra Yesperson", handle="alex_yes", home_area=area("SoMa"))
        self.dec1 = Person.objects.create(name="Quentin Declinerone", handle="quentin_no", home_area=area("SoMa"))
        self.dec2 = Person.objects.create(name="Wilhelmina Silentwo", handle="wilma_quiet", home_area=area("SoMa"))
        for p in (self.alex, self.dec1, self.dec2):
            Friendship.link(self.me, p)

    def login(self, person):
        _, token = MagicLink.issue(person)
        self.client.post(f"/d/{token}/")

    def finished(self, kind="lunch", group=1):
        plan = self.plan(kind=kind, part="evening" if kind == "group_dinner" else "lunch", group=group)
        # the order of the asks: the two decliners first, the yes last
        Offer.objects.create(plan=plan, person=self.dec1, order=0, status="declined")
        Offer.objects.create(plan=plan, person=self.dec2, order=1, status="expired")
        Offer.objects.create(plan=plan, person=self.alex, order=2, status="accepted")
        import datetime as dt
        plan.chosen = plan.option_list()[0]
        plan.exact_time = dt.time(19, 30) if kind == "group_dinner" else dt.time(12, 30)
        plan.status = "final"
        plan.save()
        return plan


class PrivacyTests(StoryPageBase):
    SECRET = ("Quentin", "Declinerone", "quentin_no", "Wilhelmina", "Silentwo", "wilma_quiet")

    def assert_private(self, html):
        for word in self.SECRET:
            self.assertNotIn(word, html)

    def test_owner_sees_counts_never_the_names_of_the_no(self):
        plan = self.finished()
        self.login(self.me)
        for url in (f"/plan/{plan.uid}/log/", f"/outing/{plan.uid}/"):
            html = self.client.get(url).content.decode()
            self.assertIn("How this meetup came together", html, url)
            sk = html.split('id="story"', 1)[1]
            self.assertIn("Not this time: 1", sk)
            self.assertIn("No answer: 1", sk)
            self.assertIn("Yes: 1", sk)
            self.assertIn("Alexandra", sk)  # the yes is named, as the site does already
            self.assert_private(html)
        # the JSON poller of the same page holds no decliner either
        self.assert_private(json.dumps(self.client.get(f"/plan/{plan.uid}/log/?format=json").json()))

    def test_no_ask_order_in_the_graph(self):
        plan = self.finished()
        self.login(self.me)
        html = self.client.get(f"/outing/{plan.uid}/").content.decode()
        for svg in re.findall(r"<svg class=\"sk\".*?</svg>", html, re.S):
            self.assertNotRegex(svg, r"(?i)\b(first|second|third|order|#\d)\b")

    def test_guest_sees_no_ask_funnel(self):
        """A guest must not learn how many friends said no before her yes (that tells the order)."""
        plan = self.finished()
        self.login(self.alex)
        html = self.client.get(f"/outing/{plan.uid}/").content.decode()
        sk = html.split('id="story"', 1)[1]
        self.assertNotIn("Not this time", sk)
        self.assertNotIn("No answer", sk)
        self.assertIn("Going:", sk)
        self.assert_private(html)

    def test_decliner_sees_nothing_of_the_others(self):
        plan = self.finished()
        self.login(self.dec1)
        r = self.client.get(f"/plan/{plan.uid}/log/")
        html = r.content.decode()
        self.assertNotIn("Wilhelmina", html)
        self.assertNotIn("No answer:", html)


class PageTests(StoryPageBase):
    def test_one_on_one_page(self):
        plan = self.finished()
        self.login(self.me)
        html = self.client.get(f"/outing/{plan.uid}/").content.decode()
        sk = html.split('id="story"', 1)[1]
        self.assertIn("<svg class=\"sk\"", sk)
        self.assertIn(f"Friends: {Friendship.friends_of(self.me.pk).count()}", sk)
        self.assertIn("Short list:", sk)
        self.assertIn(plan.chosen.name[:15], sk)
        self.assertIn("Calendar invite", sk)
        self.assertIn("12:30 PM", sk)

    def test_group_dinner_page(self):
        plan = self.finished(kind="group_dinner", group=3)
        self.login(self.me)
        sk = self.client.get(f"/outing/{plan.uid}/").content.decode().split('id="story"', 1)[1]
        self.assertIn("for dinner", sk)
        self.assertIn("7:30 PM", sk)
        self.assertIn("Free: 3", sk)

    def test_plan_in_progress_shows_flow_so_far(self):
        plan = self.plan()
        Offer.objects.create(plan=plan, person=self.dec1, order=0, status="declined")
        Offer.objects.create(plan=plan, person=self.alex, order=1, status="pending")
        Offer.objects.create(plan=plan, person=self.dec2, order=2, status="queued")
        plan.status = "asking"
        plan.save()
        self.login(self.me)
        sk = self.client.get(f"/plan/{plan.uid}/log/").content.decode().split('id="story"', 1)[1]
        self.assertIn("Waiting: 1", sk)
        self.assertIn("Not asked yet: 1", sk)
        self.assertIn("asking friends", sk)
        self.assertNotIn("Alexandra", sk)  # a pending friend is not a yes: no name

    def test_playdate_page(self):
        plan = self.plan(kind="kids", part="morning", where="Mission")
        Offer.objects.create(plan=plan, person=self.alex, order=0, status="accepted")
        plan.chosen = plan.option_list()[0] if plan.option_list() else None
        plan.status = "confirmed"
        plan.save()
        self.login(self.me)
        r = self.client.get(f"/outing/{plan.uid}/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "How this meetup came together")


@override_settings(LLM_BACKEND="stub", SANDBOX_SYNC=True)
class TryDemoStoryTests(Base):
    """The /try/ demo's finished outing shows the graph (the judges' path)."""

    def test_demo_lunch_outing_has_the_graph(self):
        cache.clear()
        self.client.post("/try/")
        owner = Person.objects.get(is_sandbox=True, name="You")
        self.client.post("/d/free/", {"text": "free for lunch Thursday near Hayes Valley"})
        plan = Plan.objects.get(owner=owner)
        offer = plan.offers.get(status="owner_wait")
        self.client.post(f"/d/answer/{offer.pk}/", {"answer": "accept"})
        plan.refresh_from_db()
        self.assertIn(plan.status, ("confirmed", "final"))
        html = self.client.get(f"/outing/{plan.uid}/").content.decode()
        self.assertIn("How this meetup came together", html)
        self.assertIn("Yes: 1", html)
        self.assertIn("Maria", html)
        self.assertTrue(re.search(r'class="sk-l', html))
