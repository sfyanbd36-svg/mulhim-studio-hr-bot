import unittest

from outreach import auto as outreach_auto
from outreach import harvest_osm, sectors


class SectorDetectTests(unittest.TestCase):
    def test_food_labels_detected(self):
        cases = (
            "طباخ شرقي وغربي",
            "مقهى كاباري - نادل",
            "مطاعم البصرة كاشير",
            "باريستا - Barista",
            "وجبات سريعة - أربيل",
            "fast food cook - Baghdad",
        )
        for title in cases:
            self.assertEqual(sectors.detect_sector(title), "food", title)

    def test_non_food_sectors_detected(self):
        self.assertEqual(sectors.detect_sector("مبرمج ويب"), "tech")
        self.assertEqual(sectors.detect_sector("معلم رياضيات"), "education")
        self.assertEqual(sectors.detect_sector("صيدلية السلام"), "medical")
        self.assertEqual(sectors.detect_sector("تسويق واعلان"), "sales")

    def test_unknown_sector_is_none(self):
        self.assertIsNone(sectors.detect_sector("مدير عام"))


class IraqGeoTests(unittest.TestCase):
    def test_iraqi_places(self):
        places = ("بغداد", "Erbil, Iraq", "السليمانية", "موصل", "Baghdad", "الكوت", "عن بعد")
        for place in places:
            self.assertTrue(sectors.is_iraq(place), place)

    def test_non_iraqi_places(self):
        places = ("دبي", "Dubai UAE", "القاهرة", "Cairo", "", None)
        for place in places:
            self.assertFalse(sectors.is_iraq(place), str(place))


class EmailCleanTests(unittest.TestCase):
    def test_clean_accepts_business_mail(self):
        self.assertEqual(sectors.clean_email("Info@WOP.KRD"), "info@wop.krd")

    def test_clean_rejects_aggregators_and_assets(self):
        self.assertIsNone(sectors.clean_email("info@tripadvisor.com"))
        self.assertIsNone(sectors.clean_email("jobs@facebook.com"))
        self.assertIsNone(sectors.clean_email("photo@site.png"))
        self.assertIsNone(sectors.clean_email("not-an-email"))

    def test_emails_in_filters_and_dedupes(self):
        text = "تواصل hr@company.iq او hr@company.iq ولا image@x.jpg"
        self.assertEqual(sectors.emails_in(text), ["hr@company.iq"])


class TemplatePickTests(unittest.TestCase):
    def test_food_roles_get_food_template(self):
        path, subject = sectors.bot_template_for("نادل - أربيل")
        self.assertEqual(path, sectors.FOOD_BOT_TEMPLATE)
        self.assertEqual(subject, sectors.FOOD_BOT_SUBJECT)
        self.assertTrue(path.exists())

    def test_other_roles_get_default_template(self):
        path, subject = sectors.bot_template_for("مبرمج ويب")
        self.assertEqual(path, sectors.DEFAULT_BOT_TEMPLATE)
        self.assertEqual(subject, sectors.DEFAULT_BOT_SUBJECT)
        self.assertTrue(path.exists())

    def test_empty_roles_fall_back_to_default(self):
        path, _ = sectors.bot_template_for("")
        self.assertEqual(path, sectors.DEFAULT_BOT_TEMPLATE)

    def test_food_template_renders_clean(self):
        body = sectors.FOOD_BOT_TEMPLATE.read_text(encoding="utf-8")
        rendered = body.format(roles="كاشير", company="مطعم النخيل")
        self.assertIn("mulhimstudio_hr_bot", rendered)
        self.assertNotIn("{", rendered)
        self.assertIn("مطعم النخيل", rendered)

    def test_default_template_still_renders(self):
        body = sectors.DEFAULT_BOT_TEMPLATE.read_text(encoding="utf-8")
        rendered = body.format(roles="محاسب", company="شركة الاختبار")
        self.assertNotIn("{", rendered)


class BestPerDomainTests(unittest.TestCase):
    def test_free_mail_kept_per_address(self):
        rows = [
            {"email": "x1@gmail.com"},
            {"email": "x2@gmail.com"},
            {"email": "hr@corp-iq.com"},
            {"email": "info@corp-iq.com"},
        ]
        picked = outreach_auto.best_per_domain(rows)
        emails = sorted(row["email"] for row in picked)
        self.assertEqual(len(emails), 3)
        self.assertIn("x1@gmail.com", emails)
        self.assertIn("x2@gmail.com", emails)
        self.assertEqual(len([e for e in emails if e.endswith("corp-iq.com")]), 1)


class OsmHarvestTests(unittest.TestCase):
    def test_query_targets_all_iraq_food_amenities(self):
        query = harvest_osm.build_query()
        self.assertIn("ISO3166-1", query)
        self.assertIn("restaurant|cafe|fast_food|food_court|ice_cream", query)
        self.assertIn("out tags;", query)

    def test_poi_row_uses_food_labels(self):
        poi = {
            "type": "way",
            "id": 42,
            "tags": {"amenity": "cafe", "name": "مقهى النهر", "addr:city": "أربيل"},
        }
        row = harvest_osm.poi_row(poi, "info@cafe.iq")
        self.assertEqual(row["email"], "info@cafe.iq")
        self.assertEqual(row["company"], "مقهى النهر")
        self.assertEqual(row["roles"], ["مقهى - أربيل"])
        self.assertEqual(row["loc"], "أربيل")
        self.assertEqual(row["source"], "openstreetmap.org/way/42")
        self.assertEqual(sectors.detect_sector("، ".join(row["roles"])), "food")

    def test_poi_row_falls_back_without_name(self):
        poi = {"type": "node", "id": 7, "tags": {"amenity": "restaurant", "addr:city": "البصرة"}}
        row = harvest_osm.poi_row(poi, "x@y.iq")
        self.assertEqual(row["company"], "مطعم البصرة")
        self.assertEqual(row["roles"], ["مطعم - البصرة"])


if __name__ == "__main__":
    unittest.main()
