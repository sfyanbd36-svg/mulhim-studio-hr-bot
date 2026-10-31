import json
import os
import re
import tempfile
import unittest

os.environ.setdefault(
    "MULHIM_DB", os.path.join(tempfile.gettempdir(), "mulhim_test.db")
)

import site_gen

PLACEHOLDER = re.compile(r"\{[a-z_]+\}")


class SiteGenerationTests(unittest.TestCase):
    def test_all_pages_build(self):
        prof = site_gen.build_prof_files()
        city = site_gen.build_city_files()
        combo = site_gen.build_combo_files()
        self.assertEqual(len(prof), len(site_gen.PROF_PAGES))
        self.assertEqual(len(city), len(site_gen.CITY_PAGES))
        self.assertEqual(len(combo), len(site_gen.CITY_PAGES) * len(site_gen.PROF_PAGES))
        self.assertIn("week-", site_gen.week_slug())
        self.assertIn("الأسبوع", site_gen.build_weekly_article())

    def test_no_leftover_placeholders(self):
        pages = list(site_gen.build_prof_files().items()) + list(
            site_gen.build_city_files().items()
        )
        combo = site_gen.build_combo_files()
        pages.append(("baghdad-engineer.html", combo["baghdad-engineer.html"]))
        pages.append(("basra-sales.html", combo["basra-sales.html"]))
        pages.append(("index.html", site_gen.build_page()))
        pages.append((site_gen.week_slug() + ".html", site_gen.build_weekly_article()))
        for name, page in pages:
            self.assertIsNone(PLACEHOLDER.search(page), name)

    def test_jsonld_parses(self):
        page = site_gen.build_prof_page(*site_gen.PROF_PAGES[0])
        match = re.search(
            r'<script type="application/ld\+json">(.+?)</script>', page, re.S
        )
        self.assertIsNotNone(match)
        data = json.loads(match.group(1))
        self.assertEqual(data["@type"], "CollectionPage")

    def test_matches_prof(self):
        terms = site_gen.PROF_PAGES[1][2]
        self.assertTrue(site_gen._matches_prof({"title": "مطلوب محاسب/ة"}, terms))
        self.assertTrue(site_gen._matches_prof({"title": "Accountant - Basra"}, terms))
        self.assertFalse(site_gen._matches_prof({"title": "سائق لنشافة"}, terms))

    def test_zero_count_hidden_in_titles(self):
        pages = list(site_gen.build_prof_files().values()) + list(
            site_gen.build_city_files().values()
        ) + list(site_gen.build_combo_files().values())
        for page in pages:
            self.assertNotIn("(0)", page)

    def test_sitemap_and_indexnow_cover_everything(self):
        weeks = len(list(site_gen.SITE_REPO_DIR.glob("week-*.html")))
        expected = (
            1
            + len(site_gen.CITY_PAGES)
            + len(site_gen.PROF_PAGES)
            + len(site_gen.CITY_PAGES) * len(site_gen.PROF_PAGES)
            + weeks
        )
        sitemap = site_gen.build_sitemap()
        self.assertEqual(sitemap.count("<url>"), expected)
        self.assertIn("baghdad-engineer.html", sitemap)
        urls = site_gen._indexnow_urls()
        self.assertEqual(len(urls), expected)
        self.assertIn(site_gen.SITE_URL + "/baghdad-engineer.html", urls)

    def test_cross_links_present(self):
        index = site_gen.build_page()
        self.assertIn('href="engineer.html"', index)
        self.assertIn('href="baghdad.html"', index)
        self.assertIn(site_gen.week_slug() + ".html", index)
        city_page = site_gen.build_city_page(*site_gen.CITY_PAGES[0])
        self.assertIn('href="baghdad-sales.html"', city_page)
        self.assertIn('href="basra.html"', city_page)
        prof_page = site_gen.build_prof_page(*site_gen.PROF_PAGES[0])
        self.assertIn('href="baghdad-engineer.html"', prof_page)
        combo = site_gen.build_combo_files()["baghdad-engineer.html"]
        self.assertIn(site_gen.SITE_URL + "/baghdad.html", combo)
        self.assertIn(site_gen.SITE_URL + "/engineer.html", combo)
