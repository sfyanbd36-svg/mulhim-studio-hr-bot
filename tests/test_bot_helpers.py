import os
import tempfile
import unittest
from unittest import mock

os.environ["MULHIM_DB"] = os.path.join(tempfile.gettempdir(), "mulhim_test.db")

import bot
import storage


def ensure_clear(name, headers):
    storage.register_schema(name, headers)
    with storage._lock:
        conn = storage._conn()
        storage._ensure_table(name, headers, conn)
        conn.execute('DELETE FROM "{}"'.format(name))
        conn.commit()


class ReferralTests(unittest.TestCase):
    def setUp(self):
        ensure_clear("referrals", ["ref", "user_id", "at"])

    def test_code_format(self):
        self.assertEqual(bot.referral_code(123), "r123")

    def test_referral_count_excludes_self(self):
        bot.record_referral("r123", 123)
        bot.record_referral("r123", 55)
        bot.record_referral("r123", 66)
        self.assertEqual(bot.referral_count(123), 2)

    def test_tiers(self):
        self.assertIn("ابدائي", bot.referral_tier(0))
        self.assertIn("فضي", bot.referral_tier(3))
        self.assertIn("ذهبي", bot.referral_tier(10))


class StatusTests(unittest.TestCase):
    def setUp(self):
        ensure_clear(
            "app_status",
            ["row_key", "user_id", "job_id", "status", "updated_at"],
        )

    def test_set_get_status(self):
        self.assertEqual(bot.get_application_status("10", "4"), "")
        bot.set_application_status("10", "4", "طلب مقابلة")
        self.assertEqual(bot.get_application_status("10", "4"), "طلب مقابلة")
        bot.set_application_status("10", "4", "تواصل معك صاحب الوظيفة")
        self.assertEqual(bot.get_application_status("10", "4"), "تواصل معك صاحب الوظيفة")

    def test_status_key_isolated(self):
        bot.set_application_status("10", "4", "a")
        self.assertEqual(bot.get_application_status("11", "4"), "")
        self.assertEqual(bot.get_application_status("10", "5"), "")


class HelperTests(unittest.TestCase):
    def test_get_telegram_channels_parses_env(self):
        os.environ["TELEGRAM_CHANNELS"] = "@baghdadjobs, @iraqjobs , "
        try:
            self.assertEqual(
                bot.get_telegram_channels(), ["@baghdadjobs", "@iraqjobs"]
            )
            os.environ["TELEGRAM_CHANNELS"] = ""
            self.assertEqual(bot.get_telegram_channels(), [])
        finally:
            os.environ.pop("TELEGRAM_CHANNELS", None)

    def test_register_unregister_channel(self):
        from pathlib import Path

        env_backup = os.environ.get("TELEGRAM_CHANNELS")
        orig_env_file = bot.ENV_FILE
        with tempfile.TemporaryDirectory() as tmp:
            bot.ENV_FILE = Path(tmp) / ".env"
            bot.ENV_FILE.write_text("FOO=bar\n", encoding="utf-8")
            os.environ["TELEGRAM_CHANNELS"] = ""
            try:
                self.assertTrue(bot.register_channel("-100123"))
                self.assertFalse(bot.register_channel("-100123"))
                self.assertTrue(bot.register_channel("-100999"))
                self.assertEqual(
                    bot.get_telegram_channels(), ["-100123", "-100999"]
                )
                content = bot.ENV_FILE.read_text(encoding="utf-8")
                self.assertIn("FOO=bar", content)
                self.assertIn("TELEGRAM_CHANNELS=-100123, -100999", content)
                self.assertTrue(bot.unregister_channel("-100123"))
                self.assertFalse(bot.unregister_channel("-100123"))
                self.assertEqual(bot.get_telegram_channels(), ["-100999"])
            finally:
                bot.ENV_FILE = orig_env_file
                if env_backup is None:
                    os.environ.pop("TELEGRAM_CHANNELS", None)
                else:
                    os.environ["TELEGRAM_CHANNELS"] = env_backup

    def test_latest_saved_application_picks_last(self):
        rows = [
            {
                "user_id": "500",
                "full_name": "first",
                "timestamp": "2026-10-01T10:00:00",
            },
            {
                "user_id": "500",
                "full_name": "second",
                "timestamp": "2026-10-02T10:00:00",
            },
            {"user_id": "501", "full_name": "other", "timestamp": "2026-10-03"},
        ]
        orig = bot.load_applications
        bot.load_applications = lambda: rows
        try:
            got = bot.latest_saved_application(500)
            self.assertEqual(got["full_name"], "second")
            self.assertIsNone(bot.latest_saved_application(999))
        finally:
            bot.load_applications = orig

    def test_build_quick_record_overrides_job_fields(self):
        saved = {
            "user_id": "500",
            "full_name": "أحمد",
            "phone": "0770",
            "cv_file": "a.pdf",
            "job": "وظيفة قديمة",
            "company": "شركة قديمة",
            "timestamp": "2026-10-01",
        }
        job = {
            "job_id": "9",
            "title": "مبرمج",
            "company_id": "2",
        }
        company = {"name": "شركة جديدة", "company_id": "2"}
        rec = bot.build_quick_record(saved, job, company)
        self.assertEqual(rec["job"], "مبرمج")
        self.assertEqual(rec["job_id"], "9")
        self.assertEqual(rec["company"], "شركة جديدة")
        self.assertEqual(rec["full_name"], "أحمد")
        self.assertNotEqual(rec["timestamp"], "2026-10-01")

    def test_visible_jobs_shape(self):
        items = bot.visible_jobs()
        self.assertIsInstance(items, list)
        if items:
            first = items[0]
            for key in ("title", "company"):
                self.assertIn(key, first)

    def test_site_public_url_default(self):
        os.environ.pop("SITE_PUBLIC_URL", None)
        self.assertIn("github.io", bot.site_public_url())


class DetectSpecialtyTests(unittest.TestCase):
    def test_detects_accounting(self):
        self.assertEqual(
            bot.detect_specialty("مطلوب محاسب خبرة سنتين بالمحاسبة"), "محاسبة ومالية"
        )

    def test_detects_programming(self):
        self.assertEqual(
            bot.detect_specialty("شركة تبحث عن مبرمج Python و تطوير مواقع"), "برمجة وتقنية"
        )

    def test_detects_engineering(self):
        self.assertEqual(
            bot.detect_specialty("مطلوب مدني مدني مهندس إنشائي"), "هندسة"
        )

    def test_detects_marketing(self):
        self.assertEqual(bot.detect_specialty("أخصائي تسويق رقمي"), "تسويق")

    def test_empty_and_unknown(self):
        self.assertEqual(bot.detect_specialty(""), "")
        self.assertEqual(bot.detect_specialty(None), "")
        self.assertEqual(bot.detect_specialty("نص عشوائي بدون تخصص"), "")


class SearchJobsTests(unittest.TestCase):
    def setUp(self):
        ensure_clear("companies", bot.COMPANY_HEADERS)
        ensure_clear("company_jobs", bot.JOB_HEADERS)
        ensure_clear("feed_jobs", bot.FEED_HEADERS)

    def _seed_feed(self, key="t-1"):
        storage.insert_rows(
            "feed_jobs",
            bot.FEED_HEADERS,
            [
                {
                    "key": key,
                    "title": "مطلوب محاسب خبرة",
                    "company": "شركة تجريبية",
                    "city": "بغداد",
                    "text": "خبرة سنتين - دوام كامل",
                    "source": "test",
                    "url": "https://example.com/j/1",
                    "posted": "2026-10-30",
                    "apply": "",
                    "imported_at": "2026-10-30",
                }
            ],
        )

    def test_specialty_label_filters_feed_by_detection(self):
        self._seed_feed()
        matches, feed = bot.search_jobs("محاسبة ومالية")
        self.assertEqual(matches, [])
        self.assertEqual(len(feed), 1)

    def test_keyword_search_still_matches_literal_text(self):
        self._seed_feed()
        matches, feed = bot.search_jobs("محاسب")
        self.assertEqual(matches, [])
        self.assertEqual(len(feed), 1)

    def test_label_with_no_hits_returns_empty(self):
        self._seed_feed()
        matches, feed = bot.search_jobs("قانون")
        self.assertEqual(matches, [])
        self.assertEqual(feed, [])

    def test_label_matches_company_job_by_caption_and_specialty(self):
        bot.ensure_curated_company()
        bot.save_job_post(bot.CURATED_COMPANY_ID, "مطلوب محاسب للعمل ببغداد")
        matches, feed = bot.search_jobs("محاسبة ومالية")
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["specialty"], "محاسبة ومالية")
        self.assertEqual(feed, [])


class CuratedCompanyTests(unittest.TestCase):
    def setUp(self):
        ensure_clear("companies", bot.COMPANY_HEADERS)
        ensure_clear("company_jobs", bot.JOB_HEADERS)

    def test_ensure_creates_and_is_idempotent(self):
        first = bot.ensure_curated_company()
        self.assertEqual(first["company_id"], bot.CURATED_COMPANY_ID)
        self.assertEqual(first["owner_user_id"], "")
        second = bot.ensure_curated_company()
        self.assertEqual(second["company_id"], bot.CURATED_COMPANY_ID)
        self.assertEqual(len(bot.get_companies()), 1)

    def test_is_curated_company_id(self):
        self.assertTrue(bot.is_curated_company_id("curated"))
        self.assertFalse(bot.is_curated_company_id("1"))
        self.assertFalse(bot.is_curated_company_id(""))

    def test_save_job_post_sets_specialty(self):
        bot.ensure_curated_company()
        job = bot.save_job_post(
            bot.CURATED_COMPANY_ID,
            "مطلوب محاسب للعمل ببغداد - خبرة سنتين",
        )
        self.assertEqual(job["company_id"], bot.CURATED_COMPANY_ID)
        self.assertEqual(job["specialty"], "محاسبة ومالية")
        self.assertEqual(job["active"], "1")
        self.assertTrue(bot.get_job(job["job_id"]))

    def test_curated_jobs_appear_in_active_list(self):
        bot.ensure_curated_company()
        bot.save_job_post(bot.CURATED_COMPANY_ID, "مطلوب مبرمج ويب")
        active = bot.get_all_active_jobs()
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["company_id"], bot.CURATED_COMPANY_ID)

    def test_save_job_post_stores_apply_email(self):
        bot.ensure_curated_company()
        job = bot.save_job_post(
            bot.CURATED_COMPANY_ID,
            "مطلوب مصمم جرافيك - ارسال السيرة على Careers@Example.COM",
            apply_email="Careers@Example.COM",
        )
        self.assertEqual(job["apply_email"], "careers@example.com")
        stored = bot.get_job(job["job_id"])
        self.assertEqual(stored["apply_email"], "careers@example.com")

    def test_save_job_post_defaults_apply_email_empty(self):
        bot.ensure_curated_company()
        job = bot.save_job_post(bot.CURATED_COMPANY_ID, "مطلوب كاتب محتوى")
        self.assertEqual(job["apply_email"], "")


class ApplyEmailTests(unittest.TestCase):
    def test_extract_email_from_free_text(self):
        match = bot.EMAIL_EXTRACT_RE.search("التقديم على hr@company.iq من فضلك")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(0), "hr@company.iq")

    def test_full_rejects_embedded_text(self):
        self.assertIsNone(bot.EMAIL_FULL_RE.search("hr@company.iq فقط"))

    def test_send_application_email_without_smtp_returns_false(self):
        saved = {
            "OUTREACH_EMAIL": os.environ.pop("OUTREACH_EMAIL", None),
            "OUTREACH_APP_PASSWORD": os.environ.pop("OUTREACH_APP_PASSWORD", None),
        }
        try:
            ok = bot.send_application_email(
                "x@y.com", {"job": "t", "full_name": "n"}, "summary", None
            )
            self.assertFalse(ok)
        finally:
            for key, value in saved.items():
                if value is not None:
                    os.environ[key] = value


class NotifyOwnerGuardTests(unittest.IsolatedAsyncioTestCase):
    async def test_ownerless_company_returns_false(self):
        company = {"company_id": "curated", "owner_user_id": ""}
        result = await bot.notify_company_owner(None, company, "text")
        self.assertFalse(result)

    async def test_nonnumeric_owner_returns_false(self):
        company = {"company_id": "1", "owner_user_id": "abc"}
        result = await bot.notify_company_owner(None, company, "text")
        self.assertFalse(result)


class ApplicationRoutingTests(unittest.TestCase):
    def setUp(self):
        ensure_clear("companies", bot.COMPANY_HEADERS)
        ensure_clear("company_jobs", bot.JOB_HEADERS)
        ensure_clear("applicants", bot.CSV_HEADERS)

    def _seed(self):
        class FakeUser:
            def __init__(self, uid, username):
                self.id = uid
                self.username = username

        acc = bot.register_company(FakeUser(111, "acc_owner"), "شركة المحاسبين")
        eng = bot.register_company(FakeUser(222, "eng_owner"), "شركة المهندسين")
        job_acc = bot.save_job_post(
            acc["company_id"], "مطلوب محاسب خبرة سنتين ببغداد"
        )
        job_eng = bot.save_job_post(
            eng["company_id"], "مطلوب مهندس مدني للمشاريع"
        )
        return acc, eng, job_acc, job_eng

    def test_quick_record_targets_only_announcing_company(self):
        acc, eng, job_acc, job_eng = self._seed()
        saved = {
            "timestamp": "2026-01-01", "user_id": "9", "full_name": "متقدم",
            "phone": "0770", "company_id": acc["company_id"], "job_id": job_acc["job_id"],
        }
        record = bot.build_quick_record(saved, job_eng, eng)
        self.assertEqual(record["company_id"], str(eng["company_id"]))
        self.assertNotEqual(record["company_id"], str(acc["company_id"]))
        self.assertEqual(str(record["job_id"]), str(job_eng["job_id"]))
        self.assertNotIn("specialty", record)
        self.assertEqual(job_acc["specialty"], "محاسبة ومالية")
        self.assertNotEqual(job_acc["specialty"], job_eng["specialty"])


class FinalizeRoutingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        ensure_clear("companies", bot.COMPANY_HEADERS)
        ensure_clear("company_jobs", bot.JOB_HEADERS)
        ensure_clear("applicants", bot.CSV_HEADERS)

    def _seed(self):
        class FakeUser:
            def __init__(self, uid, username):
                self.id = uid
                self.username = username

        acc = bot.register_company(FakeUser(111, "acc_owner"), "شركة المحاسبين")
        eng = bot.register_company(FakeUser(222, "eng_owner"), "شركة المهندسين")
        job_acc = bot.save_job_post(acc["company_id"], "مطلوب محاسب خبرة سنتين ببغداد")
        job_eng = bot.save_job_post(eng["company_id"], "مطلوب مهندس مدني للمشاريع")
        return acc, eng, job_acc, job_eng

    async def test_finalize_sends_only_to_announcing_company_owner(self):
        acc, eng, job_acc, job_eng = self._seed()
        delivered_chat_ids = []

        class FakeBot:
            async def send_message(self, chat_id, text, reply_markup=None):
                delivered_chat_ids.append(chat_id)

            async def send_document(self, chat_id, document, filename, caption):
                delivered_chat_ids.append(chat_id)

        class FakeApp:
            bot = FakeBot()

        record = {
            "timestamp": bot.now_iso(),
            "user_id": "9", "username": "u", "full_name": "متقدم الاختبار",
            "phone": "07700000000", "email": "a@b.com", "city": "بغداد",
            "education": "بكالوريوس", "work_experience": "سنة",
            "skills": "محاسبة", "languages": "العربية", "summary": "نبذة",
            "company_id": str(job_eng["company_id"]), "company": "شركة المهندسين",
            "job_id": str(job_eng["job_id"]), "job": job_eng["title"],
        }
        with mock.patch.object(bot, "notify_admins") as admin_mock, \
                mock.patch.object(bot, "notify_whatsapp"), \
                mock.patch.object(bot, "send_application_email", return_value=False):
            ok = await bot.finalize_application(record, FakeApp(), mock.AsyncMock())
        self.assertTrue(ok)
        self.assertIn(222, delivered_chat_ids)
        self.assertNotIn(111, delivered_chat_ids)
        admin_mock.assert_not_called()
        saved_row = [
            row for row in bot.load_applications()
            if str(row.get("user_id")) == "9"
        ]
        self.assertTrue(saved_row)
        self.assertEqual(str(saved_row[-1]["company_id"]), str(job_eng["company_id"]))
        self.assertEqual(str(saved_row[-1]["job_id"]), str(job_eng["job_id"]))


class SpecialtyBroadcastTests(unittest.TestCase):
    def setUp(self):
        ensure_clear("users", bot.USER_HEADERS)
        ensure_clear("seeker_prefs", bot.SEEKER_HEADERS)

    def _register(self, uid, username=None, keywords=None):
        class FakeUser:
            def __init__(self):
                self.id = uid
                self.username = username or "u{uid}".format(uid=uid)
                self.first_name = "u{uid}".format(uid=uid)

        bot.record_user(FakeUser())
        if keywords is not None:
            bot.save_seeker(uid, keywords=keywords)

    def test_filters_out_other_specialties(self):
        self._register(1, keywords="محاسبة")
        self._register(2, keywords="هندسة مدنية")
        self._register(3)
        targets, registered, mode = bot.specialty_broadcast_targets(
            "محاسبة ومالية"
        )
        self.assertEqual(registered, 3)
        self.assertEqual(mode, "محاسبة ومالية")
        self.assertIn(1, targets)
        self.assertNotIn(2, targets)
        self.assertIn(3, targets)

    def test_multi_specialty_seeker_matches_both(self):
        self._register(1, keywords="محاسبة، تصميم")
        acc_targets, _, _ = bot.specialty_broadcast_targets("محاسبة ومالية")
        design_targets, _, _ = bot.specialty_broadcast_targets("تصميم")
        self.assertIn(1, acc_targets)
        self.assertIn(1, design_targets)

    def test_empty_specialty_sends_to_everyone(self):
        self._register(1, keywords="هندسة مدنية")
        self._register(2, keywords="محاسبة")
        targets, registered, mode = bot.specialty_broadcast_targets("")
        self.assertEqual(mode, "all")
        self.assertEqual(registered, 2)
        self.assertEqual(sorted(targets), [1, 2])

    def test_unknown_keywords_seeker_still_gets_alert(self):
        self._register(1, keywords="")
        self._register(2, keywords="تسويق")
        targets, _, _ = bot.specialty_broadcast_targets("برمجة وتقنية")
        self.assertIn(1, targets)
        self.assertNotIn(2, targets)


class MarketApplyTests(unittest.TestCase):
    def setUp(self):
        ensure_clear("companies", bot.COMPANY_HEADERS)
        ensure_clear("company_jobs", bot.JOB_HEADERS)
        ensure_clear("feed_jobs", bot.FEED_HEADERS)

    def _seed_feed(self, key="ijq-3082", apply="hr@company.iq"):
        storage.insert_rows(
            "feed_jobs",
            bot.FEED_HEADERS,
            [
                {
                    "key": key,
                    "title": "مطلوب محاسب للشركة",
                    "company": "شركة تجريبية",
                    "city": "بغداد",
                    "text": "خبرة سنتين - التقديم hr@company.iq",
                    "source": "ijobsiq",
                    "url": "https://ijobsiq.com/jobs/3082",
                    "posted": "2026-10-01",
                    "apply": apply,
                    "imported_at": "2026-10-01",
                }
            ],
        )

    def test_resolve_market_job_with_email(self):
        self._seed_feed()
        job = bot.resolve_job_for_apply("ijq-3082")
        self.assertIsNotNone(job)
        self.assertEqual(job["company_id"], bot.MARKET_COMPANY_ID)
        self.assertEqual(job["apply_email"], "hr@company.iq")
        self.assertEqual(job["feed_url"], "https://ijobsiq.com/jobs/3082")
        self.assertEqual(job["active"], "1")
        self.assertTrue(bot.get_company(bot.MARKET_COMPANY_ID))

    def test_resolve_market_job_without_email_is_refused(self):
        self._seed_feed(apply="")
        self.assertIsNone(bot.resolve_job_for_apply("ijq-3082"))

    def test_resolve_unknown_id_is_none(self):
        self.assertIsNone(bot.resolve_job_for_apply("nope-1"))
        self.assertIsNone(bot.resolve_job_for_apply("999999"))

    def test_visible_jobs_marks_applyable_market_jobs(self):
        self._seed_feed()
        self._seed_feed(key="ijq-1111", apply="")
        market = [j for j in bot.visible_jobs() if not j["local"]]
        by_key = {j["key"]: j for j in market}
        self.assertEqual(by_key["ijq-3082"]["apply"], "hr@company.iq")
        self.assertEqual(by_key["ijq-1111"]["apply"], "")

    def test_jobs_page_offers_inbot_apply_for_market_job(self):
        self._seed_feed()
        text, markup = bot.build_jobs_page(1)
        flat = [cb for row in markup.inline_keyboard for cb in row]
        callbacks = [b.callback_data for b in flat if getattr(b, "callback_data", None)]
        urls = [b.url for b in flat if getattr(b, "url", None)]
        self.assertIn("applyjob:ijq-3082", callbacks)
        self.assertIn("https://ijobsiq.com/jobs/3082", urls)


class MarketFinalizeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        ensure_clear("companies", bot.COMPANY_HEADERS)
        ensure_clear("company_jobs", bot.JOB_HEADERS)
        ensure_clear("applicants", bot.CSV_HEADERS)
        ensure_clear("feed_jobs", bot.FEED_HEADERS)

    async def test_market_application_is_emailed_to_announcing_company(self):
        bot.ensure_market_company()
        sent_to = {}

        with mock.patch.object(bot, "notify_admins") as admin_mock, \
                mock.patch.object(bot, "notify_whatsapp"), \
                mock.patch.object(
                    bot, "send_application_email",
                    side_effect=lambda to, rec, summary, pdf: sent_to.setdefault("to", to) or True,
                ), \
                mock.patch.object(bot, "notify_company_owner", return_value=False):
            record = {
                "timestamp": bot.now_iso(),
                "user_id": "42", "username": "seeker", "full_name": "متقدم السوق",
                "phone": "07700000001", "email": "s@mail.com", "city": "بغداد",
                "education": "بكالوريوس محاسبة", "work_experience": "سنتين",
                "skills": "محاسبة", "languages": "العربية", "summary": "نبذة",
                "company_id": bot.MARKET_COMPANY_ID, "company": bot.MARKET_COMPANY_NAME,
                "job_id": "ijq-3082", "job": "مطلوب محاسب",
                "apply_email": "hr@company.iq",
                "feed_url": "https://ijobsiq.com/jobs/3082",
            }
            ok = await bot.finalize_application(record, mock.MagicMock(), mock.AsyncMock())
        self.assertTrue(ok)
        self.assertEqual(sent_to.get("to"), "hr@company.iq")
        admin_mock.assert_called_once()
        summary_text = admin_mock.call_args[0][1]
        self.assertIn("hr@company.iq", summary_text)
        self.assertIn("https://ijobsiq.com/jobs/3082", summary_text)


class SpecialtyButtonTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        ensure_clear("companies", bot.COMPANY_HEADERS)
        ensure_clear("company_jobs", bot.JOB_HEADERS)
        ensure_clear("feed_jobs", bot.FEED_HEADERS)

    async def test_callback_replies_via_query_message(self):
        storage.insert_rows(
            "feed_jobs",
            bot.FEED_HEADERS,
            [
                {
                    "key": "t-9",
                    "title": "مطلوب محاسب خبرة",
                    "company": "شركة تجريبية",
                    "city": "بغداد",
                    "text": "خبرة سنتين",
                    "source": "test",
                    "url": "https://example.com/j/9",
                    "posted": "2026-10-31",
                    "apply": "",
                    "imported_at": "2026-10-31",
                }
            ],
        )

        class FakeMessage:
            def __init__(self):
                self.replies = []

            async def reply_text(self, text, reply_markup=None, **kwargs):
                self.replies.append((text, reply_markup))

        message = FakeMessage()

        class FakeQuery:
            data = "spec:محاسبة ومالية"
            feedback_answered = False

            async def answer(self):
                FakeQuery.feedback_answered = True

        query = FakeQuery()
        query.message = message
        update = type(
            "FakeUpdate",
            (),
            {"message": None, "callback_query": query, "effective_user": None},
        )()
        context = type("FakeCtx", (), {"args": []})()
        await bot.specialty_button(update, context)
        self.assertTrue(query.feedback_answered)
        self.assertEqual(len(message.replies), 1)
        text, _ = message.replies[0]
        self.assertIn("من السوق", text)
        self.assertIn("محاسب", text)


class ApplyFlowUXTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        ensure_clear("companies", bot.COMPANY_HEADERS)
        ensure_clear("company_jobs", bot.JOB_HEADERS)
        ensure_clear("feed_jobs", bot.FEED_HEADERS)

    class _Message:
        def __init__(self, text=""):
            self.text = text
            self.replies = []

        async def reply_text(self, text, reply_markup=None, **kwargs):
            self.replies.append((text, reply_markup))

    def _update(self, text="", uid=501):
        user = type(
            "FakeUser",
            (),
            {"id": uid, "username": "seeker", "is_bot": False, "first_name": "S"},
        )()
        return type(
            "FakeUpdate", (), {"message": self._Message(text), "effective_user": user}
        )()

    def _ctx(self):
        return type("FakeCtx", (), {"user_data": {}})()

    async def test_apply_start_lists_jobs_not_companies(self):
        owner = type("FakeUser", (), {"id": 707, "username": "own", "first_name": "O"})()
        acc = bot.register_company(owner, "شركة الاختبار")
        bot.save_job_post(acc["company_id"], "مطلوب محاسب للتجربة")
        update = self._update()
        result = await bot.apply_start(update, self._ctx())
        self.assertIs(result, bot.ConversationHandler.END)
        text, markup = update.message.replies[0]
        self.assertIn("محاسب", text)
        self.assertNotIn("اختر الشركة", text)
        callbacks = [
            btn.callback_data
            for row in markup.inline_keyboard
            for btn in row
            if getattr(btn, "callback_data", None)
        ]
        self.assertTrue(any(str(c).startswith("applyjob:") for c in callbacks))

    async def test_apply_start_without_jobs(self):
        update = self._update()
        result = await bot.apply_start(update, self._ctx())
        self.assertIs(result, bot.ConversationHandler.END)
        self.assertIn("ماكو وظائف", update.message.replies[0][0])

    async def test_verify_plain_text_exits_and_points_to_apply(self):
        update = self._update("findjob")
        context = self._ctx()
        context.user_data["verify_code"] = "123456"
        result = await bot.verify_receive_email(update, context)
        self.assertIs(result, bot.ConversationHandler.END)
        reply = update.message.replies[0][0]
        self.assertIn("/apply", reply)
        self.assertIn("/jobs", reply)
        self.assertNotIn("name@company.com", reply)
        self.assertEqual(context.user_data, {})

    async def test_verify_invalid_email_keeps_state_with_cancel_hint(self):
        update = self._update("hr@company")
        result = await bot.verify_receive_email(update, self._ctx())
        self.assertEqual(result, bot.VERIFY_EMAIL)
        self.assertIn("/cancel", update.message.replies[0][0])

    async def test_cv_confirm_text_gets_button_reminder(self):
        update = self._update("ارسل")
        result = await bot.cv_confirm_text(update, self._ctx())
        self.assertEqual(result, bot.CV_CONFIRM)
        self.assertIn("ارسل الطلب", update.message.replies[0][0])


class MyCvFlowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        ensure_clear("companies", bot.COMPANY_HEADERS)
        ensure_clear("company_jobs", bot.JOB_HEADERS)
        ensure_clear("feed_jobs", bot.FEED_HEADERS)
        ensure_clear("seeker_prefs", bot.SEEKER_HEADERS)
        ensure_clear("applicants", bot.CSV_HEADERS)

    class _Message:
        def __init__(self, text=""):
            self.text = text
            self.replies = []

        async def reply_text(self, text, reply_markup=None, **kwargs):
            self.replies.append((text, reply_markup))

    def _update(self, text="", uid=601):
        user = type(
            "FakeUser", (), {"id": uid, "username": "seeker2", "first_name": "S"}
        )()
        return type(
            "FakeUpdate", (), {"message": self._Message(text), "effective_user": user}
        )()

    def _ctx(self):
        return type("FakeCtx", (), {"user_data": {}})()

    async def test_full_journey_from_spec_to_recommendations(self):
        owner = type(
            "FakeUser", (), {"id": 808, "username": "own2", "first_name": "O"}
        )()
        acc = bot.register_company(owner, "شركة المطابقة")
        bot.save_job_post(acc["company_id"], "مطلوب محاسبة خبرة سنتين ببغداد")

        context = self._ctx()
        start_update = self._update()
        result = await bot.mycv_start(start_update, context)
        self.assertIs(result, bot.MCV_SPEC)
        intro, markup = start_update.message.replies[0]
        self.assertIn("1/3", intro)
        callbacks = [
            btn.callback_data
            for row in markup.inline_keyboard
            for btn in row
        ]
        self.assertIn("mcvspec:محاسبة ومالية", callbacks)

        result = await bot.mcv_spec_text(self._update("محاسبة"), context)
        self.assertIs(result, bot.MCV_CITY)

        city_update = self._update("بغداد")
        result = await bot.mcv_city(city_update, context)
        self.assertIs(result, bot.MCV_SKILLS)
        self.assertIn("3/3", city_update.message.replies[0][0])

        skills_update = self._update("تقريرات")
        with mock.patch.object(bot.feed, "fetch_fresh_jobs", return_value=[]):
            result = await bot.mcv_skills(skills_update, context)
        self.assertIs(result, bot.ConversationHandler.END)
        final_text, final_markup = skills_update.message.replies[-1]
        self.assertIn("/follow", final_text)
        button_callbacks = [
            btn.callback_data
            for row in final_markup.inline_keyboard
            for btn in row
            if getattr(btn, "callback_data", None)
        ]
        self.assertTrue(
            any(str(c).startswith("applyjob:") for c in button_callbacks)
        )
        saved = bot.get_seeker(601)
        self.assertEqual(saved["city"], "بغداد")
        self.assertIn("محاسبة", saved["keywords"])
        self.assertIn("تقريرات", saved["keywords"])

    async def test_start_from_welcome_button_uses_query_message(self):
        class FakeMessage:
            def __init__(self):
                self.replies = []

            async def reply_text(self, text, reply_markup=None, **kwargs):
                self.replies.append((text, reply_markup))

        message = FakeMessage()

        class FakeQuery:
            data = "nav:mycv"

            async def answer(self):
                return None

        query = FakeQuery()
        query.message = message
        user = type(
            "FakeUser", (), {"id": 602, "username": "seeker3", "first_name": "S"}
        )()
        update = type(
            "FakeUpdate",
            (),
            {"message": None, "callback_query": query, "effective_user": user},
        )()
        context = self._ctx()
        result = await bot.mycv_start(update, context)
        self.assertIs(result, bot.MCV_SPEC)
        self.assertIn("1/3", message.replies[0][0])

    async def test_city_and_skills_accept_skip(self):
        context = self._ctx()
        context.user_data["mcv_spec"] = "محاسبة"
        result = await bot.mcv_city(self._update("/skip"), context)
        self.assertIs(result, bot.MCV_SKILLS)
        self.assertEqual(context.user_data["mcv_city"], "")
        with mock.patch.object(bot.feed, "fetch_fresh_jobs", return_value=[]):
            result = await bot.mcv_skills(self._update("/skip"), context)
        self.assertIs(result, bot.ConversationHandler.END)
        saved = bot.get_seeker(601)
        self.assertEqual(saved["city"], "")
        self.assertEqual(saved["keywords"], "محاسبة")


class HelpNavTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        ensure_clear("companies", bot.COMPANY_HEADERS)
        ensure_clear("company_jobs", bot.JOB_HEADERS)
        ensure_clear("feed_jobs", bot.FEED_HEADERS)

    def test_help_groups_and_hides_admin_from_seekers(self):
        text = bot.help_text(999999)
        self.assertIn("/mycv", text)
        self.assertIn("/apply", text)
        self.assertIn("/company", text)
        self.assertIn("باحث عن وظيفة", text)
        self.assertNotIn("/admin -", text)
        with mock.patch.object(bot, "is_admin", return_value=True):
            admin_text = bot.help_text(999999)
        self.assertIn("/admin", admin_text)

    class _Message:
        def __init__(self):
            self.replies = []

        async def reply_text(self, text, reply_markup=None, **kwargs):
            self.replies.append((text, reply_markup))

    def _callback_update(self, data, uid=707):
        message = self._Message()

        class FakeQuery:
            async def answer(self):
                return None

        query = FakeQuery()
        query.data = data
        query.message = message
        user = type(
            "FakeUser", (), {"id": uid, "username": "navuser", "first_name": "N"}
        )()
        update = type(
            "FakeUpdate",
            (),
            {"message": None, "callback_query": query, "effective_user": user},
        )()
        return update, message

    async def test_nav_jobs_lists_jobs(self):
        owner = type(
            "FakeUser", (), {"id": 818, "username": "own3", "first_name": "O"}
        )()
        acc = bot.register_company(owner, "شركة الازرار")
        bot.save_job_post(acc["company_id"], "مطلوب مصمم واجهات")
        update, message = self._callback_update("nav:jobs")
        context = type("FakeCtx", (), {"user_data": {}})()
        await bot.nav_button(update, context)
        text, markup = message.replies[0]
        self.assertIn("مصمم واجهات", text)

    async def test_nav_company_sets_pending_registration(self):
        update, message = self._callback_update("nav:company")
        context = type("FakeCtx", (), {"user_data": {}})()
        await bot.nav_button(update, context)
        self.assertTrue(context.user_data["pending_company_name"])
        self.assertIn("سجّل شركتك", message.replies[0][0])

    async def test_nav_help_renders_help_text(self):
        update, message = self._callback_update("nav:help")
        context = type("FakeCtx", (), {"user_data": {}})()
        await bot.nav_button(update, context)
        self.assertIn("/mycv", message.replies[0][0])


class CvSkipTests(unittest.IsolatedAsyncioTestCase):
    class _Message:
        def __init__(self, text):
            self.text = text
            self.replies = []

        async def reply_text(self, text, reply_markup=None, **kwargs):
            self.replies.append(text)

    def _ctx(self):
        return type("FakeCtx", (), {"user_data": {}})()

    async def test_edu_work_skills_accept_skip(self):
        context = self._ctx()
        update = type(
            "FakeUpdate", (), {"message": self._Message("/skip"), "effective_user": None}
        )()
        self.assertIs(await bot.cv_edu(update, context), bot.CV_WORK)
        self.assertEqual(context.user_data["education"], "")
        self.assertIs(await bot.cv_work(update, context), bot.CV_SKILLS)
        self.assertEqual(context.user_data["work_experience"], "")
        self.assertIs(await bot.cv_skills(update, context), bot.CV_LANGS)
        self.assertEqual(context.user_data["skills"], "")


class LegacyAndEntryUXTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        ensure_clear("companies", bot.COMPANY_HEADERS)
        ensure_clear("company_jobs", bot.JOB_HEADERS)
        ensure_clear("feed_jobs", bot.FEED_HEADERS)
        ensure_clear("applicants", bot.CSV_HEADERS)

    class _Query:
        def __init__(self, data):
            self.data = data
            self.edits = []
            self.message = None

        async def answer(self, *args, **kwargs):
            return None

        async def edit_message_text(self, text, reply_markup=None, **kwargs):
            self.edits.append((text, reply_markup))

    def _callback(self, data, uid=909):
        query = self._Query(data)
        user = type(
            "FakeUser", (), {"id": uid, "username": "leguser", "first_name": "L"}
        )()
        update = type(
            "FakeUpdate",
            (),
            {"message": None, "callback_query": query, "effective_user": user},
        )()
        return update, query

    def _ctx(self, args=None):
        return type("FakeCtx", (), {"user_data": {}, "args": args or []})()

    def _seed_job(self, caption="مطلوب محاسب للمسار القديم"):
        owner = type(
            "FakeUser", (), {"id": 819, "username": "own9", "first_name": "O"}
        )()
        acc = bot.register_company(owner, "شركة المسار القديم")
        row = bot.save_job_post(acc["company_id"], caption)
        return acc, row

    async def test_legacy_job_button_starts_apply_conversation(self):
        acc, row = self._seed_job()
        update, query = self._callback("job:" + str(row["job_id"]))
        result = await bot.apply_full_entry(update, self._ctx())
        self.assertEqual(result, bot.CV_NAME)
        text, _ = query.edits[0]
        self.assertIn("اسمك الكامل", text)
        self.assertIn(row["title"], text)

    async def test_legacy_applyfull_button_starts_apply_conversation(self):
        acc, row = self._seed_job("مطلوب مصمم للتقديم السريع")
        update, query = self._callback("applyfull:" + str(row["job_id"]))
        result = await bot.apply_full_entry(update, self._ctx())
        self.assertEqual(result, bot.CV_NAME)

    async def test_legacy_co_button_lists_company_jobs(self):
        acc, row = self._seed_job()
        update, query = self._callback("co:" + str(acc["company_id"]))
        result = await bot.legacy_company_entry(update, self._ctx())
        self.assertIs(result, bot.ConversationHandler.END)
        text, markup = query.edits[0]
        self.assertIn("اختر الوظيفة", text)
        callbacks = [
            btn.callback_data
            for r in markup.inline_keyboard
            for btn in r
            if getattr(btn, "callback_data", None)
        ]
        self.assertIn("applyjob:" + str(row["job_id"]), callbacks)

    async def test_legacy_co_button_without_jobs_uses_shared_no_jobs_text(self):
        update, query = self._callback("co:9999999")
        result = await bot.legacy_company_entry(update, self._ctx())
        self.assertIs(result, bot.ConversationHandler.END)
        self.assertEqual(query.edits[0][0], bot.NO_JOBS_TEXT)

    async def test_start_ref_company_and_jobs_use_shared_paths(self):
        class FakeMessage:
            def __init__(self):
                self.replies = []
                self.photos = []

            async def reply_text(self, text, reply_markup=None, **kwargs):
                self.replies.append((text, reply_markup))

            async def reply_photo(self, photo=None, caption=None, reply_markup=None,
                                  **kwargs):
                self.photos.append((caption, reply_markup))

        user = type(
            "FakeUser", (), {"id": 910, "username": "refseeker", "first_name": "R"}
        )()
        message = FakeMessage()
        update = type(
            "FakeUpdate", (), {"message": message, "effective_user": user}
        )()

        context = self._ctx(args=["company"])
        await bot.start(update, context)
        self.assertTrue(context.user_data["pending_company_name"])
        self.assertEqual(message.replies[0][0], bot.COMPANY_REG_PROMPT)

        message = FakeMessage()
        update = type(
            "FakeUpdate", (), {"message": message, "effective_user": user}
        )()
        await bot.start(update, self._ctx(args=["jobs"]))
        self.assertEqual(message.replies[0][0], bot.NO_JOBS_TEXT)

    async def test_jobs_command_empty_uses_shared_no_jobs_text(self):
        class FakeMessage:
            def __init__(self):
                self.replies = []

            async def reply_text(self, text, reply_markup=None, **kwargs):
                self.replies.append((text, reply_markup))

        message = FakeMessage()
        update = type(
            "FakeUpdate", (), {"message": message, "effective_user": None}
        )()
        await bot.jobs(update, self._ctx())
        self.assertEqual(message.replies[0][0], bot.NO_JOBS_TEXT)

    async def test_apply_full_entry_of_missing_job_refuses(self):
        update, query = self._callback("job:9999999")
        result = await bot.apply_full_entry(update, self._ctx())
        self.assertIs(result, bot.ConversationHandler.END)
        self.assertIn("مسكّرة", query.edits[0][0])


if __name__ == "__main__":
    unittest.main()
