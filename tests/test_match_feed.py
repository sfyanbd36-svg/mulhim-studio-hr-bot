import os
import tempfile
import unittest

os.environ.setdefault(
    "MULHIM_DB", os.path.join(tempfile.gettempdir(), "mulhim_test.db")
)

import match_feed

OSQ_SAMPLE = """
<div class="listing">
<a href="/en/job-posters/289338970">2 hours ago    مطلوب مندوب مبيعات هاتفي - بغداد
    Contract Type: Full Time   Working Days: 6 Days</a>
<a href="/en/job-posters/289338346">12-10-2026    مدرسة خصوصي للرياضيات
    Contract Type: Freelance</a>
<a href="/en/job-posters/289338970">2 hours ago    مطلوب مندوب مبيعات هاتفي - بغداد</a>
</div>
"""

RW_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<item>
  <title>Referral Coordination Officer</title>
  <link>https://reliefweb.int/job/4236194/referral-coordination-officer</link>
  <pubDate>Thu, 29 Oct 2026 11:38:10 +0000</pubDate>
  <author>International Labour Organization</author>
  <description>&lt;div class="tag country"&gt;Country: Iraq&lt;/div&gt; Nurse needed in Baghdad</description>
</item>
</channel></rss>
"""


class InferCityTests(unittest.TestCase):
    def test_arabic_city_from_text(self):
        self.assertEqual(
            match_feed.infer_city("مطلوب مندوب مبيعات هاتفي - بغداد"), "بغداد"
        )

    def test_english_city_from_text(self):
        self.assertEqual(
            match_feed.infer_city("KRD Holding is hiring in Erbil"), "أربيل"
        )

    def test_no_city_returns_empty(self):
        self.assertEqual(match_feed.infer_city("remote software posting"), "")

    def test_resolve_city_keeps_real_city(self):
        self.assertEqual(match_feed.resolve_city("Basra", "anything"), "Basra")

    def test_resolve_city_replaces_generic(self):
        self.assertEqual(
            match_feed.resolve_city("Not specified", "Job in Mosul - teacher"),
            "الموصل",
        )


class OpenSooqParseTests(unittest.TestCase):
    def test_parses_jobs_and_dedupes(self):
        jobs = match_feed._parse_opensooq_list(OSQ_SAMPLE)
        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[0]["key"], "osq-289338970")
        self.assertEqual(jobs[0]["title"], "مطلوب مندوب مبيعات هاتفي - بغداد")
        self.assertTrue(jobs[0]["posted"].startswith("2026-"))
        self.assertEqual(jobs[1]["title"], "مدرسة خصوصي للرياضيات")
        self.assertEqual(jobs[1]["posted"], "2026-10-12")

    def test_urls_absolute(self):
        jobs = match_feed._parse_opensooq_list(OSQ_SAMPLE)
        self.assertTrue(jobs[0]["url"].startswith("https://iq.opensooq.com/en/job-posters/"))


class ReliefWebParseTests(unittest.TestCase):
    def test_parses_rss_items(self):
        jobs = match_feed._parse_reliefweb_rss(RW_SAMPLE.encode("utf-8"))
        self.assertEqual(len(jobs), 1)
        job = jobs[0]
        self.assertEqual(job["key"], "rw-4236194")
        self.assertEqual(job["title"], "Referral Coordination Officer")
        self.assertEqual(job["company"], "International Labour Organization")
        self.assertEqual(job["posted"], "2026-10-29")
        self.assertEqual(job["url"], "https://reliefweb.int/job/4236194/referral-coordination-officer")
        self.assertIn("Nurse needed in Baghdad", job["text"])

    def test_invalid_xml_returns_empty(self):
        self.assertEqual(match_feed._parse_reliefweb_rss(b"not xml"), [])


class TitleDedupeTests(unittest.TestCase):
    def test_normalize_title_ignores_case_and_punct(self):
        a = match_feed.normalize_title("مطلوب  موظف (محاسب)")
        b = match_feed.normalize_title("مطلوب موظف محاسب!")
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
