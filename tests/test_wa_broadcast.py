import os
import tempfile
import unittest

os.environ["MULHIM_DB"] = os.path.join(tempfile.gettempdir(), "mulhim_test_wa.db")

import wa_broadcast


class WaBroadcastTests(unittest.TestCase):
    def test_set_and_list_allowed(self):
        wa_broadcast.set_group_allowed(
            "120363000000000000@g.us", True, name="Test", size="10"
        )
        allowed = wa_broadcast.allowed_groups()
        self.assertTrue(any(g["jid"] == "120363000000000000@g.us" for g in allowed))
        wa_broadcast.set_group_allowed("120363000000000000@g.us", False)
        allowed = wa_broadcast.allowed_groups()
        self.assertFalse(any(g["jid"] == "120363000000000000@g.us" for g in allowed))

    def test_reject_non_group_jid(self):
        self.assertFalse(wa_broadcast.set_group_allowed("123456789@s.whatsapp.net", True))

    def test_build_digest(self):
        jobs = [
            {"title": "محاسب", "company": "شركة أ"},
            {"title": "مبرمج", "company": "شركة ب"},
        ]
        text = wa_broadcast.build_digest(jobs, "https://t.me/bot", "https://site")
        self.assertIn("محاسب", text)
        self.assertIn("https://t.me/bot", text)

    def test_daily_counter(self):
        before = wa_broadcast.sends_today()
        wa_broadcast._bump_today()
        self.assertEqual(wa_broadcast.sends_today(), before + 1)


if __name__ == "__main__":
    unittest.main()
