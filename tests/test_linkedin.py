import os
import tempfile
import unittest
from datetime import date

os.environ["MULHIM_DB"] = os.path.join(tempfile.gettempdir(), "mulhim_linkedin_test.db")

from marketing import linkedin_daily


class RotationTests(unittest.TestCase):
    def test_pick_angle_is_deterministic(self):
        day = date(2026, 10, 31)
        self.assertEqual(linkedin_daily.pick_angle(day), linkedin_daily.pick_angle(day))

    def test_rotation_covers_all_angles(self):
        start = date(2026, 1, 1)
        picks = {linkedin_daily.pick_angle(date.fromordinal(start.toordinal() + i)) for i in range(14)}
        self.assertEqual(picks, set(linkedin_daily.ANGLES))

    def test_pick_angle_stable_value(self):
        self.assertEqual(
            linkedin_daily.pick_angle(date(2026, 10, 31)),
            linkedin_daily.ANGLES[date(2026, 10, 31).toordinal() % len(linkedin_daily.ANGLES)],
        )


class PostBuildTests(unittest.TestCase):
    STATS = {"local": 42, "feed": 275}

    def test_every_angle_within_linkedin_limit(self):
        for angle in linkedin_daily.ANGLES:
            post = linkedin_daily.build_post(angle, self.STATS)
            self.assertLessEqual(len(post), linkedin_daily.MAX_CHARS, angle)

    def test_every_angle_has_links_and_hashtags(self):
        for angle in linkedin_daily.ANGLES:
            post = linkedin_daily.build_post(angle, self.STATS)
            self.assertIn("https://t.me/mulhimstudio_hr_bot?start=li", post, angle)
            self.assertIn(linkedin_daily.SITE_URL, post, angle)
            self.assertIn("#وظائف_العراق", post, angle)
            self.assertGreaterEqual(post.count("#"), 4, angle)

    def test_posts_render_without_leftover_placeholders(self):
        for angle in linkedin_daily.ANGLES:
            post = linkedin_daily.build_post(angle, self.STATS)
            self.assertNotIn("{", post, angle)
            self.assertNotIn("}", post, angle)

    def test_market_angle_shows_live_numbers(self):
        post = linkedin_daily.build_post("market", self.STATS)
        self.assertIn("275", post)
        self.assertIn("42", post)

    def test_render_all_covers_every_angle(self):
        combined = linkedin_daily.render_all(self.STATS)
        for angle in linkedin_daily.ANGLES:
            self.assertIn("[{a}]".format(a=angle), combined)
        self.assertGreaterEqual(combined.count("https://t.me/mulhimstudio_hr_bot?start=li"), 5)


if __name__ == "__main__":
    unittest.main()
