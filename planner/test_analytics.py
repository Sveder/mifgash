"""svederlytics in Mifgash: page views recorded, secret tokens never stored, the handle ties the visitor."""
from django.test import TestCase

from svederlytics.models import Hit, Session, Visitor


class AnalyticsTests(TestCase):
    def test_page_view_recorded(self):
        r = self.client.get("/privacy/", HTTP_USER_AGENT="Mozilla/5.0 (Macintosh) Chrome/130.0 Safari/537.36")
        self.assertEqual(r.status_code, 200)
        self.assertIn("sl_vid", r.cookies)
        self.assertEqual(Hit.objects.get().path, "/privacy/")
        self.assertContains(r, "svederlytics/sl.js")

    def test_tokens_masked(self):
        ua = "Mozilla/5.0 (Macintosh) Chrome/130.0 Safari/537.36"
        for path in ("/d/abc/", "/i/shorttok/", "/open/xyz/", "/h/q1/", "/c/k9"):
            self.client.get(path, HTTP_USER_AGENT=ua)
        paths = set(Hit.objects.values_list("path", flat=True))
        self.assertGreaterEqual(len(paths), 3, paths)
        for p in paths:
            self.assertIn(":token", p, paths)
        for secret in ("abc", "shorttok", "xyz", "q1", "k9"):
            self.assertFalse(any(secret in p for p in paths), paths)

    def test_dashboard_needs_staff(self):
        r = self.client.get("/_sl/dashboard/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/ops/login/", r["Location"])
        self.assertNotIn("/ops/admin/login/", r["Location"])
