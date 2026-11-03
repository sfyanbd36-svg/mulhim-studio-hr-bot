import asyncio
import csv
import io
import json
import logging
import os
import random
import re
import secrets
import warnings
from datetime import datetime, time, timedelta
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    ChatMemberHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    PicklePersistence,
    filters,
)
from telegram.warnings import PTBUserWarning
from telegram.error import RetryAfter

from cv_builder import build_cv_pdf
import channel_digest
import match_feed as feed
import storage
import wa_broadcast

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"
APPLICANTS_CSV = BASE_DIR / "applicants.csv"
COMPANIES_CSV = BASE_DIR / "companies.csv"
COMPANY_JOBS_CSV = BASE_DIR / "company_jobs.csv"
MESSAGES_LOG = BASE_DIR / "messages.log"
USERS_CSV = BASE_DIR / "users.csv"
REFERRALS_CSV = BASE_DIR / "referrals.csv"
SEEKER_PREFS_CSV = BASE_DIR / "seeker_prefs.csv"
SEEKER_STATE_FILE = BASE_DIR / "seeker_state.json"
ASSETS_DIR = BASE_DIR / "assets"
WELCOME_IMAGE = ASSETS_DIR / "welcome.jpg"
CVS_DIR = BASE_DIR / "cvs"
MAX_CAPTION_CHARS = 1000

STUDIO_NAME = "Mulhim Studio"
CONTACT_PHONE = "+964770178043"
CONTACT_EMAIL = "info@mulhimstudio.com"
CONTACT_ADDRESS = "بغداد، العراق"
WORK_HOURS = "9 صباحا - 6 مساء"
BOT_USERNAME = "mulhimstudio_hr_bot"
SITE_PUBLIC_URL = "https://sfyanbd36-svg.github.io/mulhim-jobs/"
CURATED_COMPANY_ID = "curated"
CURATED_COMPANY_NAME = "وظائف مختارة"
MARKET_COMPANY_ID = "market"
MARKET_COMPANY_NAME = "وظائف السوق"


def site_public_url():
    load_env_file()
    return os.environ.get("SITE_PUBLIC_URL", SITE_PUBLIC_URL)
BOT_LINK = "https://t.me/" + BOT_USERNAME
SHARE_TEXT = "بوت توظيف مجاني بالعراق: الشركات تنشر وظائفها والباحثون يتابعون الوظائف الجديدة"
GROUP_JOB_KEYWORDS = (
    "وظيفة شاغرة",
    "وظائف شاغرة",
    "شاغرة",
    "شاغر",
    "مطلوب موظف",
    "مطلوب موظفة",
    "مطلوب موظفين",
    "مطلوب عامل",
    "مطلوب كادر",
    "نشر وظيفة",
    "hiring",
    "vacancy",
)
GROUP_REPLY_COOLDOWN = 1800
SHARE_LINK = (
    "https://t.me/share/url?url="
    + quote(BOT_LINK)
    + "&text="
    + quote(SHARE_TEXT)
)

(
    CV_NAME,
    CV_PHONE,
    CV_FILE,
    CV_EMAIL,
    CV_CITY,
    CV_EDU,
    CV_WORK,
    CV_SKILLS,
    CV_LANGS,
    CV_SUMMARY,
    CV_CONFIRM,
    CO_PICK,
    JOB_PICK,
    POST_CAPTION,
    CO_REG_NAME,
    VERIFY_EMAIL,
    VERIFY_CODE,
    CURATE_CAPTION,
    CURATE_CHANNEL,
    MCV_SPEC,
    MCV_CITY,
    MCV_SKILLS,
) = range(22)

CV_STEPS_TOTAL = 10
SKIP_TOKENS = {"/skip", "skip", "-", "تخطي"}

CSV_HEADERS = [
    "timestamp",
    "user_id",
    "username",
    "full_name",
    "phone",
    "email",
    "city",
    "education",
    "work_experience",
    "skills",
    "languages",
    "summary",
    "company_id",
    "company",
    "job_id",
    "job",
    "cv_file",
]
OLD_APPLICANT_HEADERS = [
    "timestamp",
    "user_id",
    "username",
    "full_name",
    "phone",
    "job",
    "experience",
]
COMPANY_HEADERS = [
    "company_id",
    "name",
    "owner_user_id",
    "owner_username",
    "created_at",
    "verified",
    "verified_email",
]
JOB_HEADERS = [
    "job_id", "company_id", "title", "caption", "created_at", "active",
    "specialty", "apply_email",
]
USER_HEADERS = ["timestamp", "user_id", "username", "first_name"]
SEEKER_HEADERS = ["user_id", "username", "city", "keywords", "follow", "wa_phone", "updated_at"]
PHONE_PATTERN = re.compile(r"^\+?\d[\d\s\-]{6,17}$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
BROADCAST_DELAY_SECONDS = 0.05
JOBS_PAGE_SIZE = 10
DAILY_BACKUP_TIME = time(hour=3, minute=0, tzinfo=ZoneInfo("Asia/Baghdad"))
DAILY_DIGEST_TIME = time(hour=10, minute=0, tzinfo=ZoneInfo("Asia/Baghdad"))
SEEKER_DIGEST_TIME = time(hour=11, minute=0, tzinfo=ZoneInfo("Asia/Baghdad"))
TG_CHANNEL_POST_TIME = time(hour=11, minute=10, tzinfo=ZoneInfo("Asia/Baghdad"))
WA_STATUS_TIME = time(hour=13, minute=0, tzinfo=ZoneInfo("Asia/Baghdad"))
JOB_REMINDER_TIME = time(hour=19, minute=0, tzinfo=ZoneInfo("Asia/Baghdad"))
SEEKER_EVENING_TIME = time(hour=18, minute=30, tzinfo=ZoneInfo("Asia/Baghdad"))
COMPANY_NUDGE_TIME = time(hour=12, minute=30, tzinfo=ZoneInfo("Asia/Baghdad"))
JOB_STALE_DAYS = 14
PERSISTENCE_FILE = BASE_DIR / "bot_data.pickle"
BACKUP_FILES = [
    storage.DB_PATH,
    MESSAGES_LOG,
    APPLICANTS_CSV,
    COMPANIES_CSV,
    COMPANY_JOBS_CSV,
    USERS_CSV,
    SEEKER_PREFS_CSV,
    REFERRALS_CSV,
]

storage.register_schema(
    "applicants", CSV_HEADERS, csv_path=APPLICANTS_CSV, legacy_experience=True
)
storage.register_schema("companies", COMPANY_HEADERS, csv_path=COMPANIES_CSV)
storage.register_schema("company_jobs", JOB_HEADERS, csv_path=COMPANY_JOBS_CSV)
storage.register_schema("users", USER_HEADERS, csv_path=USERS_CSV)
storage.register_schema(
    "referrals", ["ref", "user_id", "at"], csv_path=REFERRALS_CSV
)
storage.register_schema(
    "seeker_prefs", SEEKER_HEADERS, csv_path=SEEKER_PREFS_CSV
)
storage.register_schema(
    "app_status",
    ["row_key", "user_id", "job_id", "status", "updated_at"],
)
storage.register_schema(
    "feed_jobs",
    [
        "key", "title", "company", "city", "text", "source",
        "url", "posted", "apply", "imported_at",
    ],
)
DEFAULT_WHATSAPP_BRIDGE_URL = "http://127.0.0.1:8788/send"
DEFAULT_COUNTRY_CODE = "964"
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)
logger = logging.getLogger("mulhim-bot")

warnings.filterwarnings(
    "ignore",
    message="If 'per_message=False'",
    category=PTBUserWarning,
)


def load_env_file():
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def get_bot_token():
    load_env_file()
    token = os.environ.get("MULHIM_BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit(
            "MULHIM_BOT_TOKEN is missing. Set it in the shell or in "
            + str(ENV_FILE)
        )
    return token


def get_admin_chat_ids():
    load_env_file()
    raw = os.environ.get("ADMIN_CHAT_IDS", "")
    admin_ids = []
    for part in raw.split(","):
        part = part.strip()
        if part.lstrip("-").isdigit():
            admin_ids.append(int(part))
    return admin_ids


def get_whatsapp_bridge_url():
    load_env_file()
    return os.environ.get("WHATSAPP_BRIDGE_URL", "").strip() or DEFAULT_WHATSAPP_BRIDGE_URL


def get_whatsapp_admins():
    load_env_file()
    raw = os.environ.get("WHATSAPP_ADMINS", "")
    numbers = []
    seen = set()
    for part in raw.split(","):
        digits = "".join(ch for ch in part.translate(ARABIC_DIGITS) if ch.isdigit())
        if digits.startswith("0") and len(digits) >= 9:
            digits = DEFAULT_COUNTRY_CODE + digits[1:]
        if len(digits) >= 8 and digits not in seen:
            seen.add(digits)
            numbers.append(digits)
    return numbers


async def notify_whatsapp(text):
    numbers = get_whatsapp_admins()
    if not numbers:
        return
    url = get_whatsapp_bridge_url()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            for number in numbers:
                response = await client.post(url, json={"phone": number, "text": text})
                if response.status_code != 200:
                    logger.warning(
                        "WhatsApp bridge HTTP %s for %s", response.status_code, number
                    )
    except Exception:
        logger.warning("WhatsApp bridge unreachable at %s", url, exc_info=True)


def now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_csv_rows(path):
    return storage.read_table(storage.table_name(path))


def append_rows(path, headers, rows, legacy_experience=False):
    storage.insert_rows(
        storage.table_name(path), headers, rows, legacy_experience=legacy_experience
    )


def next_id(path, key):
    return storage.next_id(storage.table_name(path), key)


def save_application(record):
    append_rows(APPLICANTS_CSV, CSV_HEADERS, [record], legacy_experience=True)


def log_free_message(user, text):
    flat_text = " ".join(text.split())
    handle_name = "@" + user.username if user.username else str(user.id)
    line = "{} | {} | {}\n".format(now_iso(), handle_name, flat_text)
    with MESSAGES_LOG.open("a", encoding="utf-8") as handle:
        handle.write(line)


def build_application_summary(record):
    telegram_user = record.get("username") or "-"
    lines = [
        "طلب تقديم جديد - {}".format(STUDIO_NAME),
        "",
        "الاسم: {}".format(record.get("full_name", "")),
        "الهاتف: {}".format(record.get("phone", "")),
    ]
    if record.get("email"):
        lines.append("الإيميل: " + record["email"])
    if record.get("city"):
        lines.append("المدينة: " + record["city"])
    lines.append(
        "الشركة: {}".format(record.get("company") or "-"),
    )
    lines.append("الوظيفة: {}".format(record.get("job") or "-"))
    lines.append("المؤهل العلمي: {}".format(record.get("education", "")))
    lines.append("الخبرة: {}".format(record.get("work_experience", "")))
    lines.append("المهارات: {}".format(record.get("skills", "")))
    if record.get("languages"):
        lines.append("اللغات: " + record["languages"])
    if record.get("summary"):
        lines.append("نبذة: " + record["summary"])
    if record.get("cv_file"):
        lines.append("ملف الـ CV: " + record["cv_file"])
    if record.get("feed_url"):
        lines.append("مصدر الإعلان: " + record["feed_url"])
    try:
        invites = referral_count(record.get("user_id", ""))
        if invites >= 3:
            lines.append(
                "الحالة: موصى به ✓ ({n} دعوة)".format(n=invites)
            )
    except Exception:
        pass
    lines.append(
        "مستخدم تيليجرام: @{telegram_user} ({user_id})".format(
            telegram_user=telegram_user, user_id=record.get("user_id", "")
        )
    )
    lines.append("التاريخ: {}".format(record.get("timestamp", "")))
    return "\n".join(lines)


async def notify_admins(application, text, pdf_path=None):
    for admin_id in get_admin_chat_ids():
        try:
            await application.bot.send_message(chat_id=admin_id, text=text)
        except Exception:
            logger.warning("Failed to notify admin %s", admin_id, exc_info=True)
            continue
        if pdf_path:
            try:
                with Path(pdf_path).open("rb") as handle:
                    await application.bot.send_document(
                        chat_id=admin_id,
                        document=handle,
                        filename=Path(pdf_path).name,
                        caption="سيرة ذاتية PDF - " + now_iso(),
                    )
            except Exception:
                logger.warning("CV PDF to admin %s failed", admin_id, exc_info=True)
    await notify_whatsapp(text)


async def notify_company_owner(application, company, text, pdf_path=None, reply_markup=None):
    owner_raw = str(company.get("owner_user_id") or "").strip()
    if not owner_raw.lstrip("-").isdigit():
        return False
    owner_id = int(owner_raw)
    try:
        await application.bot.send_message(
            chat_id=owner_id, text=text, reply_markup=reply_markup
        )
    except Exception:
        logger.warning("Company notify %s failed", owner_id, exc_info=True)
        return False
    if pdf_path:
        try:
            with Path(pdf_path).open("rb") as handle:
                await application.bot.send_document(
                    chat_id=owner_id,
                    document=handle,
                    filename=Path(pdf_path).name,
                    caption="سيرة ذاتية المتقدم - " + now_iso(),
                )
        except Exception:
            logger.warning("CV PDF to company %s failed", owner_id, exc_info=True)
            return False
    return True


def is_admin(user_id):
    return user_id in get_admin_chat_ids()


def record_referral(ref, user_id):
    try:
        storage.insert_rows(
            "referrals",
            ["ref", "user_id", "at"],
            [
                {
                    "ref": ref,
                    "user_id": user_id,
                    "at": datetime.now().isoformat(timespec="seconds"),
                }
            ],
        )
    except Exception:
        logger.warning("referral log failed", exc_info=True)


def referral_code(user_id):
    return "r" + str(user_id)


def referral_count(user_id):
    code = referral_code(user_id)
    invited = {
        str(row.get("user_id", ""))
        for row in storage.read_table("referrals")
        if str(row.get("ref", "")) == code
    }
    invited.discard(str(user_id))
    return len(invited)


def referral_tier(count):
    if count >= 10:
        return "ذهبي - أولوية عرض سيرتك عند كل نشرة"
    if count >= 3:
        return "فضي - توصية \"موصى به ✓\" بسيرتك عند الشركات"
    return "ابدائي - دعوة 3 أصدقاء للوصول للمستوى الفضي"


def latest_saved_application(user_id):
    rows = [
        row
        for row in load_applications()
        if str(row.get("user_id", "")) == str(user_id)
        and (row.get("full_name") or "").strip()
    ]
    if not rows:
        return None
    rows.sort(key=lambda row: row.get("timestamp") or "")
    return rows[-1]


def build_quick_record(saved, job, company):
    record = dict(saved)
    record["timestamp"] = now_iso()
    record["job_id"] = str(job["job_id"])
    record["job"] = job["title"]
    record["company_id"] = str(job["company_id"])
    record["company"] = company_display(company) if company else ""
    record["apply_email"] = job.get("apply_email", "")
    record["feed_url"] = job.get("feed_url", "")
    record.pop("status", None)
    return record


def set_application_status(user_id, job_id, status):
    storage.upsert_row(
        "app_status",
        ["row_key", "user_id", "job_id", "status", "updated_at"],
        {
            "row_key": "{uid}-{jid}".format(uid=user_id, jid=job_id),
            "user_id": str(user_id),
            "job_id": str(job_id),
            "status": status,
            "updated_at": now_iso(),
        },
        "row_key",
    )


def get_application_status(user_id, job_id):
    key = "{uid}-{jid}".format(uid=user_id, jid=job_id)
    for row in storage.read_table("app_status"):
        if str(row.get("row_key", "")) == str(key):
            return row.get("status") or ""
    return ""


def get_telegram_channels():
    load_env_file()
    raw = os.environ.get("TELEGRAM_CHANNELS", "")
    return [c.strip() for c in raw.split(",") if c.strip()]


def _write_telegram_channels(items):
    value = ", ".join(items)
    os.environ["TELEGRAM_CHANNELS"] = value
    lines = []
    if ENV_FILE.exists():
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    replaced = False
    for i, line in enumerate(lines):
        if line.strip().startswith("TELEGRAM_CHANNELS="):
            lines[i] = "TELEGRAM_CHANNELS=" + value
            replaced = True
    if not replaced:
        lines.append("TELEGRAM_CHANNELS=" + value)
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def register_channel(chat_id):
    load_env_file()
    token = str(chat_id)
    items = get_telegram_channels()
    if token in items:
        return False
    items.append(token)
    _write_telegram_channels(items)
    return True


def unregister_channel(chat_id):
    load_env_file()
    token = str(chat_id)
    items = get_telegram_channels()
    if token not in items:
        return False
    _write_telegram_channels([c for c in items if c != token])
    return True


def record_user(user):
    if storage.exists_value("users", "user_id", user.id):
        return
    storage.insert_rows(
        "users",
        USER_HEADERS,
        [
            {
                "timestamp": now_iso(),
                "user_id": user.id,
                "username": user.username or "",
                "first_name": user.first_name or "",
            }
        ],
    )


def load_applications(limit=None):
    rows = load_csv_rows(APPLICANTS_CSV)
    if limit is not None:
        rows = rows[-limit:]
    return rows


def count_applications_by_job():
    counter = {}
    for row in load_applications():
        job = row.get("job", "") or "-"
        counter[job] = counter.get(job, 0) + 1
    return counter


def known_broadcast_targets():
    seen = set()
    targets = []
    for row in load_csv_rows(USERS_CSV):
        raw_id = str(row.get("user_id", "") or "")
        if raw_id.lstrip("-").isdigit() and raw_id not in seen:
            seen.add(raw_id)
            targets.append(int(raw_id))
    return targets


def specialty_broadcast_targets(specialty):
    """(interested_user_ids, registered_count, mode) for a job specialty.

    Seekers with keywords that match the specialty get the alert; seekers
    with no /prefs keywords are treated as unknown and still get it.
    """
    registered = known_broadcast_targets()
    specialty = (specialty or "").strip()
    job_keywords = SPECIALTY_KEYWORDS.get(specialty, [])
    if not specialty or not job_keywords:
        return registered, len(registered), "all"
    prefs = {}
    for row in load_seeker_prefs():
        uid = str(row.get("user_id", "") or "")
        if uid.lstrip("-").isdigit():
            prefs[uid] = (row.get("keywords") or "").strip().lower()
    targets = []
    for user_id in registered:
        keywords = prefs.get(str(user_id), "")
        if not keywords:
            targets.append(user_id)
            continue
        if any(kw.lower() in keywords for kw in job_keywords):
            targets.append(user_id)
    return targets, len(registered), specialty


async def broadcast_text(bot, text, reply_markup=None, targets=None):
    if targets is None:
        targets = known_broadcast_targets()
    sent = 0
    failed = 0
    for user_id in targets:
        try:
            await bot.send_message(
                chat_id=user_id, text=text, reply_markup=reply_markup
            )
            sent += 1
        except RetryAfter as exc:
            await asyncio.sleep(exc.retry_after + 1)
            try:
                await bot.send_message(
                    chat_id=user_id, text=text, reply_markup=reply_markup
                )
                sent += 1
            except Exception:
                failed += 1
        except Exception:
            failed += 1
        await asyncio.sleep(BROADCAST_DELAY_SECONDS)
    return sent, failed, len(targets)


def get_companies():
    return load_csv_rows(COMPANIES_CSV)


def get_company(company_id):
    for row in get_companies():
        if str(row.get("company_id", "")) == str(company_id):
            return row
    return None


def ensure_curated_company():
    existing = get_company(CURATED_COMPANY_ID)
    if existing:
        return existing
    row = {
        "company_id": CURATED_COMPANY_ID,
        "name": CURATED_COMPANY_NAME,
        "owner_user_id": "",
        "owner_username": "",
        "created_at": now_iso(),
        "verified": "1",
        "verified_email": "",
    }
    append_rows(COMPANIES_CSV, COMPANY_HEADERS, [row])
    return row


def is_curated_company_id(company_id):
    return str(company_id or "") == CURATED_COMPANY_ID


def ensure_market_company():
    existing = get_company(MARKET_COMPANY_ID)
    if existing:
        return existing
    row = {
        "company_id": MARKET_COMPANY_ID,
        "name": MARKET_COMPANY_NAME,
        "owner_user_id": "",
        "owner_username": "",
        "created_at": now_iso(),
        "verified": "1",
        "verified_email": "",
    }
    append_rows(COMPANIES_CSV, COMPANY_HEADERS, [row])
    return row


def company_by_owner(user_id):
    for row in get_companies():
        if str(row.get("owner_user_id", "")) == str(user_id):
            return row
    return None


def register_company(user, name):
    company_id = next_id(COMPANIES_CSV, "company_id")
    row = {
        "company_id": company_id,
        "name": name,
        "owner_user_id": user.id,
        "owner_username": user.username or "",
        "created_at": now_iso(),
    }
    append_rows(COMPANIES_CSV, COMPANY_HEADERS, [row])
    return row


COMPANY_NUDGE_TEXT = (
    "🏢 {name}: {reason}\n\n"
    "انشر وظيفة جديدة مجاناً وب رسالة وحدة - المتقدمين يوصلون لك مباشرة."
)


def company_nudge_reason(company_id):
    jobs = get_company_jobs(str(company_id), active_only=False)
    if not jobs:
        return "ما نشرت أي وظيفة بعد"
    newest = max((job.get("created_at") or "" for job in jobs), default="")
    age_days = 0
    try:
        age_days = (datetime.now().astimezone() - datetime.fromisoformat(newest)).days
    except ValueError:
        pass
    active = [job for job in jobs if job.get("active", "1") == "1"]
    if not active:
        return "ماكو وظيفة نشطة عندكم حالياً"
    if age_days >= 7:
        return "آخر وظيفة من {n} يوم".format(n=age_days)
    return ""


FREE_MAIL_PREFIXES = (
    "gmail.",
    "yahoo.",
    "hotmail.",
    "outlook.",
    "live.",
    "icloud.",
    "proton",
    "aol.",
    "mail.ru",
)
VERIFY_CODE_TTL = 600
VERIFY_MAX_ATTEMPTS = 5
EMAIL_FULL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
EMAIL_EXTRACT_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def company_display(company, fallback="شركة"):
    if not company:
        return fallback
    name = company.get("name") or fallback
    if str(company.get("verified", "")).strip() == "1":
        return name + " ✓"
    return name


def set_verified_email(company_id, email):
    storage.update_rows(
        "companies",
        {"verified": "1", "verified_email": email},
        "company_id",
        company_id,
    )


def send_verify_email(to_addr, code):
    import smtplib

    from email.mime.text import MIMEText

    smtp_user = os.environ.get("OUTREACH_EMAIL", "")
    smtp_pass = os.environ.get("OUTREACH_APP_PASSWORD", "")
    sender_name = os.environ.get("OUTREACH_FROM_NAME", "Mulhim Studio")
    if not smtp_user or not smtp_pass:
        raise RuntimeError("OUTREACH_EMAIL/OUTREACH_APP_PASSWORD missing")
    message = MIMEText(
        "كود توثيق شركتك في بوت التوظيف:\n\n{code}\n\n"
        "الكود ينتهي خلال 10 دقائق. إذا مو إنت طلب التوثيق، تجاهل هالرسالة.".format(
            code=code
        ),
        "plain",
        "utf-8",
    )
    message["Subject"] = "Mulhim Studio - كود التوثيق"
    message["From"] = "{name} <{user}>".format(name=sender_name, user=smtp_user)
    message["To"] = to_addr
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
        server.login(smtp_user, smtp_pass)
        server.send_message(message)


def send_application_email(to_addr, record, summary, pdf_path):
    import smtplib

    from email.mime.base import MIMEBase
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.utils import formataddr

    smtp_user = os.environ.get("OUTREACH_EMAIL", "").strip()
    smtp_pass = os.environ.get("OUTREACH_APP_PASSWORD", "").strip()
    sender_name = os.environ.get("OUTREACH_FROM_NAME", "Mulhim Studio").strip()
    if not smtp_user or not smtp_pass:
        logger.warning("Application email skipped: SMTP not configured")
        return False
    message = MIMEMultipart()
    message["From"] = formataddr((sender_name, smtp_user))
    message["To"] = to_addr
    message["Subject"] = "طلب تقديم جديد - {job} - {name}".format(
        job=(record.get("job") or "وظيفة شاغرة")[:60],
        name=record.get("full_name", ""),
    )
    body = (
        "السلام عليكم،\n\n"
        "يتقدم لكم المتقدم التالية بياناته عبر بوت {studio}:\n\n"
        "{summary}\n\n"
        "السيرتان الذاتية مرفقة بالرسالة (PDF).\n\n"
        "المصدر: بوت توظيف {bot}\n"
    ).format(studio=STUDIO_NAME, summary=summary, bot=BOT_USERNAME)
    message.attach(MIMEText(body, "plain", "utf-8"))
    if pdf_path and Path(pdf_path).exists():
        with Path(pdf_path).open("rb") as handle:
            part = MIMEBase("application", "pdf")
            part.set_payload(handle.read())
        try:
            from email import encoders

            encoders.encode_base64(part)
        except Exception:
            logger.warning("PDF base64 encode failed", exc_info=True)
            return False
        part.add_header(
            "Content-Disposition",
            "attachment",
            filename=Path(pdf_path).name,
        )
        message.attach(part)
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
            server.login(smtp_user, smtp_pass)
            server.send_message(message)
        return True
    except Exception:
        logger.warning("Application email to %s failed", to_addr, exc_info=True)
        return False


JOB_SIGNAL_RE = re.compile(
    r"وظيف|وظايف|توظيف|مطلوب|شاغر|شاغرة|سيرتك|سيرتي|سيرة ذاتية|خبرة|مقابلة"
    r"|التقديم|مهندس|محاسب|مندوب|موظف|تخصص|بكالوريوس|دبلوم|درجة|hiring|vacancy"
    r"|apply|recruit|\bcv\b",
    re.IGNORECASE,
)
BLOCK_RULES = [
    (
        re.compile(
            r"ادفع|رسوم\s*(تسجيل|تقديم|تسجيلية|توظيف)|دفع\s*(مقدم|مسبق)"
            r"|money\s*transfer|western\s*union|registration\s*fee",
            re.IGNORECASE,
        ),
        "طلب فلوس او رسوم من المتقدم",
    ),
    (
        re.compile(
            r"استثمار|أرباح\s*(يومية|مضمونة|كبيرة)|ارباح\s*(يومية|مضمونة|كبيرة)"
            r"|دخل\s*(سهل|مضمون)|ربح\s*(مضمون|يومي)|بونزي|هرمي|pyramid|ponzi"
            r"|\bmlm\b|multi-?level",
            re.IGNORECASE,
        ),
        "محتوى استثماري او هرمي",
    ),
    (
        re.compile(
            r"\bforex\b|بيتكوين|بتكوين|\busdt\b|\bbtc\b|crypto|عملات رقمية|توصيات فوركس",
            re.IGNORECASE,
        ),
        "تجارة عملات او عملات رقمية",
    ),
    (
        re.compile(r"\bxxx\b|porn|onlyfans|للبالغين|إباحي|اباحي", re.IGNORECASE),
        "محتوى غير لائق",
    ),
    (
        re.compile(
            r"داعش|تنظيم\s*الدولة|القاعدة|حزب\s*الله|ميليشيا|مخدرات|قمار|رهانات",
            re.IGNORECASE,
        ),
        "محتوى مخالف او خطر",
    ),
]
MAX_LINKS_IN_CAPTION = 3
INFO_MIN_LETTERS = 20
CONTACT_RE = re.compile(
    r"\+?964|07\d[\d\s\-]{7,12}|[\w.+\-]+@[\w\-]+\.[A-Za-z]{2,}"
    r"|https?://|t\.me/|سيرتك|سيرتي|ابعث|ابعت|أرسل|ارسل|تواصل|واتساب|whatsapp"
    r"|التقديم|التسجيل",
    re.IGNORECASE,
)


def screen_job_caption(caption):
    violations = []
    for pattern, reason in BLOCK_RULES:
        if pattern.search(caption):
            violations.append(reason)
    stripped = re.sub(r"\s+", " ", caption).strip()
    letters = re.findall(r"[A-Za-z\u0621-\u064A]", stripped)
    if len(letters) < INFO_MIN_LETTERS:
        violations.append("قصير او عبثي بدون معلومات كافية")
    if re.search(r"(.)\1{5,}", stripped):
        violations.append("حروف مكررة بدون معنى")
    if not JOB_SIGNAL_RE.search(caption):
        violations.append("ما يذكر توظيف او وظيفة شاغرة")
    if not CONTACT_RE.search(caption):
        violations.append("ما فيه طريقة تواصل او تقديم (هاتف، إيميل، رابط، او ابعث سيرتك)")
    links = re.findall(r"https?://|t\.me/", caption, flags=re.IGNORECASE)
    if len(links) > MAX_LINKS_IN_CAPTION:
        violations.append("روابط كثيرة (الحد {n})".format(n=MAX_LINKS_IN_CAPTION))
    return violations


SPECIALTY_KEYWORDS = {
    "برمجة وتقنية": [
        "مبرمج", "مطور", "برمجة", "تطوير", "developer", "programmer",
        "software", "website", "web ", "app ", "mobile", "cloud", "data",
        "backend", "frontend", "devops", "flutter", "python", "react",
    ],
    "تصميم": [
        "مصمم", "تصميم", "designer", "design", "ui ", "ux ", "graphic",
        "جرافيك", "موشن", "after effect",
    ],
    "محاسبة ومالية": [
        "محاسب", "محاسبة", "مالية", "finance", "account", "accounting",
        "مالي", "cashier", "كاشير",
    ],
    "تسويق": [
        "تسويق", "marketing", "اعلان", "دعاية", "digital marketing", "سوشيال",
        "content", "محتوى",
    ],
    "مبيعات": [
        "مبيعات", "مندوب", "sales", "sell", "commercial", "account manager",
        "بيع",
    ],
    "موارد بشرية": [
        "موارد بشرية", "توظيف", "recruitment", "hr ", "human resource",
        "موارد",
    ],
    "شبكات ودعم فني": [
        "شبكات", "دعم فني", "technical support", "helpdesk", "network",
        "cisco", "it support", "Information Technology", "IT ",
    ],
    "تعليم وتدريب": [
        "معلم", "مدرس", "مدرّس", "تدريس", "تدريب", "teacher", "instructor",
        "lecturer", "trainer", "استاذ",
    ],
    "صحة وتمريض": [
        "ممرض", "تمريض", "طبيب", "صيدلي", "nurse", "nursing", "doctor",
        "pharmacy", "medical", "صيدلية",
    ],
    "قانون": ["قانون", "محام", "legal", "law", "lawyer", "قضائي"],
    "لوجستيات ومخازن": [
        "لوجست", "مخزن", "مخزون", "توصيل", "logistic", "warehouse",
        "supply chain", "delivery", "شحنة",
    ],
    "خدمة عملاء": [
        "خدمة عملاء", "كول سنتر", "customer service", "call center",
        "استقبال",
    ],
    "ضيافة ومطاعم": [
        "شيف", "طباخ", "نادل", "ضيافة", "مطعم", "فندق", "chef", "cook",
        "waiter", "hotel", "restaurant", "hospitality",
    ],
    "سائقين": ["سائق", "نقل", "driver", "توصيل بسيارة"],
    "فنيين": ["فني", "technician", "maintenance", "صيانة", "ميكانيك"],
    "إدارة": [
        "مدير", "إداري", "اداري", "سكرتير", "manager", "admin",
        "administration", "secretary", "supervisor",
    ],
    "هندسة": [
        "مهندس", "هندسة", "engineer", "engineering", "مدني", "ميكانيكية",
        "كهربائية", "civil", "mechanical", "electrical", "architect",
    ],
    "عمالة": [
        "عامل", "حرفي", "بنّاء", "بناء", "نجار", "حداد", "labor",
        "worker", "construction",
    ],
}


def detect_specialty(text):
    low = (text or "").lower()
    best, best_score = "", 0
    for specialty, keywords in SPECIALTY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw.lower() in low)
        if score > best_score:
            best, best_score = specialty, score
    return best


def save_job_post(company_id, caption, apply_email=""):
    job_id = next_id(COMPANY_JOBS_CSV, "job_id")
    first_line = ""
    for line in caption.split("\n"):
        if line.strip():
            first_line = line.strip()
            break
    title = first_line[:70]
    row = {
        "job_id": job_id,
        "company_id": str(company_id),
        "title": title,
        "caption": caption,
        "created_at": now_iso(),
        "active": "1",
        "specialty": detect_specialty(caption),
        "apply_email": (apply_email or "").strip().lower(),
    }
    append_rows(COMPANY_JOBS_CSV, JOB_HEADERS, [row])
    return row


def get_job(job_id):
    for row in load_csv_rows(COMPANY_JOBS_CSV):
        if str(row.get("job_id", "")) == str(job_id):
            return row
    return None


def set_job_active(job_id, value):
    updated_count = storage.update_rows(
        "company_jobs", {"active": value}, "job_id", job_id
    )
    if not updated_count:
        return None
    return get_job(job_id)


def get_company_jobs(company_id, active_only=True):
    rows = [
        row
        for row in load_csv_rows(COMPANY_JOBS_CSV)
        if str(row.get("company_id", "")) == str(company_id)
    ]
    if active_only:
        rows = [row for row in rows if row.get("active", "1") == "1"]
    return rows


def get_active_jobs(limit=10):
    rows = [
        row for row in load_csv_rows(COMPANY_JOBS_CSV) if row.get("active", "1") == "1"
    ]
    rows.reverse()
    return rows[:limit]


def get_all_active_jobs():
    rows = [
        row for row in load_csv_rows(COMPANY_JOBS_CSV) if row.get("active", "1") == "1"
    ]
    rows.reverse()
    return rows


def feed_jobs_rows():
    rows = storage.read_table("feed_jobs")
    return sorted(rows, key=lambda r: r.get("posted") or "", reverse=True)


def get_feed_job(key):
    key = str(key or "").strip()
    if not key:
        return None
    for row in feed_jobs_rows():
        if str(row.get("key", "")) == key:
            return row
    return None


def resolve_job_for_apply(raw_id):
    """Return a job-shaped dict for local jobs and applyable market jobs.

    Market feed jobs qualify only when the ad text carries an apply email;
    everything else falls through so the caller can refuse with the usual
    "open the source link" behaviour.
    """
    job = get_job(raw_id)
    if job:
        return dict(job)
    feed = get_feed_job(raw_id)
    if not feed:
        return None
    apply_email = (feed.get("apply") or "").strip().lower()
    if not apply_email:
        return None
    ensure_market_company()
    title = re.sub(r"\s+", " ", feed.get("title") or "").strip()[:70]
    caption = (feed.get("text") or "").strip()[:3000]
    return {
        "job_id": str(feed.get("key") or ""),
        "company_id": MARKET_COMPANY_ID,
        "title": title,
        "caption": caption,
        "created_at": feed.get("posted") or "",
        "active": "1",
        "specialty": detect_specialty(title + " " + caption),
        "apply_email": apply_email,
        "feed_url": (feed.get("url") or "").strip(),
    }


FEED_HEADERS = [
    "key", "title", "company", "city", "text", "source",
    "url", "posted", "apply", "imported_at",
]


def _insert_feed_jobs(jobs):
    now = datetime.now(ZoneInfo("Asia/Baghdad")).isoformat()
    existing_titles = {}
    for row in storage.read_table("feed_jobs"):
        existing_titles.setdefault(
            feed.normalize_title(row.get("title", "")), row.get("posted", "") or ""
        )
    new_count = 0
    for job in jobs:
        if storage.exists_value("feed_jobs", "key", job.get("key", "")):
            continue
        title_key = feed.normalize_title(job.get("title", ""))
        prev_posted = existing_titles.get(title_key)
        if prev_posted and _posted_within_days(prev_posted, job.get("posted", ""), 14):
            continue
        row = {
            "key": job.get("key", ""),
            "title": job.get("title", ""),
            "company": job.get("company", ""),
            "city": feed.resolve_city(
                job.get("city", ""), job.get("title", ""), job.get("text", "")
            ),
            "text": job.get("text", ""),
            "source": job.get("source", ""),
            "url": job.get("url", ""),
            "posted": job.get("posted", ""),
            "apply": job.get("apply", ""),
            "imported_at": now,
        }
        storage.insert_rows("feed_jobs", FEED_HEADERS, [row])
        existing_titles[title_key] = row["posted"]
        new_count += 1
    return new_count


def _posted_within_days(a, b, days):
    try:
        da = datetime.strptime(str(a)[:10], "%Y-%m-%d")
        db = datetime.strptime(str(b)[:10], "%Y-%m-%d")
        return abs((da - db).days) <= days
    except ValueError:
        return False


def ingest_feed_jobs(hours=72):
    return _insert_feed_jobs(feed.fetch_fresh_jobs(hours=hours))


async def ingest_tg_jobs(hours=48):
    jobs = await feed.fetch_tg_jobs(hours=hours)
    if not jobs:
        return 0
    return _insert_feed_jobs(jobs)


async def feed_ingest_job(context: ContextTypes.DEFAULT_TYPE):
    try:
        new_count = ingest_feed_jobs()
    except Exception:
        logger.warning("Feed ingest failed", exc_info=True)
        return
    try:
        new_count += await ingest_tg_jobs()
    except Exception:
        logger.warning("TG channel ingest failed", exc_info=True)
    if new_count <= 0:
        logger.info("Feed ingest: no new jobs")
        return
    logger.info("Feed ingest: %s new jobs", new_count)
    text = (
        "دفعة وظائف جديدة من السوق: {count}\n"
        "اكتب /jobs لشوفها، او /match اذا حاطت تفضيلاتك."
    ).format(count=new_count)
    for admin_id in get_admin_chat_ids():
        try:
            await context.bot.send_message(chat_id=admin_id, text=text)
        except Exception:
            logger.warning("Feed ingest notify to %s failed", admin_id, exc_info=True)
    try:
        alert_count = await push_follower_alerts(
            context, header="تنبيه فوري - وظائف جديدة تناسبك:"
        )
        if alert_count:
            logger.info("Feed ingest follower alerts: %s", alert_count)
        newest = feed_jobs_rows()[:5]
        if newest:
            lines = [
                "{i}) {title} - {url}".format(
                    i=i,
                    title=(row.get("title") or "")[:60],
                    url=row.get("url") or "",
                )
                for i, row in enumerate(newest, start=1)
            ]
            channel_text = (
                "{n} وظيفة جديدة بالسوق العراقي اليوم:\n\n{lines}\n\n"
                "كل الوظائف بالموقع: {site}\n"
                "سجّل بالبوت للمزيد: t.me/{bot}"
            ).format(
                n=new_count,
                lines="\n".join(lines),
                site=site_public_url(),
                bot=BOT_USERNAME,
            )
            await post_to_channels(context.bot, channel_text)
    except Exception:
        logger.warning("Feed ingest distribute failed", exc_info=True)
    await asyncio.to_thread(publish_site_safe)
    try:
        newest = feed_jobs_rows()[:5]
        if newest and wa_broadcast.allowed_groups():
            context.application.create_task(
                wa_broadcast.broadcast_digest(
                    newest, BOT_LINK, site_public_url()
                )
            )
            logger.info("WA group broadcast scheduled (%s jobs)", len(newest))
    except Exception:
        logger.warning("WA broadcast schedule failed", exc_info=True)


def visible_jobs():
    items = []
    for job in get_all_active_jobs():
        company = get_company(job["company_id"])
        items.append(
            {
                "local": True,
                "job_id": job["job_id"],
                "title": job.get("title", ""),
                "company": company_display(company),
                "specialty": job.get("specialty") or "",
            }
        )
    for row in feed_jobs_rows():
        company_name = (row.get("company") or "").strip()
        if company_name.casefold() in ("", "not specified", "n/a"):
            company_name = "السوق"
        title = re.sub(r"\s+", " ", (row.get("title") or "")).strip()
        items.append(
            {
                "local": False,
                "key": row.get("key", ""),
                "title": title[:70],
                "company": company_name[:40],
                "city": row.get("city") or "",
                "url": row.get("url") or "",
                "apply": (row.get("apply") or "").strip().lower(),
                "specialty": detect_specialty(
                    (row.get("title") or "") + " " + (row.get("text") or "")
                ),
            }
        )
    return items


def build_jobs_page(page):
    all_jobs = visible_jobs()
    total_pages = max(1, (len(all_jobs) + JOBS_PAGE_SIZE - 1) // JOBS_PAGE_SIZE)
    page = max(1, min(int(page), total_pages))
    start = (page - 1) * JOBS_PAGE_SIZE
    chunk = all_jobs[start : start + JOBS_PAGE_SIZE]
    lines = []
    keyboard = []
    for index, job in enumerate(chunk, start=start + 1):
        suffix = " ({city})".format(city=job["city"]) if job.get("city") else ""
        specialty = job.get("specialty") or ""
        spec_tag = " [{specialty}]".format(specialty=specialty) if specialty else ""
        lines.append(
            "{index}) {company} - {title}{spec}{suffix}".format(
                index=index,
                company=job["company"],
                title=job["title"],
                spec=spec_tag,
                suffix=suffix,
            )
        )
        if job["local"]:
            keyboard.append(
                [
                    InlineKeyboardButton(
                        "التقديم: " + job["title"][:30],
                        callback_data="applyjob:" + str(job["job_id"]),
                    )
                ]
            )
        else:
            row_buttons = []
            if job.get("apply"):
                row_buttons.append(
                    InlineKeyboardButton(
                        "التقديم بالسيرة: " + job["title"][:20],
                        callback_data="applyjob:" + str(job["key"]),
                    )
                )
            if job.get("url"):
                row_buttons.append(
                    InlineKeyboardButton("افتح المصدر", url=job["url"])
                )
            if row_buttons:
                keyboard.append(row_buttons)
    nav = []
    if page > 1:
        nav.append(
            InlineKeyboardButton("<< السابق", callback_data="jobspage:" + str(page - 1))
        )
    if page < total_pages:
        nav.append(
            InlineKeyboardButton("التالي >>", callback_data="jobspage:" + str(page + 1))
        )
    if nav:
        keyboard.append(nav)
    wa_share = "https://wa.me/?text=" + quote(
        "وظائف جديدة بالعراق تتابعها من البوت: " + BOT_LINK + "\nالموقع: " + site_public_url()
    )
    keyboard.append([InlineKeyboardButton("📱 شارك الوظائف بالواتساب", url=wa_share)])
    header = "الوظائف الشاغرة ({total} وظيفة - صفحة {page}/{pages}):\n\n".format(
        total=len(all_jobs), page=page, pages=total_pages
    )
    body = "\n".join(lines) if lines else "ماكو وظائف بهذي الصفحة."
    return (
        header + body + "\n\nاضغط زر الوظيفة اللي تبيها وبعدها عبي سيرتك.",
        InlineKeyboardMarkup(keyboard) if keyboard else None,
    )


def count_company_applicants(company_id):
    return sum(
        1
        for row in load_applications()
        if str(row.get("company_id", "")) == str(company_id)
    )


def build_decision_keyboard(record):
    user_id = str(record.get("user_id", ""))
    job_id = str(record.get("job_id", ""))
    if not user_id or not job_id:
        return None
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "طلب مقابلة",
                    callback_data="dec:interview:{uid}:{jid}".format(
                        uid=user_id, jid=job_id
                    ),
                ),
                InlineKeyboardButton(
                    "التواصل معه",
                    callback_data="dec:contact:{uid}:{jid}".format(
                        uid=user_id, jid=job_id
                    ),
                ),
            ]
        ]
    )


def find_application(user_id, job_id):
    matches = [
        row
        for row in load_applications()
        if str(row.get("user_id", "")) == str(user_id)
        and str(row.get("job_id", "")) == str(job_id)
    ]
    return matches[-1] if matches else None


def build_application_row(index, row):
    handle_name = "@" + row["username"] if row.get("username") else "بدون معرّف"
    date_part = (row.get("timestamp") or "").split("T")[0]
    company = row.get("company") or "-"
    return (
        "{index}) {name} | {phone}\n"
        "   {company} - {job} | {handle} ({user_id}) | {date}\n"
        "   {experience}"
    ).format(
        index=index,
        name=row.get("full_name", ""),
        phone=row.get("phone", ""),
        company=company,
        job=row.get("job", ""),
        handle=handle_name,
        user_id=row.get("user_id", ""),
        date=date_part,
        experience=row.get("work_experience", "") or row.get("experience", ""),
    )


def search_applications(query):
    needle = query.strip().lower()
    if not needle:
        return []
    matches = []
    for row in load_applications():
        haystack = " ".join(
            [
                row.get("full_name", ""),
                row.get("phone", ""),
                row.get("username", ""),
                row.get("job", ""),
                row.get("company", ""),
                row.get("email", ""),
                row.get("city", ""),
                row.get("skills", ""),
                str(row.get("user_id", "")),
            ]
        ).lower()
        if needle in haystack:
            matches.append(row)
    return matches


NO_JOBS_TEXT = "ماكو وظائف شاغلة حاليا. تابعنا، الوظائف الجديدة تنزل هنا."
COMPANY_REG_PROMPT = "سجّل شركتك برسالة وحدة — ابعثلي اسمها (من 2 لـ 60 حرف):"
NEED_COMPANY_TEXT = "سجّل شركتك أول بـ /company."


async def send_welcome(message, text, reply_markup=None):
    if not WELCOME_IMAGE.exists():
        await message.reply_text(text, reply_markup=reply_markup)
        return
    with WELCOME_IMAGE.open("rb") as handle:
        if len(text) <= MAX_CAPTION_CHARS:
            await message.reply_photo(photo=handle, caption=text, reply_markup=reply_markup)
            return
        await message.reply_photo(photo=handle)
    await message.reply_text(text, reply_markup=reply_markup)


def load_seeker_prefs():
    return load_csv_rows(SEEKER_PREFS_CSV)


def get_seeker(user_id):
    for row in load_seeker_prefs():
        if str(row.get("user_id", "")) == str(user_id):
            return row
    return None


def save_seeker(
    user_id, username=None, city=None, keywords=None, follow=None, wa_phone=None
):
    target = get_seeker(user_id)
    if target is None:
        target = {
            "user_id": str(user_id),
            "username": "",
            "city": "",
            "keywords": "",
            "follow": "0",
            "wa_phone": "",
            "updated_at": "",
        }
    if username is not None:
        target["username"] = username
    if city is not None:
        target["city"] = city
    if keywords is not None:
        target["keywords"] = keywords
    if follow is not None:
        target["follow"] = follow
    if wa_phone is not None:
        target["wa_phone"] = wa_phone
    target["updated_at"] = now_iso()
    return storage.upsert_row(
        "seeker_prefs", SEEKER_HEADERS, target, key_column="user_id"
    )


def seeker_profile(user_id):
    prefs = get_seeker(user_id) or {}
    city = (prefs.get("city") or "").strip()
    keywords = (prefs.get("keywords") or "").strip()
    if city or keywords:
        return city, keywords
    for row in reversed(load_applications()):
        if str(row.get("user_id", "")) == str(user_id):
            skills = (row.get("skills") or "").strip()
            job = (row.get("job") or "").strip()
            return (row.get("city") or "").strip(), "، ".join(x for x in (skills, job) if x)
    return "", ""


def load_seen_state():
    if not SEEKER_STATE_FILE.exists():
        return {}
    try:
        return json.loads(SEEKER_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("Seeker state unreadable, starting fresh", exc_info=True)
        return {}


def seeker_mark_seen(user_id, keys):
    state = load_seen_state()
    bucket = list(state.get(str(user_id), []))
    for key in keys:
        key = str(key or "")
        if key and key not in bucket:
            bucket.insert(0, key)
    state[str(user_id)] = bucket[:150]
    SEEKER_STATE_FILE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def seeker_internal_jobs():
    rows = []
    for job in get_all_active_jobs():
        company = get_company(job["company_id"])
        row = dict(job)
        row["company"] = company_display(company)
        rows.append(row)
    return feed.internal_jobs(rows)


def collect_recommendations(user_id, keyword_arg=None, limit=6, exclude_seen=False):
    city, keywords_raw = seeker_profile(user_id)
    if keyword_arg:
        keywords_raw = keyword_arg
    keywords = feed.parse_keywords(keywords_raw)
    try:
        external = feed.fetch_fresh_jobs(hours=72)
    except Exception:
        logger.warning("Job feed fetch failed", exc_info=True)
        external = []
    jobs = seeker_internal_jobs() + external
    if not jobs:
        return "ماكو وظائف حاليا - تابعنا، الجديد ينزل هنا.", None
    if city or keywords:
        picks = feed.recommend(jobs, keywords, city, limit=limit)
        header = "ترشيحات وظائف لك"
        if city:
            header += " | " + city
        if keywords:
            header += "\nالمهارات: " + "، ".join(keywords)
    else:
        ordered = sorted(jobs, key=lambda item: item.get("posted") or "", reverse=True)[:limit]
        picks = [(0, [], item) for item in ordered]
        header = "أحدث الوظائف بالسوق\nعيّن تفضيلاتك عشان تصير الترشيحات مطابقة: /prefs بغداد، محاسبة"
    if exclude_seen:
        seen = {str(key) for key in load_seen_state().get(str(user_id), [])}
        picks = [pick for pick in picks if str(pick[2].get("key")) not in seen]
    if not picks:
        return "خلصت ترشيحات اليوم — بكرة تنزل وظائف جديدة.", None
    return header, picks


def render_recommendations(header, picks):
    lines = [header, ""]
    keyboard = []
    for index, (_score, reasons, job) in enumerate(picks, start=1):
        title = re.sub(r"\s+", " ", (job.get("title") or "")).strip()[:70]
        company = (job.get("company") or "").strip()
        local = bool(job.get("job_id"))
        head = "{index}) {title}".format(index=index, title=title or "وظيفة")
        if company and company.lower() != "not specified":
            head += " — " + company
        lines.append(head)
        meta = []
        if job.get("city"):
            meta.append(job["city"])
        if reasons:
            meta.append("يطابق: " + "، ".join(reasons))
        if local:
            meta.append("وظيفة داخل المنصة")
        elif job.get("apply"):
            meta.append("للتقديم: " + job["apply"])
        elif job.get("posted"):
            meta.append("نُشرت: " + str(job.get("posted"))[:10])
        if meta:
            lines.append("   " + " | ".join(meta))
        lines.append("")
        if local:
            keyboard.append(
                [
                    InlineKeyboardButton(
                        "تقدّم: " + (title[:24] or "الوظيفة"),
                        callback_data="applyjob:" + str(job.get("job_id")),
                    )
                ]
            )
        elif job.get("url"):
            keyboard.append(
                [
                    InlineKeyboardButton(
                        "فتح الإعلان: " + (title[:24] or "الوظيفة"),
                        url=job["url"],
                    )
                ]
            )
    text = "\n".join(lines).strip()
    text += "\n\nاضغط زر الوظيفة للتقديم او فتح الإعلان."
    return text, (InlineKeyboardMarkup(keyboard) if keyboard else None)


async def match_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    record_user(update.effective_user)
    arg = " ".join(context.args).strip() or None
    try:
        header, picks = collect_recommendations(update.effective_user.id, keyword_arg=arg)
    except Exception:
        logger.warning("/match failed", exc_info=True)
        await update.message.reply_text("صار خطأ بجلب الوظائف - جرب بعد شوي.")
        return
    if picks is None:
        await update.message.reply_text(header)
        return
    text, markup = render_recommendations(header, picks)
    await update.message.reply_text(text, reply_markup=markup)


async def prefs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    record_user(update.effective_user)
    user = update.effective_user
    arg = " ".join(context.args).strip()
    if not arg:
        current = get_seeker(user.id) or {}
        if current.get("city") or current.get("keywords"):
            await update.message.reply_text(
                "تفضيلاتك الحالية:\n"
                "المدينة: {city}\n"
                "المهارات: {kw}\n"
                "المتابعة اليومية: {follow}\n\n"
                "تعدلها: /prefs بغداد، محاسبة، مبيعات".format(
                    city=current.get("city") or "-",
                    kw=current.get("keywords") or "-",
                    follow="مفعّلة" if current.get("follow") == "1" else "مطفية",
                )
            )
        else:
            await update.message.reply_text(
                "اكتب تفضيلاتك بهالشكل:\n"
                "/prefs بغداد، محاسبة، مبيعات\n\n"
                "كلمة بعد فاصلة = مدينة او مهارة.\n"
                "بعدها: /match يعرض الترشيحات، و /follow يفعّل الإرسال اليومي."
            )
        return
    parts = [part.strip() for part in re.split(r"[،,\n]+", arg) if part.strip()]
    city = parts[0]
    keywords = "، ".join(parts[1:])
    save_seeker(user.id, username=(user.username or ""), city=city, keywords=keywords)
    try:
        header, picks = collect_recommendations(user.id, limit=5)
    except Exception:
        logger.warning("/prefs match failed", exc_info=True)
        await update.message.reply_text(
            "تم حفظ التفضيلات: {city} | {kw}".format(city=city, kw=keywords or "-")
        )
        return
    if picks is None:
        await update.message.reply_text(
            "تم حفظ التفضيلات: {city} | {kw}\n{body}".format(
                city=city, kw=keywords or "-", body=header
            )
        )
        return
    text, markup = render_recommendations(header, picks)
    await update.message.reply_text(
        "تم حفظ التفضيلات: {city} | {kw}\n\n{body}".format(
            city=city, kw=keywords or "-", body=text
        ),
        reply_markup=markup,
    )


def _mcv_reply_target(update):
    return update.message or (
        update.callback_query.message if update.callback_query else None
    )


async def mycv_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    record_user(update.effective_user)
    target = _mcv_reply_target(update)
    if target is None:
        return
    prefs = get_seeker(update.effective_user.id) or {}
    intro = ""
    if prefs.get("city") or prefs.get("keywords"):
        intro = (
            "تفضيلاتك الحالية: {city} | {kw}\n"
            "اختر جديد لتحديثها:\n\n"
        ).format(city=prefs.get("city") or "-", kw=prefs.get("keywords") or "-")
    keyboard = []
    for specialty, count in specialty_counts()[:10]:
        if specialty == "غير مصنف":
            continue
        keyboard.append(
            [
                InlineKeyboardButton(
                    "{specialty} ({count})".format(specialty=specialty, count=count),
                    callback_data="mcvspec:" + specialty,
                )
            ]
        )
    await target.reply_text(
        intro
        + "1/3 - اختر تخصصك (اضغط زر او اكتبه بحرية):\n"
        "مثال: محاسبة، مبرمج، هندسة...",
        reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None,
    )
    return MCV_SPEC


async def _mcv_ask_city(target, context):
    await target.reply_text(
        "2/3 - وين تبي تشتغل؟ اكتب مدينتك (بغداد، اربيل، البصرة...)\n"
        "او اكتب /skip إذا مو محدد."
    )
    return MCV_CITY


async def mcv_spec_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["mcv_spec"] = query.data.split(":", 1)[1][:60]
    return await _mcv_ask_city(query.message, context)


async def mcv_spec_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["mcv_spec"] = update.message.text.strip()[:60]
    return await _mcv_ask_city(update.message, context)


async def mcv_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if is_skip(text):
        city = ""
    elif len(text) < 2 or len(text) > 60:
        await update.message.reply_text(
            "اكتب اسم المدينة (من 2 لـ 60 حرف) او /skip:"
        )
        return MCV_CITY
    else:
        city = text
    context.user_data["mcv_city"] = city
    await update.message.reply_text(
        "3/3 - خبراتك/مهاراتك (اختياري) - افصل بينها بفاصلة\n"
        "مثال: Excel, محاسبة, تقريرات\n"
        "اكتب /skip إذا مو تبي."
    )
    return MCV_SKILLS


async def mcv_skills(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    spec = (context.user_data.pop("mcv_spec", "") or "").strip()
    city = (context.user_data.pop("mcv_city", "") or "").strip()
    text = update.message.text.strip()
    skills = "" if is_skip(text) else text[:200]
    keywords = "، ".join(part for part in (spec, skills) if part)
    save_seeker(user.id, username=(user.username or ""), city=city, keywords=keywords)
    try:
        header, picks = collect_recommendations(user.id, limit=5)
    except Exception:
        logger.warning("mycv recommendations failed", exc_info=True)
        await update.message.reply_text(
            "صار خطأ بالمطابقة - جرب بعد شوي، او شوف /jobs كل الوظائف."
        )
        return ConversationHandler.END
    if picks is None:
        await update.message.reply_text(
            header + "\n\nشوف كل الوظائف: /jobs\nاو غيّر تخصصك: /specialties"
        )
        return ConversationHandler.END
    body, markup = render_recommendations(header, picks)
    await update.message.reply_text(
        body + "\n\nفعّل التنبيه اليومي حتى يجيك الجديد: /follow",
        reply_markup=markup,
    )
    return ConversationHandler.END


async def _handle_wa_phone_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    raw = (update.message.text or "").strip()
    lowered = raw.lower()
    if lowered in ("لا", "لأ", "لا شكرا", "لا شكراً", "no", "skip"):
        await update.message.reply_text("تمام، تنبيهات تيليجرام بس.")
        return
    digits = "".join(ch for ch in raw.translate(ARABIC_DIGITS) if ch.isdigit())
    if digits.startswith("0") and len(digits) >= 10:
        digits = DEFAULT_COUNTRY_CODE + digits[1:]
    if len(digits) < 9:
        await update.message.reply_text(
            "الرقم غير صحيح. ابعته مرة ثانية (مثال: 07712345678) او اكتب لا."
        )
        context.user_data["pending_wa_phone"] = True
        return
    save_seeker(user.id, username=(user.username or ""), wa_phone=digits)
    await update.message.reply_text(
        "تمام، بيوصلك تنبيه واتساب مع تنبيهات تيليجرام بالوقت نفسه."
    )


async def follow_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    record_user(update.effective_user)
    user = update.effective_user
    current = get_seeker(user.id) or {}
    if not (current.get("city") or current.get("keywords")):
        await update.message.reply_text(
            "قبلها اكتب تفضيلاتك: /prefs بغداد، محاسبة\nبعدها فعّل المتابعة بـ /follow"
        )
        return
    if str(current.get("follow", "")) == "1":
        save_seeker(user.id, username=(user.username or ""), follow="0")
        await update.message.reply_text("تلغيت المتابعة اليومية. ترجع تفعّلها بـ /follow")
        return
    save_seeker(user.id, username=(user.username or ""), follow="1")
    context.user_data["pending_wa_phone"] = True
    await update.message.reply_text(
        "تفعّلت المتابعة - كل يوم الساعة 11 صباحا ارسل لك 3 وظائف مطابقة لتفضيلاتك.\n\n"
        "تبي تنبيه واتساب بعد؟ ابعت رقمك (مثال: 07712345678) او اكتب لا."
    )


async def push_follower_alerts(
    context, header="وظائف جديدة تناسبك اليوم:", include_wa=True
):
    rows = [row for row in load_seeker_prefs() if str(row.get("follow", "")) == "1"]
    if not rows:
        logger.info("Follower alerts: no followers")
        return 0
    sent_count = 0
    for row in rows:
        user_id = row.get("user_id")
        try:
            _header, picks = collect_recommendations(user_id, limit=3, exclude_seen=True)
        except Exception:
            logger.warning("Follower alert collect failed for %s", user_id, exc_info=True)
            continue
        if picks is None:
            continue
        text, markup = render_recommendations(header, picks)
        try:
            await context.bot.send_message(chat_id=int(user_id), text=text, reply_markup=markup)
            seeker_mark_seen(user_id, [pick[2].get("key") for pick in picks])
            sent_count += 1
        except Exception:
            logger.warning("Follower alert send failed for %s", user_id, exc_info=True)
        wa_phone = (row.get("wa_phone") or "").strip() if include_wa else ""
        if wa_phone:
            try:
                await wa_broadcast.send_dm(
                    wa_phone,
                    header + "\n\n" + text.split("\n\n")[0][:400]
                    + "\n\nالتفاصيل بالبوت: " + BOT_LINK,
                )
                await asyncio.sleep(random.uniform(2.0, 5.0))
            except Exception:
                logger.warning("WA follower alert failed for %s", user_id, exc_info=True)
    return sent_count


async def post_to_channels(bot, text, reply_markup=None):
    channels = get_telegram_channels()
    ok = 0
    for channel in channels:
        try:
            await bot.send_message(chat_id=channel, text=text, reply_markup=reply_markup)
            ok += 1
        except Exception:
            logger.warning("Channel post to %s failed", channel, exc_info=True)
    return ok


MEMBER_STATUSES = ("member", "administrator", "creator")


def join_promo_text(title):
    return (
        "تم ربط «{title}» مع بوت ملهم ✓\n\n"
        "🚀 من الحين تنزل الوظائف الجديدة هني تلقائياً كل 6 ساعات\n\n"
        "🏢 الشركات تنزل وظيفتها برسالة وحدة والبوت يوزعها فوراً\n"
        "📄 المتقدمين يقدّمون بسيرتهم PDF ويصلكم إشعار فوري\n\n"
        "البوت: t.me/{bot}\n"
        "الموقع: {site}\n\n"
        "الخدمة مجانية للجميع ✅"
    ).format(title=title or "هذه المجموعة", bot=BOT_USERNAME, site=site_public_url())


async def chat_membership_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    membership = update.my_chat_member
    if not membership:
        return
    chat = membership.chat
    if chat.type not in ("group", "supergroup", "channel"):
        return
    was_member = membership.old_chat_member.status in MEMBER_STATUSES
    is_member = membership.new_chat_member.status in MEMBER_STATUSES
    if is_member and not was_member:
        if register_channel(chat.id):
            logger.info("Channel registered: %s (%s)", chat.id, chat.title)
        try:
            await context.bot.send_message(
                chat_id=chat.id, text=join_promo_text(chat.title)
            )
        except Exception:
            logger.warning("Join promo post failed for %s", chat.id, exc_info=True)
    elif was_member and not is_member:
        if unregister_channel(chat.id):
            logger.info("Channel unregistered: %s (%s)", chat.id, chat.title)


def publish_site_safe():
    try:
        import site_gen

        ok = site_gen.publish_site()
        logger.info("site publish: %s", ok)
    except Exception:
        logger.warning("site publish failed", exc_info=True)


async def seeker_digest_job(context: ContextTypes.DEFAULT_TYPE):
    sent_count = await push_follower_alerts(context)
    logger.info("Seeker digest: %s messages sent", sent_count)


async def seeker_evening_job(context: ContextTypes.DEFAULT_TYPE):
    sent_count = await push_follower_alerts(
        context,
        header="ملخص آخر 24 ساعة - وظائف جديدة تناسبك:",
        include_wa=False,
    )
    logger.info("Seeker evening alert: %s messages sent", sent_count)


async def company_nudge_job(context: ContextTypes.DEFAULT_TYPE):
    now_ts = datetime.now().timestamp()
    stamped = context.bot_data.setdefault("company_nudge_sent", {})
    for company in storage.read_table("companies"):
        company_id = str(company.get("company_id", ""))
        owner = company.get("owner_user_id", "")
        if not company_id or not owner:
            continue
        reason = company_nudge_reason(company_id)
        if not reason:
            continue
        if now_ts - float(stamped.get(company_id, 0)) < 7 * 86400:
            continue
        stamped[company_id] = now_ts
        try:
            await context.bot.send_message(
                chat_id=int(owner),
                text=COMPANY_NUDGE_TEXT.format(
                    name=company.get("name", "شركتك"), reason=reason
                ),
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "🏢 انشر وظيفة جديدة",
                                callback_data="nav:company",
                            )
                        ]
                    ]
                ),
            )
            logger.info("Company nudge sent to %s", company_id)
        except Exception:
            logger.warning("Company nudge to %s failed", owner)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    record_user(update.effective_user)
    ref = ""
    if getattr(context, "args", None):
        ref = str(context.args[0]).strip()[:32]
    if ref == "company":
        context.user_data["pending_company_name"] = True
        await update.message.reply_text(COMPANY_REG_PROMPT)
        return
    if ref == "jobs":
        await send_jobs_list(update.message)
        return
    if ref:
        record_referral(ref, update.effective_user.id)
    admin_note = "\n🔧 للادارة: /admin" if is_admin(update.effective_user.id) else ""
    await send_welcome(
        update.message,
        "بوت {studio} — وظائف العراق بمكان واحد.\n\n"
        "👤 باحث عن وظيفة: اضغط «سجّل سيرتي» وبنگلك الشغل المناسب.\n"
        "🏢 صاحب شركة: اضغط «انشر وظيفة» وسجّل شركتك برسالة وحدة.\n\n"
        "الاوامر كاملة: /help{note}".format(studio=STUDIO_NAME, note=admin_note),
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "💼 سجّل سيرتي ورشّحني",
                        callback_data="nav:mycv",
                    ),
                    InlineKeyboardButton(
                        "🏢 انشر وظيفة",
                        callback_data="nav:company",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "📋 كل الوظائف", callback_data="nav:jobs"
                    ),
                    InlineKeyboardButton(
                        "❓ شلون أستخدمه", callback_data="nav:help"
                    ),
                ],
                [
                    InlineKeyboardButton("📤 شارك البوت", url=SHARE_LINK),
                    InlineKeyboardButton(
                        "📱 واتساب",
                        url="wa.me/?text="
                        + quote(
                            "بوت توظيف مجاني بالعراق — وظائف وسيرة PDF: " + BOT_LINK
                        ),
                    ),
                ],
            ]
        ),
    )
    company_id = context.user_data.get("company_id")
    if company_id:
        reason = company_nudge_reason(company_id)
        if reason:
            company = get_company(company_id) or {}
            await update.message.reply_text(
                COMPANY_NUDGE_TEXT.format(
                    name=company.get("name", "شركتك"), reason=reason
                ),
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "🏢 انشر وظيفة جديدة",
                                callback_data="nav:company",
                            )
                        ]
                    ]
                ),
            )


def help_text(user_id):
    lines = [
        "👤 باحث عن وظيفة:",
        "/mycv - احفظ تخصصك ومدينتك وبنگلك الوظائف المناسبة",
        "/apply - كل الوظائف الشاغرة - اضغط زر التقديم على اللي تريدها",
        "/specialties - تصفح الوظائف حسب الاختصاص",
        "/match - ترشيحات مطابقة لمدينتك ومهاراتك",
        "/follow - تنبيه يومي بالوظائف الجديدة",
        "/mystatus - حالة طلباتك (قيد المراجعة / مقابلة)",
        "",
        "🏢 للشركات:",
        "/company - سجّل شركتك وانشر وظائفك برسالة وحدة",
        "/postjob - نشر وظيفة جديدة",
        "/verify - توثيق الشركة - علامة ✓ للمتقدمين",
        "/mystats - احصائيات متقدميك",
        "",
        "✉ عام:",
        "/prefs بغداد، محاسبة - احفظ تفضيلاتك يدوياً",
        "/findjob كلمة - بحث سريع بالوظائف",
        "/ref - رابط دعواتك | /share - رسالة مشاركة | /top - لوحة الدعاة",
        "/contact - تواصل معانا",
        "/cancel - إلغاء أي عملية ماگدرتك تكملها",
    ]
    if is_admin(user_id):
        lines += ["", "/admin - مساعدة الادارة"]
    return "\n".join(lines)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(help_text(update.effective_user.id))


async def nav_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    target = query.data.split(":", 1)[-1]
    if target == "jobs":
        await send_jobs_list(query.message)
    elif target == "company":
        context.user_data["pending_company_name"] = True
        await query.message.reply_text(COMPANY_REG_PROMPT)
    elif target == "help":
        await query.message.reply_text(help_text(update.effective_user.id))


async def jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_jobs_list(update.message)


async def send_jobs_list(target):
    if not visible_jobs():
        await target.reply_text(NO_JOBS_TEXT)
        return
    text, markup = build_jobs_page(1)
    await target.reply_text(text, reply_markup=markup)


async def jobs_page(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        page = int(query.data.rsplit(":", 1)[-1])
    except ValueError:
        page = 1
    text, markup = build_jobs_page(page)
    try:
        await query.edit_message_text(text, reply_markup=markup)
    except Exception:
        logger.info("jobs page edit failed, sending new message")
        await query.message.reply_text(text, reply_markup=markup)


def search_jobs(query):
    cleaned = str(query or "").strip()
    needle = cleaned.casefold()
    label = cleaned if cleaned in SPECIALTY_KEYWORDS else ""
    matches = []
    for job in get_all_active_jobs():
        blob = (
            job.get("title", "") + " " + job.get("caption", "") + " " + job.get("specialty", "")
        ).casefold()
        if needle in blob or (label and detect_specialty(job.get("caption", "")) == label):
            matches.append(job)
    feed_matches = []
    for row in feed_jobs_rows():
        title = (row.get("title") or "").strip()
        text = (row.get("text") or "").strip()
        blob = (title + " " + text + " " + (row.get("city") or "")).casefold()
        if label:
            if detect_specialty(title + " " + text) == label or needle in blob:
                feed_matches.append(row)
        elif needle in blob:
            feed_matches.append(row)
    return matches, feed_matches


async def find_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reply_target = update.message or (
        update.callback_query.message if update.callback_query else None
    )
    if reply_target is None:
        return
    query = " ".join(context.args).strip()
    if not query:
        await reply_target.reply_text(
            "اكتب كلمة البحث:\n"
            "/findjob محاسب\n"
            "او اختصر: /specialties تختار تخصصك وبتطلع وظائفه بس.\n"
            "يبحث بالمسمى الوظيفي وبنص الإعلان (شركة، مدينة، شرط...)."
        )
        return
    matches, feed_matches = search_jobs(query)
    if not matches and not feed_matches:
        await reply_target.reply_text(
            "ما لقينا وظيفة فيها «{q}» - جرب كلمة ثانية او شوف /jobs كلهن.".format(
                q=query
            )
        )
        return
    matches = matches[:20]
    lines = []
    keyboard = []
    for index, job in enumerate(matches, start=1):
        company = get_company(job["company_id"])
        company_name = company_display(company)
        specialty = job.get("specialty") or ""
        spec_tag = " [{specialty}]".format(specialty=specialty) if specialty else ""
        lines.append(
            "{index}) {company} - {title}{spec} (#{jid})".format(
                index=index,
                company=company_name,
                title=job["title"],
                spec=spec_tag,
                jid=job["job_id"],
            )
        )
        keyboard.append(
            [
                InlineKeyboardButton(
                    "التقديم: " + job["title"][:30],
                    callback_data="applyjob:" + str(job["job_id"]),
                )
            ]
        )
    total_found = len(matches) + len(feed_matches)
    if feed_matches:
        lines.append("")
        lines.append("من السوق:")
        for index, row in enumerate(feed_matches[:8], start=len(matches) + 1):
            has_apply = (row.get("apply") or "").strip()
            lines.append(
                "{index}) {title}{tag} — {url}".format(
                    index=index,
                    title=(row.get("title") or "").strip(),
                    tag=" ✉" if has_apply else "",
                    url=row.get("url") or "-",
                )
            )
            row_buttons = []
            if has_apply:
                row_buttons.append(
                    InlineKeyboardButton(
                        "التقديم بالسيرة: "
                        + (row.get("title") or "وظيفة")[:20],
                        callback_data="applyjob:" + str(row.get("key") or ""),
                    )
                )
            if row.get("url"):
                row_buttons.append(
                    InlineKeyboardButton("افتح المصدر", url=row["url"])
                )
            if row_buttons:
                keyboard.append(row_buttons)
    header = "نتائج بحث «{q}» ({n} وظيفة):\n\n".format(q=query, n=total_found)
    body = "\n".join(lines)
    if keyboard:
        footer = "\n\nاضغط زر الوظيفة اللي تبيها وبعدها عبي سيرتك."
        markup = InlineKeyboardMarkup(keyboard)
    else:
        footer = "\n\nاكتب /apply عشان تتقدم، او /jobs تشوف كل الوظائف."
        markup = None
    await reply_target.reply_text(
        header + body + footer,
        reply_markup=markup,
    )


def specialty_counts():
    counts = {}
    for job in get_all_active_jobs():
        specialty = (job.get("specialty") or "").strip() or "غير مصنف"
        counts[specialty] = counts.get(specialty, 0) + 1
    for row in feed_jobs_rows():
        specialty = detect_specialty(
            (row.get("title") or "") + " " + (row.get("text") or "")
        ).strip() or "غير مصنف"
        counts[specialty] = counts.get(specialty, 0) + 1
    return sorted(counts.items(), key=lambda item: item[1], reverse=True)


async def specialties_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    record_user(update.effective_user)
    ordered = specialty_counts()
    if not ordered:
        await update.message.reply_text(
            "ماكو وظائف حاليا - تابعنا، الجديد ينزل هنا."
        )
        return
    lines = ["الاختصاصات المتاحة ({n} اختصاص):\n".format(n=len(ordered))]
    keyboard = []
    for specialty, count in ordered[:16]:
        lines.append("- {specialty}: {count} وظيفة".format(specialty=specialty, count=count))
        keyboard.append(
            [
                InlineKeyboardButton(
                    "{specialty} ({count})".format(specialty=specialty, count=count),
                    callback_data="spec:" + specialty,
                )
            ]
        )
    footer = "\nاضغط اختصاص لتشوف وظائفه، او /findjob كلمة للبحث المباشر."
    await update.message.reply_text(
        "\n".join(lines) + footer,
        reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None,
    )


async def specialty_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    specialty = query.data.split(":", 1)[1]
    context.args = [specialty]
    await find_jobs(update, context)


async def contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "للتواصل مع ادارة {studio}:\n\n"
        "الهاتف: {phone}\n"
        "الإيميل: {email}\n"
        "العنوان: {address}\n\n"
        "ساعات العمل: {hours}".format(
            studio=STUDIO_NAME,
            phone=CONTACT_PHONE,
            email=CONTACT_EMAIL,
            address=CONTACT_ADDRESS,
            hours=WORK_HOURS,
        )
    )


def cv_step_prompt(step, text):
    return "الخطوة {step} من {total} - {text}".format(
        step=step, total=CV_STEPS_TOTAL, text=text
    )


def is_skip(text):
    return text.strip().lower() in SKIP_TOKENS


async def apply_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    record_user(update.effective_user)
    context.user_data.clear()
    if not visible_jobs():
        await update.message.reply_text(NO_JOBS_TEXT)
        return ConversationHandler.END
    text, markup = build_jobs_page(1)
    await update.message.reply_text(text, reply_markup=markup)
    return ConversationHandler.END


async def legacy_company_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    company = get_company(query.data.split(":", 1)[1])
    company_jobs = get_company_jobs(company["company_id"]) if company else []
    if not company_jobs:
        await query.edit_message_text(NO_JOBS_TEXT)
        return ConversationHandler.END
    keyboard = [
        [
            InlineKeyboardButton(
                job["title"][:40],
                callback_data="applyjob:" + str(job["job_id"]),
            )
        ]
        for job in company_jobs[:8]
    ]
    await query.edit_message_text(
        "شركة {name} - اختر الوظيفة:".format(
            name=company_display(company) if company else "-"
        ),
        reply_markup=InlineKeyboardMarkup(keyboard),
    )
    return ConversationHandler.END


async def apply_job_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    job = resolve_job_for_apply(query.data.split(":", 1)[1])
    if not job or job.get("active", "1") != "1":
        await query.edit_message_text("الوظيفة مسكّرة، اكتب /jobs تشوف المفتوحة.")
        return ConversationHandler.END
    record_user(update.effective_user)
    context.user_data.clear()
    company = get_company(job["company_id"])
    saved = latest_saved_application(update.effective_user.id)
    if saved and (saved.get("cv_file") or saved.get("phone")):
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "تقديم سريع بسيرتك ✓",
                        callback_data="quick:" + str(job["job_id"]),
                    )
                ],
                [
                    InlineKeyboardButton(
                        "استمارة جديدة",
                        callback_data="applyfull:" + str(job["job_id"]),
                    )
                ],
            ]
        )
        await query.edit_message_text(
            "عندك سيرة محفوظة باسم: {name}\n"
            "تبغى تقديم سريع على: {title}؟".format(
                name=saved.get("full_name", "-"), title=job["title"]
            ),
            reply_markup=keyboard,
        )
        return ConversationHandler.END
    return await _start_full_apply(query, context, job, company)


async def apply_full_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    job = resolve_job_for_apply(query.data.split(":", 1)[1])
    if not job or job.get("active", "1") != "1":
        await query.edit_message_text("الوظيفة مسكّرة، اكتب /jobs تشوف المفتوحة.")
        return ConversationHandler.END
    record_user(update.effective_user)
    context.user_data.clear()
    company = get_company(job["company_id"])
    return await _start_full_apply(query, context, job, company)


async def _start_full_apply(query, context, job, company):
    context.user_data["job_id"] = str(job["job_id"])
    context.user_data["company_id"] = str(job["company_id"])
    context.user_data["job"] = job["title"]
    context.user_data["company"] = company_display(company) if company else ""
    context.user_data["apply_email"] = job.get("apply_email", "")
    context.user_data["feed_url"] = job.get("feed_url", "")
    await query.edit_message_text(
        cv_step_prompt(1, "ابعثلي اسمك الكامل:")
        + "\n(التقديم على: {title} - {company})".format(
            title=job["title"], company=company_display(company) if company else "-"
        )
    )
    return CV_NAME


async def quick_apply_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    job = resolve_job_for_apply(query.data.split(":", 1)[1])
    if not job or job.get("active", "1") != "1":
        await query.edit_message_text("الوظيفة مسكّرة، اكتب /jobs تشوف المفتوحة.")
        return ConversationHandler.END
    saved = latest_saved_application(user.id)
    if not saved:
        await query.edit_message_text(
            "ما لقينا سيرة محفوظة - اكتب /apply عبي الاستمارة أول مرة."
        )
        return ConversationHandler.END
    company = get_company(job["company_id"])
    record = build_quick_record(saved, job, company)
    try:
        await finalize_application(record, context.application, query.message)
    except Exception:
        logger.exception("quick apply failed")
        await query.message.reply_text(
            "صار خلل بالتقديم السريع - جرب /apply عادي."
        )
        return ConversationHandler.END
    try:
        await query.edit_message_text(
            "انرسل تقديمك السريع لـ {title} ✓".format(title=job["title"])
        )
    except Exception:
        pass
    return ConversationHandler.END


async def finalize_application(record, application, reply_message):
    pdf_path = CVS_DIR / safe_cv_filename(record["full_name"], datetime.now())
    record["cv_file"] = pdf_path.name
    try:
        build_cv_pdf(record, pdf_path)
    except Exception:
        logger.warning("CV PDF build failed", exc_info=True)
        await reply_message.reply_text(
            "صار خلل ويا تجهيز الـ PDF، بس طلبك انحفظ - جرب /apply مرة ثانية."
        )
        return False
    save_application(record)
    summary = build_application_summary(record)
    job = get_job(record.get("job_id")) if record.get("job_id") else None
    apply_email = (
        (record.get("apply_email") or "").strip()
        or ((job or {}).get("apply_email") or "").strip()
    ).lower()
    email_sent = False
    if apply_email:
        email_sent = await asyncio.to_thread(
            send_application_email, apply_email, record, summary, pdf_path
        )
        summary += "\nالإرسال التلقائي للشركة ({email}): {state}".format(
            email=apply_email, state="تم ✓" if email_sent else "فشل - يتطلب ارسال يدوي"
        )
    company = get_company(record["company_id"]) if record["company_id"] else None
    delivered = False
    if company:
        delivered = await notify_company_owner(
            application,
            company,
            summary,
            pdf_path=pdf_path,
            reply_markup=build_decision_keyboard(record),
        )
    if not delivered:
        await notify_admins(application, summary, pdf_path=pdf_path)
    await notify_whatsapp(
        "طلب جديد: {name} على {job} - {company}".format(
            name=record.get("full_name", "-"),
            job=record.get("job", "-"),
            company=record.get("company", "-"),
        )
    )
    if apply_email and email_sent:
        delivery_line = (
            "وتوصل لشركة الفرصة بالإيميل: {email} ✓".format(email=apply_email)
        )
    elif apply_email:
        delivery_line = (
            "انحفظ طلبك ووصل للإدارة — راح يزوجه لشركة الفرصة يدوياً "
            "(تعذر الإرسال بالإيميل تلقائياً)."
        )
    else:
        delivery_line = "ووصلت للشركة: {company} - {job}".format(
            company=record["company"] or "-", job=record["job"] or "-"
        )
    caption = (
        "وصلنا طلبك يا {name}! سيرتك الذاتية PDF مرفقة هنا.\n"
        "{delivery}\n\n"
        "تتبع حالة طلبك: /mystatus\n"
        "تبي تفيد صاحبك يلقى شغل؟ ادعوهة برابطك: /ref"
    ).format(
        name=record["full_name"],
        delivery=delivery_line,
    )
    try:
        with pdf_path.open("rb") as handle:
            await reply_message.reply_document(
                document=handle,
                filename=pdf_path.name,
                caption=caption,
            )
    except Exception:
        logger.warning("CV PDF to applicant failed", exc_info=True)
        await reply_message.reply_text(caption)
    return True


async def cv_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if len(name) < 3 or len(name) > 80:
        await update.message.reply_text(
            "اسمك لازم من 3 لـ 80 حرف، اعدي ابعته:"
        )
        return CV_NAME
    context.user_data["full_name"] = name
    await update.message.reply_text(
        cv_step_prompt(2, "ابعث رقم موبايلك (8 ارقام فما فوق)\nمثال: 07712345678")
    )
    return CV_PHONE


async def cv_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    if not PHONE_PATTERN.match(phone):
        await update.message.reply_text(
            "الرقم غلط - ابعت رقما يبدأ برقم أو + وبقيّة الأرقام بس:"
        )
        return CV_PHONE
    context.user_data["phone"] = phone
    await update.message.reply_text(
        cv_step_prompt(3, "ابعث CV (ملف PDF او وورد او صورة)")
        + "\nاو اكتب /form وعبي الاستمارة معي ونطلعها PDF."
    )
    return CV_FILE


async def cv_form_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        cv_step_prompt(4, "ابعث الإيميل (إذا مو موجود اكتب /skip)")
    )
    return CV_EMAIL


async def cv_file_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ابعث ملف CV (PDF او وورد او صورة) او اكتب /form عشان الاستمارة."
    )
    return CV_FILE


async def cv_receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    document = update.message.document
    if document.file_size and document.file_size > 10 * 1024 * 1024:
        await update.message.reply_text("الملف كبير - الحد 10 ميغا، صغّره وابعثه.")
        return CV_FILE
    return await store_uploaded_cv(
        update, context, document.file_id, document.file_name or "cv.pdf"
    )


async def cv_receive_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo = max(update.message.photo, key=lambda item: item.file_size or 0)
    if photo.file_size and photo.file_size > 10 * 1024 * 1024:
        await update.message.reply_text("الصورة كبيرة - الحد 10 ميغا، صغّرها.")
        return CV_FILE
    return await store_uploaded_cv(update, context, photo.file_id, "cv_photo.jpg")


async def store_uploaded_cv(update, context, file_id, original_name):
    user = update.effective_user
    data = context.user_data
    safe = re.sub(r"[^\w.]+", "_", original_name, flags=re.UNICODE).strip("_")[:60]
    if not safe:
        safe = "cv.pdf"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = CVS_DIR / "CV_{stamp}_{name}".format(stamp=stamp, name=safe)
    CVS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        remote = await context.bot.get_file(file_id)
        await remote.download(custom_path=str(dest))
    except Exception:
        logger.warning("CV upload download failed", exc_info=True)
        await update.message.reply_text(
            "ما گدرنا نحمّل الملف، جرب ابعته مرة ثانية."
        )
        return CV_FILE
    record = {
        "timestamp": now_iso(),
        "user_id": user.id,
        "username": user.username or "",
        "full_name": data.get("full_name", ""),
        "phone": data.get("phone", ""),
        "email": data.get("email", ""),
        "city": data.get("city", ""),
        "education": data.get("education", ""),
        "work_experience": data.get("work_experience", ""),
        "skills": data.get("skills", ""),
        "languages": data.get("languages", ""),
        "summary": data.get("summary", ""),
        "company_id": data.get("company_id", ""),
        "company": data.get("company", ""),
        "job_id": data.get("job_id", ""),
        "job": data.get("job", ""),
        "cv_file": dest.name,
    }
    save_application(record)
    summary = build_application_summary(record)
    company = get_company(record["company_id"]) if record["company_id"] else None
    delivered = False
    if company:
        delivered = await notify_company_owner(
            context.application,
            company,
            summary,
            pdf_path=dest,
            reply_markup=build_decision_keyboard(record),
        )
    if not delivered:
        await notify_admins(context.application, summary, pdf_path=dest)
    context.user_data.clear()
    await update.message.reply_text(
        "وصلنا ملف الـ CV يا {name}! وصل للشركة {company} - {job}. بالتوفيق!".format(
            name=record["full_name"] or "صديق",
            company=record["company"] or "-",
            job=record["job"] or "-",
        )
    )
    if record.get("skills") or record.get("city"):
        try:
            _cv_header, cv_picks = collect_recommendations(
                user.id, limit=3, exclude_seen=True
            )
            if cv_picks:
                cv_text, cv_markup = render_recommendations(
                    "أقرب الوظائف لسيرتك الذاتية:", cv_picks
                )
                await update.message.reply_text(cv_text, reply_markup=cv_markup)
        except Exception:
            logger.warning("CV match reply failed for %s", user.id, exc_info=True)
    return ConversationHandler.END


async def cv_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if is_skip(text):
        context.user_data["email"] = ""
    elif not EMAIL_PATTERN.match(text) or len(text) > 100:
        await update.message.reply_text("اكتب إيميلك عدل، أو اكتب /skip:")
        return CV_EMAIL
    else:
        context.user_data["email"] = text
    await update.message.reply_text(
        cv_step_prompt(5, "ابعث مدينتك / محافظتك (إذا مو متأكد اكتب /skip)")
    )
    return CV_CITY


async def cv_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if is_skip(text):
        context.user_data["city"] = ""
    elif len(text) < 2 or len(text) > 60:
        await update.message.reply_text("المدينة لازم من 2 لـ 60 حرف، اعديها أو /skip:")
        return CV_CITY
    else:
        context.user_data["city"] = text
    await update.message.reply_text(
        cv_step_prompt(6, "شهادتك - التخصص وسنة التخرج (اكتب /skip إذا تخطيت)\nمثال: هندسة حاسوب - جامعة بغداد 2022")
    )
    return CV_EDU


async def cv_edu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if is_skip(text):
        context.user_data["education"] = ""
    elif len(text) < 2 or len(text) > 300:
        await update.message.reply_text(
            "الشهادة لازم من 2 لـ 300 حرف، اعديها أو اكتب /skip:"
        )
        return CV_EDU
    else:
        context.user_data["education"] = text
    await update.message.reply_text(
        cv_step_prompt(7, "خبرتك - وين اشتغلت وشنو كانت مسؤولياتك (اكتب /skip إذا تخطيت)")
    )
    return CV_WORK


async def cv_work(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if is_skip(text):
        context.user_data["work_experience"] = ""
    elif len(text) < 2 or len(text) > 600:
        await update.message.reply_text(
            "الخبرة لازم من 2 لـ 600 حرف، اعديها أو اكتب /skip:"
        )
        return CV_WORK
    else:
        context.user_data["work_experience"] = text
    await update.message.reply_text(
        cv_step_prompt(8, "مهاراتك - افصل بينها بفاصلة (اكتب /skip إذا تخطيت)\nمثال: Photoshop, مونتاج")
    )
    return CV_SKILLS


async def cv_skills(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if is_skip(text):
        context.user_data["skills"] = ""
    elif len(text) < 2 or len(text) > 400:
        await update.message.reply_text(
            "المهارات لازم من 2 لـ 400 حرف، اعديها أو اكتب /skip:"
        )
        return CV_SKILLS
    else:
        context.user_data["skills"] = text
    await update.message.reply_text(
        cv_step_prompt(9, "اللغات (اختياري)\nمثال: العربية - لغة ام، الانجليزية - متوسط")
    )
    return CV_LANGS


async def cv_langs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if is_skip(text):
        context.user_data["languages"] = ""
    elif len(text) < 2 or len(text) > 200:
        await update.message.reply_text("اللغات لازم من 2 لـ 200 حرف، اعديها أو /skip:")
        return CV_LANGS
    else:
        context.user_data["languages"] = text
    await update.message.reply_text(
        cv_step_prompt(10, "نبذة قصيرة عنك (إذا مو تبي اكتب /skip)")
    )
    return CV_SUMMARY


async def cv_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if is_skip(text):
        context.user_data["summary"] = ""
    elif len(text) < 2 or len(text) > 400:
        await update.message.reply_text("النبذة لازم من 2 لـ 400 حرف، اعديها أو /skip:")
        return CV_SUMMARY
    else:
        context.user_data["summary"] = text

    data = context.user_data
    preview_lines = [
        "شوف، هذي سيرتك الذاتية:",
        "",
        "الاسم: " + data.get("full_name", ""),
        "الهاتف: " + data.get("phone", ""),
    ]
    if data.get("email"):
        preview_lines.append("الإيميل: " + data["email"])
    if data.get("city"):
        preview_lines.append("المدينة: " + data["city"])
    preview_lines.append("المؤهل: " + data.get("education", ""))
    preview_lines.append("الخبرة: " + data.get("work_experience", ""))
    preview_lines.append("المهارات: " + data.get("skills", ""))
    if data.get("languages"):
        preview_lines.append("اللغات: " + data["languages"])
    if data.get("summary"):
        preview_lines.append("النبذة: " + data["summary"])
    preview_lines.append("")
    preview_lines.append(
        "الوظيفة: {job} - {company}".format(
            job=data.get("job", ""), company=data.get("company", "")
        )
    )
    preview_lines.append("")
    preview_lines.append("اضغط ارسل الطلب وراح اوليدها سيرة ذاتية PDF، توصلك إنت وتوصل للشركة.")
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("ارسل الطلب", callback_data="cv:send")],
            [InlineKeyboardButton("الغاء", callback_data="cv:cancel")],
        ]
    )
    await update.message.reply_text(
        "\n".join(preview_lines), reply_markup=keyboard
    )
    return CV_CONFIRM


def safe_cv_filename(full_name, when):
    safe = re.sub(r"[^\w]+", "_", full_name, flags=re.UNICODE).strip("_")[:40]
    return "CV_{name}_{stamp}.pdf".format(
        name=safe or "cv", stamp=when.strftime("%Y%m%d_%H%M%S")
    )


async def cv_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    data = dict(context.user_data)
    record = {
        "timestamp": now_iso(),
        "user_id": user.id,
        "username": user.username or "",
        "full_name": data.get("full_name", ""),
        "phone": data.get("phone", ""),
        "email": data.get("email", ""),
        "city": data.get("city", ""),
        "education": data.get("education", ""),
        "work_experience": data.get("work_experience", ""),
        "skills": data.get("skills", ""),
        "languages": data.get("languages", ""),
        "summary": data.get("summary", ""),
        "company_id": data.get("company_id", ""),
        "company": data.get("company", ""),
        "job_id": data.get("job_id", ""),
        "job": data.get("job", ""),
        "apply_email": data.get("apply_email", ""),
        "feed_url": data.get("feed_url", ""),
    }
    await finalize_application(record, context.application, query.message)
    context.user_data.clear()
    return ConversationHandler.END


async def cv_cancel_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.edit_message_text("انلغي التقديم - إذا تبي تعيده، اكتب /apply")
    return ConversationHandler.END


async def cv_confirm_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "اضغط زر (ارسل الطلب) او (الغاء) عشان تكمل."
    )
    return CV_CONFIRM


async def cancel_apply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "انلغي التقديم - إذا تبي تعيده، اكتب /apply"
    )
    return ConversationHandler.END


def company_panel_text(company):
    jobs_count = len(get_company_jobs(company["company_id"]))
    applicants_count = count_company_applicants(company["company_id"])
    if str(company.get("verified", "")).strip() == "1":
        verified_line = "موثّقة ✓ ({email})".format(
            email=company.get("verified_email") or "-"
        )
    else:
        verified_line = "غير موثّقة - اكتب /verify"
    return (
        "شركة {name} (#{cid})\n"
        "التوثيق: {verified}\n"
        "الوظائف: {jobs} | المتقدمون: {applicants}\n\n"
        "انشر ونشوف الطلبات:\n"
        "/postjob - كابشن الوظيفة\n"
        "/myjobs - وظائفي | /myapplicants - الطلبات\n"
        "/mystats - احصائياتك | /export - تنزيل CSV\n"
        "/verify - توثيق الشركة (علامة ✓ للمتقدمين)\n"
        "/closejob رقم | /openjob رقم | /deletejob رقم\n"
        "/help - كل اوامر البوت"
    ).format(
        name=company_display(company),
        cid=company["company_id"],
        verified=verified_line,
        jobs=jobs_count,
        applicants=applicants_count,
    )


async def company_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    record_user(update.effective_user)
    company = company_by_owner(update.effective_user.id)
    if company:
        await update.message.reply_text(company_panel_text(company))
        return ConversationHandler.END
    await update.message.reply_text(COMPANY_REG_PROMPT)
    return CO_REG_NAME


async def company_receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    if len(name) < 2 or len(name) > 60:
        await update.message.reply_text("اسم الشركة لازم من 2 لـ 60 حرف، اعديه:")
        return CO_REG_NAME
    company = register_company(update.effective_user, name)
    await update.message.reply_text(
        "تسجلت {name}!\n\n{panel}".format(
            name=name, panel=company_panel_text(company)
        )
    )
    return ConversationHandler.END


async def verify_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    record_user(update.effective_user)
    company = company_by_owner(update.effective_user.id)
    if not company:
        await update.message.reply_text(
            NEED_COMPANY_TEXT + " وبعدها ارجع /verify."
        )
        return ConversationHandler.END
    if str(company.get("verified", "")).strip() == "1":
        await update.message.reply_text(
            "شركتك موثّقة من قبل ✓ ({email})\n\n{panel}".format(
                email=company.get("verified_email") or "-",
                panel=company_panel_text(company),
            )
        )
        return ConversationHandler.END
    await update.message.reply_text(
        "توثيق الشركة: ابعث الإيميل الرسمي لشركتك (دومين باسمكم، مو gmail/yahoo).\n"
        "بنرسله كود تأكيد من 6 ارقام - أول ما تستلمونه اكتبوه هنا."
    )
    return VERIFY_EMAIL


async def verify_receive_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    email = update.message.text.strip().lower()
    if "@" not in email:
        await update.message.reply_text(
            "يظهر انت بصفحة توثيق الشركات مو تقديم وظائف.\n"
            "للتقديم على وظيفة: /apply\n"
            "لشوف الوظائف: /jobs\n"
            "واتوثيق يرجع بي: /verify"
        )
        context.user_data.clear()
        return ConversationHandler.END
    if len(email) > 120 or not EMAIL_FULL_RE.match(email):
        await update.message.reply_text(
            "اكتب الإيميل عدل - بهالشكل: name@company.com\n"
            "إذا مو قصدك التوثيق، اكتب /cancel عشان تخرج."
        )
        return VERIFY_EMAIL
    domain = email.split("@", 1)[1]
    if any(domain.startswith(prefix) for prefix in FREE_MAIL_PREFIXES):
        await update.message.reply_text(
            "محتاجين دومين رسمي بشركتكم (مو إيميل شخصي) حتى ينفع التوثيق - اعديه:"
        )
        return VERIFY_EMAIL
    code = "{:06d}".format(secrets.randbelow(1000000))
    context.user_data["verify_email"] = email
    context.user_data["verify_code"] = code
    context.user_data["verify_ts"] = datetime.now().timestamp()
    context.user_data["verify_attempts"] = 0
    try:
        await asyncio.to_thread(send_verify_email, email, code)
    except Exception:
        logger.warning("verify code email failed", exc_info=True)
        await update.message.reply_text(
            "ما كدرنا نرسل الكود لـ {email} - تأكد منه وجرّب /verify مرة ثانية.".format(
                email=email
            )
        )
        return ConversationHandler.END
    await update.message.reply_text(
        "انرسل كود من 6 ارقام لـ {email}.\nادخله هنا (صالح 10 دقايق):".format(
            email=email
        )
    )
    return VERIFY_CODE


async def verify_receive_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    attempts = int(context.user_data.get("verify_attempts", 0)) + 1
    context.user_data["verify_attempts"] = attempts
    expected = str(context.user_data.get("verify_code", ""))
    elapsed = datetime.now().timestamp() - float(context.user_data.get("verify_ts", 0))
    if not expected or elapsed > VERIFY_CODE_TTL:
        await update.message.reply_text(
            "انتهت صلاحية الكود - اكتب /verify من جديد."
        )
        context.user_data.clear()
        return ConversationHandler.END
    if text != expected:
        remaining = VERIFY_MAX_ATTEMPTS - attempts
        if remaining <= 0:
            await update.message.reply_text(
                "كثروا المحاولات - ابدأ من جديد بـ /verify."
            )
            context.user_data.clear()
            return ConversationHandler.END
        await update.message.reply_text(
            "الكود غلط - جرب مرة ثانية ({n} محاولات متبقية):".format(n=remaining)
        )
        return VERIFY_CODE
    company = company_by_owner(update.effective_user.id)
    if not company:
        await update.message.reply_text(NEED_COMPANY_TEXT)
        context.user_data.clear()
        return ConversationHandler.END
    email = context.user_data.get("verify_email", "")
    set_verified_email(company["company_id"], email)
    context.user_data.clear()
    company = company_by_owner(update.effective_user.id)
    await update.message.reply_text(
        "تم التوثيق ✓\nالحين اسم شركتك يظهر لكل المتقدمين بعلامة ✓.\n\n{panel}".format(
            panel=company_panel_text(company)
        )
    )
    try:
        await notify_admins(
            context.application,
            "توثيق جديد: {name} <{email}>".format(
                name=company["name"], email=email
            ),
        )
    except Exception:
        logger.warning("verify admin notify failed", exc_info=True)
    return ConversationHandler.END


async def post_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    company = company_by_owner(update.effective_user.id)
    if not company:
        await update.message.reply_text(NEED_COMPANY_TEXT)
        return ConversationHandler.END
    await update.message.reply_text(
        "ابعت كابشن الوظيفة كامل (المسمى، الشروط، الوصف) - "
        "يوصل للكل مع زر التقديم:"
    )
    return POST_CAPTION


async def post_receive_caption(update: Update, context: ContextTypes.DEFAULT_TYPE):
    caption = update.message.text.strip()
    if len(caption) < 10 or len(caption) > 3000:
        await update.message.reply_text(
            "الكابشن لازم من 10 لـ 3000 حرف، اعديه:"
        )
        return POST_CAPTION
    company = company_by_owner(update.effective_user.id)
    if not company:
        await update.message.reply_text(NEED_COMPANY_TEXT)
        return ConversationHandler.END
    violations = screen_job_caption(caption)
    if violations:
        await update.message.reply_text(
            "ما نشرنا الإعلان - لقينا فيه:\n- "
            + "\n- ".join(violations)
            + "\n\nاكتب الإعلان الحقيقي بمعلومات دقيقة بس: المسمى الوظيفي، الشروط، "
            "والطريقة للتواصل او التقديم - وبعدها ابعته مرة ثانية."
        )
        try:
            await notify_admins(
                context.application,
                "حجب نشر تلقائي - {company}:\n- {violations}\n\nالنص: {caption}".format(
                    company=company["name"],
                    violations="\n- ".join(violations),
                    caption=caption[:400],
                ),
            )
        except Exception:
            logger.warning("screen notify failed", exc_info=True)
        return POST_CAPTION
    job = save_job_post(company["company_id"], caption)
    text = "وظيفة جديدة من {company}:\n\n{caption}".format(
        company=company_display(company), caption=caption
    )
    if job.get("specialty"):
        text += "\n\nالاختصاص: {specialty}".format(specialty=job["specialty"])
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("التقديم على الوظيفة", callback_data="applyjob:" + str(job["job_id"]))]]
    )
    await update.message.reply_text(
        "جاري نشر الوظيفة للمهتمين بالاختصاص، بوصلك الخبر اذا خلص."
    )
    targets, registered, mode = specialty_broadcast_targets(job.get("specialty"))

    async def _publish():
        sent, failed, total = await broadcast_text(
            context.bot, text, reply_markup=keyboard, targets=targets
        )
        try:
            if mode == "all":
                scope = "المسجلون: {registered}".format(registered=registered)
            else:
                scope = (
                    "المهتمون بـ {mode}: {registered} من أصل {all_count} مسجل"
                ).format(mode=mode, registered=total, all_count=registered)
            await update.message.reply_text(
                "انشرت! وصلت لـ {sent} مستخدم ({failed} فشل)\n{scope}".format(
                    sent=sent, failed=failed, scope=scope
                )
            )
        except Exception:
            logger.warning("Broadcast report to company failed", exc_info=True)
        await notify_admins(
            context.application,
            "نشر وظيفة جديدة: {title}\nالشركة: {company} (وصول: {sent}/{total} مستهدف)".format(
                title=job["title"], company=company["name"], sent=sent, total=total
            ),
        )
        try:
            channel_text = (
                "وظيفة جديدة ببغداد والعراق:\n\n"
                "{title}\n{company} | {city}\n"
                "الراتب: {salary}\n\n"
                "قدّم من البوت: t.me/{bot}"
            ).format(
                title=job["title"],
                company=company["name"],
                city=job.get("city") or "-",
                salary=job.get("salary") or "بالاتفاق",
                bot=BOT_USERNAME,
            )
            await post_to_channels(context.bot, channel_text)
        except Exception:
            logger.warning("Channel publish failed", exc_info=True)
        await asyncio.to_thread(publish_site_safe)

    context.application.create_task(_publish())
    return ConversationHandler.END


async def curate_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await refuse_non_admin(update)
        return ConversationHandler.END
    record_user(update.effective_user)
    context.user_data.clear()
    await update.message.reply_text(
        "نشر وظيفة مختارة (من بحثك - بدون تسجيل شركة).\n\n"
        "ابعت كابشن الوظيفة كامل (المسمى، الشروط، المدينة...)"
        " — ينعرض بـ /jobs و /findjob مع زر التقديم.\n\n"
        "بعدها بسألك عن إيميل التقديم بالشركة حتى ندز السير تلقائياً."
    )
    return CURATE_CAPTION


async def curate_receive_caption(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await refuse_non_admin(update)
        return ConversationHandler.END
    caption = (update.message.text or "").strip()
    if len(caption) < 10 or len(caption) > 3000:
        await update.message.reply_text(
            "الكابشن لازم من 10 لـ 3000 حرف، اعديه:"
        )
        return CURATE_CAPTION
    context.user_data["curate_caption"] = caption
    await update.message.reply_text(
        "تمام. وين نرسل طلبات المتقدمين للشركة؟\n\n"
        "ابعت إيميل التقديم الرسمي (مثل careers@company.com)\n"
        "او اكتب «بدون» إذا حاب الطلبات توصلك بس وتزوجها بنفسك."
    )
    return CURATE_CHANNEL


async def curate_receive_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await refuse_non_admin(update)
        return ConversationHandler.END
    raw = (update.message.text or "").strip()
    caption = (context.user_data.get("curate_caption") or "").strip()
    if len(caption) < 10:
        await update.message.reply_text(
            "انقطعت الجلسة - اكتب /curatejob من جديد."
        )
        return ConversationHandler.END
    apply_email = ""
    if raw.casefold() not in ("بدون", "no", "-", "لا"):
        match = EMAIL_EXTRACT_RE.search(raw)
        if not match:
            await update.message.reply_text(
                "ما لقينا إيميل صحيح بـ «{raw}».\n"
                "ابعت الإيميل (مثل careers@company.com) او اكتب «بدون».".format(
                    raw=raw[:60]
                )
            )
            return CURATE_CHANNEL
        apply_email = match.group(0).lower()
    ensure_curated_company()
    job = save_job_post(CURATED_COMPANY_ID, caption, apply_email=apply_email)
    context.user_data.pop("curate_caption", None)
    specialty = job.get("specialty") or "غير مصنف"
    channel_line = (
        "الإرسال التلقائي: {email} ✓".format(email=apply_email)
        if apply_email
        else "الإرسال: يدوي (يوصلك انت)"
    )
    text = (
        "وظيفة مختارة من {studio}:\n\n{caption}\n\n"
        "الاختصاص: {specialty}"
    ).format(studio=STUDIO_NAME, caption=caption, specialty=specialty)
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton("التقديم على الوظيفة", callback_data="applyjob:" + str(job["job_id"]))]]
    )
    await update.message.reply_text(
        "جاري نشر الوظيفة للمهتمين بالاختصاص، بوصلك الخبر اذا خلص."
    )
    targets, registered, mode = specialty_broadcast_targets(specialty)

    async def _publish_curated():
        sent, failed, total = await broadcast_text(
            context.bot, text, reply_markup=keyboard, targets=targets
        )
        try:
            if mode == "all":
                scope = "المسجلون: {registered}".format(registered=registered)
            else:
                scope = (
                    "المهتمون بـ {mode}: {registered} من أصل {all_count} مسجل"
                    "\n(الباقي يشوفونها بـ /jobs)"
                ).format(mode=mode, registered=total, all_count=registered)
            await update.message.reply_text(
                "انشرت! وصلت لـ {sent} مستخدم ({failed} فشل)\n"
                "{scope}\n"
                "رقم الوظيفة: #{jid} | الاختصاص: {specialty}\n"
                "{channel}\n"
                "ادارتها: /curatejobs".format(
                    sent=sent, failed=failed, scope=scope,
                    jid=job["job_id"], specialty=specialty,
                    channel=channel_line,
                )
            )
        except Exception:
            logger.warning("Broadcast report to admin failed", exc_info=True)

    context.application.create_task(_publish_curated())
    return ConversationHandler.END


async def curate_jobs_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await refuse_non_admin(update)
        return
    jobs = get_company_jobs(CURATED_COMPANY_ID, active_only=False)
    if not jobs:
        await update.message.reply_text(
            "ماكو وظائف مختارة بعد - انشر وحدة: /curatejob"
        )
        return
    apps = load_applications()
    lines = []
    for index, job in enumerate(reversed(jobs), start=1):
        applicants = sum(
            1 for row in apps if str(row.get("job_id", "")) == str(job["job_id"])
        )
        status = "مفتوحة" if job.get("active", "1") == "1" else "مغلقة"
        specialty = job.get("specialty") or "غير مصنف"
        channel = job.get("apply_email") or "يدوي"
        lines.append(
            "{index}) {title} (#{jid})\n   {applicants} متقدم | {status} | {specialty}"
            " | الإرسال: {channel} | {date}".format(
                index=index,
                jid=job["job_id"],
                title=job["title"],
                applicants=applicants,
                status=status,
                specialty=specialty,
                channel=channel,
                date=(job.get("created_at") or "").split("T")[0],
            )
        )
    await update.message.reply_text(
        "الوظائف المختارة ({n}):\n\n{lines}\n\n"
        "اغلق: /closejob رقم | تفتح: /openjob رقم | تحذف: /deletejob رقم\n"
        "انشر وحدة جديدة: /curatejob".format(n=len(jobs), lines="\n".join(lines))
    )


async def my_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    company = company_by_owner(update.effective_user.id)
    if not company:
        await update.message.reply_text(NEED_COMPANY_TEXT)
        return
    company_jobs = get_company_jobs(company["company_id"], active_only=False)
    if not company_jobs:
        await update.message.reply_text(
            "ماكو وظائف منشورة - نشر وظيفة: /postjob"
        )
        return
    lines = []
    apps = load_applications()
    for index, job in enumerate(reversed(company_jobs), start=1):
        applicants = sum(
            1
            for row in apps
            if str(row.get("job_id", "")) == str(job["job_id"])
        )
        status = "مفتوحة" if job.get("active", "1") == "1" else "مغلقة"
        lines.append(
            "{index}) {title} (#{jid})\n   {applicants} متقدم | {status} | {date}".format(
                index=index,
                jid=job["job_id"],
                title=job["title"],
                applicants=applicants,
                status=status,
                date=(job.get("created_at") or "").split("T")[0],
            )
        )
    await update.message.reply_text(
        "وظائف {company}:\n\n{lines}\n\n"
        "اغلق وظيفة: /closejob رقم | تعيد فتحها: /openjob رقم".format(
            company=company["name"], lines="\n".join(lines)
        )
    )


async def _set_job_state(update: Update, context: ContextTypes.DEFAULT_TYPE, state):
    user_id = update.effective_user.id
    admin = is_admin(user_id)
    company = company_by_owner(user_id)
    if not company and not admin:
        await update.message.reply_text(NEED_COMPANY_TEXT)
        return
    cmd = "closejob" if state == "0" else "openjob"
    if not context.args:
        await update.message.reply_text(
            "الاستخدام: /{cmd} <رقم الوظيفة>\nالرقم تشوفه بـ /myjobs (مثل: /{cmd} 3)".format(
                cmd=cmd
            )
        )
        return
    job = get_job(context.args[0].lstrip("#"))
    if not job:
        await update.message.reply_text(
            "ماكو وظيفة بهالرقم - الرقم شوفه بـ /myjobs"
        )
        return
    if not admin and str(job.get("company_id", "")) != str(company["company_id"]):
        await update.message.reply_text(
            "ماكو وظيفة بهالرقم ويا شركتك - الرقم شوفه بـ /myjobs"
        )
        return
    if job.get("active", "1") == state:
        already = "مغلقة أصلاً" if state == "0" else "مفتوحة أصلاً"
        await update.message.reply_text(
            "هاي الوظيفة «{title}» {already}.".format(
                title=job["title"], already=already
            )
        )
        return
    set_job_active(job["job_id"], state)
    if state == "0":
        await update.message.reply_text(
            "انغلقت «{title}» - ما تقبل طلبات جديدة ولا تنعرض بـ /jobs.\n"
            "تعيدها: /openjob {jid}".format(title=job["title"], jid=job["job_id"])
        )
    else:
        await update.message.reply_text(
            "رجعت «{title}» مفتوحة وتنعرض للجميع بالضغط: /jobs".format(
                title=job["title"]
            )
        )


async def close_job(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _set_job_state(update, context, "0")


async def open_job(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _set_job_state(update, context, "1")


async def delete_job(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    admin = is_admin(user_id)
    company = company_by_owner(user_id)
    if not company and not admin:
        await update.message.reply_text(NEED_COMPANY_TEXT)
        return
    if not context.args or not context.args[0].lstrip("#").isdigit():
        await update.message.reply_text(
            "اكتب: /deletejob رقم\n(الأرقام تشوفها بـ /myjobs) - الحذف نهائي."
        )
        return
    job_id = context.args[0].lstrip("#")
    existing = get_job(job_id)
    if not existing:
        await update.message.reply_text("ما لقينا وظيفة بهالرقم.")
        return
    if not admin and str(existing.get("company_id", "")) != str(company["company_id"]):
        await update.message.reply_text("ما لقينا وظيفة بهالرقم تابعة لشركتك.")
        return
    storage.delete_rows("company_jobs", {"job_id": job_id})
    await update.message.reply_text(
        "انحذفت الوظيفة رقم {job} نهائياً.".format(job=job_id)
    )


async def decision_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = (query.data or "").split(":")
    if len(parts) != 4:
        await query.answer()
        return
    _, action, user_id, job_id = parts
    await query.answer()
    job = get_job(job_id)
    if not job:
        await query.message.reply_text("ماكو وظيفة بهالرقم (يمكن انحذفت).")
        return
    company = get_company(job["company_id"])
    pressed_by = update.effective_user.id
    owner_ok = company and str(company.get("owner_user_id", "")) == str(pressed_by)
    if not (owner_ok or is_admin(pressed_by)):
        await query.message.reply_text("هذا الإجراء يخص صاحب الوظيفة بس.")
        return
    record = find_application(user_id, job_id)
    if not record:
        await query.message.reply_text("ما لقينا طلب هالمتقدم على هالوظيفة.")
        return
    try:
        if action == "contact":
            set_application_status(user_id, job_id, "تواصل معك صاحب الوظيفة")
        elif action == "interview":
            set_application_status(user_id, job_id, "طلب مقابلة ✓")
    except Exception:
        logger.warning("app status update failed", exc_info=True)
    if action == "contact":
        username = record.get("username") or ""
        await query.message.reply_text(
            "بيانات المتقدم {name}:\n"
            "الهاتف: {phone}\n"
            "تيليجرام: {tg}".format(
                name=record.get("full_name", "-"),
                phone=record.get("phone", "-"),
                tg=("@" + username) if username else "بدون معرّف",
            )
        )
        return
    contact = (
        "@" + company["owner_username"]
        if company and company.get("owner_username")
        else CONTACT_PHONE
    )
    applicant_text = (
        "مبروك يا {name}! الشركة {company} شافت سيرتك لوظيفة {job} "
        "وتبيلك تكمل معاها خطوات المقابلة.\n\n"
        "تواصل معهم: {contact}\n"
        "واذا صار اي استفسار: {studio}"
    ).format(
        name=record.get("full_name", "صديقي"),
        company=company["name"] if company else "-",
        job=job["title"],
        contact=contact,
        studio=CONTACT_PHONE,
    )
    delivered = True
    try:
        await context.bot.send_message(chat_id=int(user_id), text=applicant_text)
    except Exception:
        logger.warning("Interview notice to %s failed", user_id, exc_info=True)
        delivered = False
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        logger.info("Decision keyboard removal failed", exc_info=True)
    if delivered:
        await query.message.reply_text(
            "انرسل طلب المقابلة لـ {name} ✓".format(
                name=record.get("full_name", "")
            )
        )
    else:
        await query.message.reply_text(
            "ما گدرنا نوصل للمتقدم (user_id: {uid}) - لازم يبدأ البوت بـ /start.".format(
                uid=user_id
            )
        )


async def my_applicants(update: Update, context: ContextTypes.DEFAULT_TYPE):
    company = company_by_owner(update.effective_user.id)
    if not company:
        await update.message.reply_text(NEED_COMPANY_TEXT)
        return
    rows = [
        row
        for row in load_applications()
        if str(row.get("company_id", "")) == str(company["company_id"])
    ]
    if not rows:
        await update.message.reply_text("ماكو متقدمين على وظائفك بعد.")
        return
    shown = rows[-10:]
    header = "متقدمو {company}: {total} (اعرض {shown})\n\n".format(
        company=company["name"], total=len(rows), shown=len(shown)
    )
    blocks = [
        build_application_row(number, row)
        for number, row in enumerate(reversed(shown), start=1)
    ]
    for message in pack_blocks(header, blocks):
        await update.message.reply_text(message)


OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:1.5b")
OLLAMA_TIMEOUT = float(os.environ.get("OLLAMA_TIMEOUT", "8"))

SMART_PROMPT = (
    "أنت مساعد بوت تيليجرام «{studio}» للتوظيف في العراق. "
    "أجب بالعربية العراقية البسيطة، أقصى 3 أسطر، بدون تطويل. "
    "أوامر البوت: /apply تقديم طلب، /jobs الوظائف، /findjob كلمة للبحث، "
    "/match ترشيح وظائف، /prefs حفظ تفضيلاتك، /company للشركات، /contact للتواصل. "
    "إذا سأل عن وظيفة أو دوام، وصّله /findjob او /jobs. "
    "لا تخترع وظائف - القائمة الحالية:\n{jobs}"
)

GREETING_WORDS = {
    "هلا", "اهلا", "أهلا", "مرحبا", "سلام", "السلام", "شلونك", "شلونكم",
    "كيفك", "هاي", "hi", "hello", "hey", "salam",
}
THANKS_WORDS = {"شكرا", "شكراً", "شكر", "مشكور", "يسلمو", "ثانكس", "thanks", "thx"}
STOPWORDS = {
    "وين", "ليش", "شلون", "متى", "عندي", "ابي", "أبي", "بدي", "هذا", "هذي",
    "اللي", "او", "أو", "منو", "شنو", "هاذا", "the", "and", "for", "you",
    "mom", "with", "from", "هسه", "بعد", "بس", "الحين", "عندكم", "عندنا",
    "على", "الى", "الي", "عند", "ابحث", "الان", "اليوم", "ابغى", "بغي",
}


def extract_job_query(text):
    words = re.findall(r"[؀-ۿa-zA-Z]{3,}", text)
    cleaned = []
    for word in words:
        word = word.strip("؟،.!:؛")
        if len(word) >= 3 and word.casefold() not in STOPWORDS:
            cleaned.append(word.casefold())
    return cleaned


def inline_job_matches(words):
    active = get_all_active_jobs()
    for word in words:
        hits = [
            job
            for job in active
            if word in (job.get("title", "") + " " + job.get("caption", "")).casefold()
        ]
        if hits:
            return word, hits
    return None, []


def jobs_brief_lines(limit=5):
    jobs_list = get_all_active_jobs()[:limit]
    if not jobs_list:
        return "ماكو وظائف شاغلة حاليا"
    return "\n".join(
        "- {title} ({company})".format(
            title=j.get("title", "-"), company=j.get("company", "-")
        )
        for j in jobs_list
    )


async def ollama_reply(text, user_text):
    prompt = SMART_PROMPT.format(studio=STUDIO_NAME, jobs=jobs_brief_lines())
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": "السياق:\n" + prompt + "\n\nالرسالة: " + user_text + "\nالرد:",
        "stream": False,
        "options": {"temperature": 0.5, "num_predict": 160},
    }
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(OLLAMA_TIMEOUT, connect=2.0)
        ) as client:
            response = await client.post(OLLAMA_URL, json=payload)
            response.raise_for_status()
            reply = (response.json().get("response") or "").strip()
    except Exception:
        logger.info("ollama unavailable, falling back", exc_info=True)
        return None
    if not reply or len(reply) > 1200:
        return None
    return reply


async def group_auto_reply(
    update: Update, context: ContextTypes.DEFAULT_TYPE, text: str
):
    lowered = text.casefold()
    if not any(k in lowered for k in GROUP_JOB_KEYWORDS):
        return
    if BOT_USERNAME in text or BOT_LINK in text:
        return
    chat = update.effective_chat
    if chat is None:
        return
    now = datetime.now().timestamp()
    stamps = context.bot_data.setdefault("group_auto_reply_ts", {})
    if now - float(stamps.get(str(chat.id), 0)) < GROUP_REPLY_COOLDOWN:
        return
    if len(stamps) > 500:
        stamps.clear()
    stamps[str(chat.id)] = now
    await update.message.reply_text(
        "الوظائف الشاغرة كلها بمكان واحد - بوت ملهم مجاناً:\n"
        "سيرة ذاتية PDF، تنبيهات تلائمك لجوالك، والشركات تنشر برسالة وحدة.",
        reply_to_message_id=update.message.message_id,
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "كل الوظائف بالبوت", url=BOT_LINK + "?start=jobs"
                    ),
                    InlineKeyboardButton(
                        "انشر وظيفة مجاناً", url=BOT_LINK + "?start=company"
                    ),
                ]
            ]
        ),
    )


async def handle_free_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user is None:
        logger.info("free message without user (channel/anonymous), ignored")
        return
    if user.is_bot:
        return
    record_user(user)
    text = update.message.text
    log_free_message(user, text)
    chat = update.effective_chat
    if chat and chat.type in ("group", "supergroup"):
        await group_auto_reply(update, context, text)
        return
    if context.user_data.pop("pending_company_name", False):
        await company_receive_name(update, context)
        return
    if context.user_data.pop("pending_wa_phone", False):
        await _handle_wa_phone_reply(update, context)
        return
    lowered = text.lower().strip()

    first_word = lowered.split()[0] if lowered.split() else ""
    if first_word in GREETING_WORDS or lowered in GREETING_WORDS:
        await update.message.reply_text(
            "هلا وغلا! أنا بوت {studio} للتوظيف بالعراق.\n"
            "ابدأ: /jobs للوظائف | /apply للتقديم | /contact للتواصل".format(
                studio=STUDIO_NAME
            )
        )
        return
    if any(w in text for w in THANKS_WORDS):
        await update.message.reply_text(
            "العفو! فرحانين باهتمامك بـ " + STUDIO_NAME
        )
        return
    if (
        "تقديم" in text
        or "اقدم" in text
        or "أقدم" in text
        or "apply" in lowered
        or "cv" in lowered
        or "سيف" in text
        or "سيرة" in text
    ):
        await update.message.reply_text(
            "إذا تبي تتقدم، اكتب /apply - ابعث ملف CV او عبي الاستمارة وتصير PDF."
        )
        return
    if "شرك" in text:
        await update.message.reply_text(
            "للشركات: اكتب /company لتسجيل شركتك، وبعدها /postjob لنشر وظيفة."
        )
        return
    if "تواصل" in text or "contact" in lowered:
        await contact(update, context)
        return
    if "راتب" in text or "مرتب" in text:
        await update.message.reply_text(
            "الرواتب تحدد حسب الوظيفة والخبرة. ارسل سيرتك عبر /apply"
        )
        return
    if "تابع" in text or "تنبيه" in text or "follow" in lowered:
        await update.message.reply_text(
            "اكتب /follow عشان يوصلك 3 وظائف جديدة كل يوم الساعة 11،\n"
            "ولا /prefs لمدينتك ومهاراتك عشان /match يرشحلك الأنسب."
        )
        return

    query_words = extract_job_query(text)
    if query_words:
        word, matches = inline_job_matches(query_words)
        if matches:
            lines = [
                "- #{jid} {title} ({company})".format(
                    jid=j.get("job_id", "?"),
                    title=j.get("title", "-"),
                    company=j.get("company", "-"),
                )
                for j in matches[:4]
            ]
            reply = (
                "لقيت {count} وظيفة تطابق «{word}»:\n{lines}\n\n"
                "اكتب /jobs للقائمة كاملة او /apply للتقديم."
            ).format(count=len(matches), word=word, lines="\n".join(lines))
            await update.message.reply_text(reply)
            return
        if re.search(r"وظا|وظيف|شغل|فرصة|توظيف|job|hiring", lowered):
            await jobs(update, context)
            return

    smart = await ollama_reply(text, text)
    if smart:
        await update.message.reply_text(smart)
        return
    await update.message.reply_text(
        "يسلمو على رسالتك! فريقنا يراجعها.\n"
        "للتقديم الرسمي اكتب /apply\n"
        "للوظائف المتاحة اكتب /jobs\n"
        "للشركات اكتب /company\n"
        "للتواصل اكتب /contact"
    )


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Unhandled error", exc_info=context.error)


async def refuse_non_admin(update: Update):
    await update.message.reply_text("هذا الأمر للإدارة بس.")


def pack_blocks(header, blocks, max_chars=3900):
    messages = []
    current = header
    for block in blocks:
        if len(current) + len(block) + 2 > max_chars:
            messages.append(current)
            current = block + "\n\n"
        else:
            current = current + block + "\n\n"
    if current.strip():
        messages.append(current)
    return messages


async def admin_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await refuse_non_admin(update)
        return
    await update.message.reply_text(
        "أوامر الإدارة:\n"
        "/list [عدد] - اخر الطلبات (الافتراضي 5، الاقصى 50)\n"
        "/find [كلمة] - بحث بالاسم او الهاتف او الوظيفة\n"
        "/reply [معرّف] [نص] - رد على متقدم\n"
        "/stats - عدد الطلبات لكل وظيفة\n"
        "/companies - الشركات المسجلة\n"
        "/curatejob - نشر وظيفة مختارة (من بحثك، بدون تسجيل شركة + ايميل للإرسال التلقائي)\n"
        "/curatejobs - ادارة الوظائف المختارة\n"
        "/specialties - تصفح الاختصاصات\n"
        "/export - ارسال ملف الطلبات CSV\n"
        "/backup - ارسال نسخة من كل ملفات البيانات\n"
        "/broadcast [نص] - ارسال رسالة لكل من تواصل مع البوت\n"
        "/wagroups - مجموعات الواتساب المرئية للبوت\n"
        "/waallow [رقم|الكل] - تفعيل البث لمجموعة (من /wagroups)\n"
        "/wadeny [رقم|الكل] - ايقاف البث لمجموعة\n"
        "/watest [رقم] - رسالة تجريبية لمجموعة مفعّلة\n"
        "/wacap - حدود وحالة بث الواتساب"
    )


async def wa_groups_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await refuse_non_admin(update)
        return
    try:
        groups = await wa_broadcast.fetch_bridge_groups()
    except Exception:
        logger.warning("WA groups fetch failed", exc_info=True)
        await update.message.reply_text(
            "ما كدرت أجيب المجموعات - تأكد البريدج شغّال: /health"
        )
        return
    if not groups:
        await update.message.reply_text("البوت مو بآي مجموعة واتساب.")
        return
    known = {str(g.get("jid", "")): g for g in wa_broadcast.load_groups()}
    lines = []
    keyboard = []
    for i, group in enumerate(groups, start=1):
        jid = str(group.get("id", ""))
        name = (group.get("subject") or "بدون اسم")[:40]
        size = group.get("size") or "?"
        stored = known.get(jid)
        flag = "✅" if stored and str(stored.get("allowed", "")) == "1" else "—"
        lines.append("{i}) {flag} {name} ({size} عضو)".format(i=i, flag=flag, name=name, size=size))
        keyboard.append(
            [
                InlineKeyboardButton(
                    "✅ فعّل " + str(i), callback_data="waon:" + jid
                ),
                InlineKeyboardButton(
                    "⛔ أوقف " + str(i), callback_data="waoff:" + jid
                ),
            ]
        )
    context.bot_data["wa_group_ids"] = [str(g.get("id", "")) for g in groups]
    text = "مجموعات الواتساب ({n}):\n\n".format(n=len(groups)) + "\n".join(lines)
    text += "\n\nأوامر يدوية: /waallow رقم | /wadeny رقم | /watest رقم"
    await update.message.reply_text(
        text, reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None
    )


async def wa_allow_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await refuse_non_admin(update)
        return
    args = context.args or []
    if not args:
        await update.message.reply_text("اكتب: /waallow 1 او /waallow الكل")
        return
    try:
        groups = await wa_broadcast.fetch_bridge_groups()
    except Exception:
        await update.message.reply_text("ما كدرت أجيب المجموعات.")
        return
    known = context.bot_data.get("wa_group_ids") or [str(g.get("id", "")) for g in groups]
    by_id = {str(g.get("id", "")): g for g in groups}

    def target_jid(token):
        if token.isdigit():
            index = int(token) - 1
            if 0 <= index < len(known):
                return known[index]
            return None
        if token in by_id:
            return token
        return None

    tokens = [a for a in args if a.strip()]
    if any(t.strip().lower() in ("الكل", "all") for t in tokens):
        tokens = known
    done = 0
    for token in tokens:
        jid = target_jid(str(token).strip())
        if not jid:
            continue
        group = by_id.get(jid, {})
        wa_broadcast.set_group_allowed(
            jid, True, name=group.get("subject", ""), size=group.get("size", "")
        )
        done += 1
    await update.message.reply_text(
        "فعّلت {n} مجموعة للبث الآلي. الحد: {cap}/يوم، {max}/تشغيل.".format(
            n=done,
            cap=wa_broadcast.MAX_SENDS_PER_DAY,
            max=wa_broadcast.MAX_GROUPS_PER_RUN,
        )
    )


async def wa_deny_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await refuse_non_admin(update)
        return
    args = context.args or []
    if not args:
        await update.message.reply_text("اكتب: /wadeny 1 او /wadeny الكل")
        return
    groups = wa_broadcast.load_groups()
    known = context.bot_data.get("wa_group_ids") or [str(g.get("jid", "")) for g in groups]
    jids = []
    if any(a.strip().lower() in ("الكل", "all") for a in args):
        jids = [str(g.get("jid", "")) for g in groups]
    else:
        for token in args:
            token = token.strip()
            if token.isdigit():
                index = int(token) - 1
                if 0 <= index < len(known):
                    jids.append(known[index])
            elif token.endswith("@g.us"):
                jids.append(token)
    done = 0
    for jid in jids:
        wa_broadcast.set_group_allowed(jid, False)
        done += 1
    await update.message.reply_text("أوقفت {n} مجموعة عن البث.".format(n=done))


async def wa_test_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await refuse_non_admin(update)
        return
    allowed = wa_broadcast.allowed_groups()
    if not allowed:
        await update.message.reply_text("ماكو مجموعة مفعّلة. استخدم /waallow اولاً.")
        return
    jid = None
    args = context.args or []
    known = context.bot_data.get("wa_group_ids") or []
    if args and args[0].isdigit() and known:
        index = int(args[0]) - 1
        if 0 <= index < len(known):
            jid = known[index]
    if not jid:
        jid = str(allowed[0].get("jid", ""))
    text = (
        "تجربة من ملهم ✓\n"
        "بوت توظيف مجاني للعراق — الوظائف تنزل هنا كل 6 ساعات.\n"
        "سجّل وتابع: {bot}"
    ).format(bot=BOT_LINK)
    try:
        await wa_broadcast.send_group_message(jid, text)
    except Exception:
        logger.warning("WA test send failed", exc_info=True)
        await update.message.reply_text("فشل الإرسال للمجموعة المختارة.")
        return
    await update.message.reply_text("انرسلت رسالة التجربة للمجموعة المحددة ✓")


async def wa_cap_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await refuse_non_admin(update)
        return
    allowed = wa_broadcast.allowed_groups()
    await update.message.reply_text(
        "بث الواتساب:\n"
        "مجموعات مفعّلة: {allowed}\n"
        "مُرسل اليوم: {today}/{cap}\n"
        "حد التشغيل: {max} مجموعة\n"
        "تأخير بين الرسائل: {dmin}-{dmax} ثانية\n\n"
        "الرسائل تتغيّر نصها تلقائياً والترتيب عشوائي — تقليل خطر الحظر.".format(
            allowed=len(allowed),
            today=wa_broadcast.sends_today(),
            cap=wa_broadcast.MAX_SENDS_PER_DAY,
            max=wa_broadcast.MAX_GROUPS_PER_RUN,
            dmin=wa_broadcast.DELAY_MIN,
            dmax=wa_broadcast.DELAY_MAX,
        )
    )


async def wa_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(update.effective_user.id):
        return
    data = query.data or ""
    if data.startswith("waon:"):
        jid = data[5:]
        wa_broadcast.set_group_allowed(jid, True)
        await query.message.reply_text("فعّلت البث لهذي المجموعة ✓")
    elif data.startswith("waoff:"):
        jid = data[6:]
        wa_broadcast.set_group_allowed(jid, False)
        await query.message.reply_text("أوقفت البث لهذي المجموعة ✓")


async def list_applicants(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await refuse_non_admin(update)
        return
    limit = 5
    if context.args and context.args[0].isdigit():
        limit = max(1, min(int(context.args[0]), 50))
    all_rows = load_applications()
    rows = all_rows[-limit:]
    if not rows:
        await update.message.reply_text("ماكو طلبات مسجلة بعد.")
        return
    header = "اخر {shown} طلبات (المجموع: {total}):\n\n".format(
        shown=len(rows), total=len(all_rows)
    )
    blocks = [
        build_application_row(number, row)
        for number, row in enumerate(reversed(rows), start=1)
    ]
    for message in pack_blocks(header, blocks):
        await update.message.reply_text(message)


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await refuse_non_admin(update)
        return
    counter = count_applications_by_job()
    total = sum(counter.values())
    users_count = len(known_broadcast_targets())
    companies_count = len(get_companies())
    jobs_count = len(load_csv_rows(COMPANY_JOBS_CSV))
    if total == 0:
        await update.message.reply_text(
            "ماكو طلبات بعد.\n"
            "الشركات: {companies} | الوظائف: {jobs}\n"
            "المستخدمون المسجلون: {users}".format(
                companies=companies_count, jobs=jobs_count, users=users_count
            )
        )
        return
    ranked = sorted(counter.items(), key=lambda item: -item[1])
    job_lines = "\n".join(
        "{job}: {count}".format(job=job, count=count) for job, count in ranked
    )
    await update.message.reply_text(
        "الطلبات الكلية: {total}\n"
        "الشركات: {companies} | الوظائف المنشورة: {jobs}\n"
        "المستخدمون المسجلون: {users}\n\n"
        "حسب الوظيفة:\n{lines}".format(
            total=total,
            companies=companies_count,
            jobs=jobs_count,
            users=users_count,
            lines=job_lines,
        )
    )


async def ref_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    record_user(user)
    code = referral_code(user.id)
    link = "https://t.me/{bot}?start={code}".format(
        bot=BOT_USERNAME, code=code
    )
    count = referral_count(user.id)
    share_url = "https://t.me/share/url?url={link}&text={text}".format(
        quote(link),
        quote("تعال سجّل ببوت توظيف العراق وسوي سيرة ذاتية PDF: "),
    )
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("شارك الرابط", url=share_url),
                InlineKeyboardButton("انسخ الرابط", url=link),
            ]
        ]
    )
    await update.message.reply_text(
        "رابط الدعوة الخاص فيك:\n{link}\n\n"
        "دعواتك: {count}\n"
        "المستوى: {tier}\n\n"
        "لكل دعوة يسجّل صاحبك ويقدم على وظيفة، تزيد حصيلتك - "
        "عند 3 دعوات: شركات تشوف سيرتك عليها \"موصى به ✓\"، وعند 10: أولوية عرض بكل نشرة.".format(
            link=link, count=count, tier=referral_tier(count)
        ),
        reply_markup=keyboard,
    )


def _short_tier(count):
    if count >= 10:
        return "ذهبي"
    if count >= 3:
        return "فضي"
    return "ابدائي"


async def share_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    record_user(user)
    link = "https://t.me/{bot}?start={code}".format(
        bot=BOT_USERNAME, code=referral_code(user.id)
    )
    text = (
        "ملهم - بوت توظيف العراق (مجاني):\n"
        "- وظائف محدّثة كل 6 ساعات بكل المحافظات\n"
        "- سيرة ذاتية PDF بثواني والتقديم بضغطة\n"
        "- تنبيه يومي بالوظائف المناسبة لمهنتك\n\n"
        "انضم عبر هالرابط واكتب /follow: {link}"
    ).format(link=link)
    encoded = quote(text)
    share_url = "https://t.me/share/url?url={url}&text={msg}".format(
        url=quote(BOT_LINK), msg=encoded
    )
    wa_url = "https://wa.me/?text={msg}".format(msg=encoded)
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("شارك برسالة تيليجرام", url=share_url)],
            [
                InlineKeyboardButton("شارك بالواتساب", url=wa_url),
                InlineKeyboardButton("انسخ رابطك", url=link),
            ],
        ]
    )
    await update.message.reply_text(
        "رسالة جاهزة تنشرها بأصحابك أو بقروباتك أو بحالة الواتساب:\n\n" + text,
        reply_markup=keyboard,
    )


async def top_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    invited_by = {}
    for row in storage.read_table("referrals"):
        ref = str(row.get("ref", ""))
        uid = str(row.get("user_id", ""))
        if ref.startswith("r") and uid:
            invited_by.setdefault(ref, set()).add(uid)
    users = {str(row.get("user_id", "")): row for row in storage.read_table("users")}
    board = []
    for ref, invited in invited_by.items():
        uid = ref[1:]
        unique = {i for i in invited if i != uid}
        if not unique:
            continue
        profile = users.get(uid, {})
        name = (
            (profile.get("first_name") or "").strip()
            or (profile.get("username") or "").strip()
            or "مستخدم"
        )
        board.append((len(unique), name, uid))
    if not board:
        await update.message.reply_text(
            "ما اكو دعوات بعد - انشر رابطك بقروباتك وكن أول واحد باللوحة.\n"
            "/share رسالة جاهزة للنشر، و /ref يعطيك رابطك."
        )
        return
    board.sort(key=lambda row: (-row[0], row[1]))
    lines = ["أعلى الدعاة بملهم:", ""]
    for rank, (count, name, _) in enumerate(board[:10], start=1):
        lines.append(
            "{rank}. {name} - {count} دعوة ({tier})".format(
                rank=rank, name=name, count=count, tier=_short_tier(count)
            )
        )
    me = str(update.effective_user.id)
    my_rank = next(
        (i for i, row in enumerate(board, start=1) if str(row[2]) == me), None
    )
    lines.append("")
    if my_rank:
        my_count = referral_count(update.effective_user.id)
        lines.append(
            "انت: #{rank} - {count} دعوة ({tier})".format(
                rank=my_rank, count=my_count, tier=_short_tier(my_count)
            )
        )
    else:
        lines.append("انت بره القائمة - اعمل دعوة وحدة وادخلها: /ref")
    await update.message.reply_text("\n".join(lines))


STATUS_LABELS = {
    "": "قيد المراجعة",
    "تواصل معك صاحب الوظيفة": "تواصل معك صاحب الوظيفة ✓",
    "طلب مقابلة ✓": "طلب مقابلة ✓",
}


async def mystatus_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    rows = [
        row
        for row in load_applications()
        if str(row.get("user_id", "")) == str(user_id)
    ]
    if not rows:
        await update.message.reply_text(
            "ما عندك طلبات بعد - اكتب /apply عشان تتقدم، "
            "ولا /jobs تشوف الوظائف المفتوحة."
        )
        return
    rows.sort(key=lambda row: row.get("timestamp") or "", reverse=True)
    lines = ["طلباتك ({n}):".format(n=len(rows)), ""]
    for row in rows[:12]:
        status = get_application_status(user_id, row.get("job_id", ""))
        date = (row.get("timestamp") or "")[:10]
        lines.append(
            "• {job}\n  {company} | {date}\n  الحالة: {status}".format(
                job=(row.get("job") or "بدون وظيفة")[:50],
                company=row.get("company") or "-",
                date=date or "-",
                status=STATUS_LABELS.get(status, status or "قيد المراجعة"),
            )
        )
    if len(rows) > 12:
        lines.append("\n(+{more} طلب ثاني)".format(more=len(rows) - 12))
    await update.message.reply_text("\n".join(lines))


async def mystats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    company = company_by_owner(update.effective_user.id)
    if not company:
        await update.message.reply_text(
            "ما تسجلت شركة بعد - اكتب /company اول عشان تنشئها."
        )
        return
    cid = company["company_id"]
    jobs = get_company_jobs(cid)
    active_jobs = [j for j in jobs if str(j.get("active", "1")) == "1"]
    applications = [
        a for a in load_applications() if str(a.get("company_id", "")) == str(cid)
    ]
    since = (datetime.now() - timedelta(days=7)).date()
    week_count = 0
    for app in applications:
        raw = (app.get("timestamp", "") or "")[:10]
        try:
            if datetime.strptime(raw, "%Y-%m-%d").date() >= since:
                week_count += 1
        except ValueError:
            continue
    per_job = {}
    for app in applications:
        job_title = app.get("job", "بدون وظيفة")
        per_job[job_title] = per_job.get(job_title, 0) + 1
    ranked = sorted(per_job.items(), key=lambda item: -item[1])
    ranked_text = "\n".join(
        "{job}: {count}".format(job=job, count=count) for job, count in ranked[:8]
    ) or "ماكو طلبات بعد"
    avg = round(len(applications) / len(jobs), 1) if jobs else 0
    await update.message.reply_text(
        "إحصائيات شركة {name}:\n\n"
        "الوظائف: {total} ({active} شغالة)\n"
        "المتقدمون: {apps} | آخر 7 أيام: {week}\n"
        "معدل المتقدمين لكل وظيفة: {avg}\n\n"
        "الأكثر تلقائياً:\n{ranked}".format(
            name=company_display(company),
            total=len(jobs),
            active=len(active_jobs),
            apps=len(applications),
            week=week_count,
            avg=avg,
            ranked=ranked_text,
        )
    )


async def companies_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await refuse_non_admin(update)
        return
    companies = get_companies()
    if not companies:
        await update.message.reply_text("ماكو شركات مسجلة بعد.")
        return
    lines = []
    for index, company in enumerate(companies, start=1):
        lines.append(
            "{index}) {name} (#{cid})\n"
            "   المالك: {owner} | وظائف: {jobs} | متقدمون: {applicants}".format(
                index=index,
                name=company_display(company),
                cid=company["company_id"],
                owner=company.get("owner_username") or company.get("owner_user_id"),
                jobs=len(get_company_jobs(company["company_id"], active_only=False)),
                applicants=count_company_applicants(company["company_id"]),
            )
        )
    await update.message.reply_text(
        "الشركات المسجلة: {count}\n\n{lines}".format(
            count=len(companies), lines="\n".join(lines)
        )
    )


async def export_applicants(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_admin(user_id):
        if storage.table_count("applicants") == 0:
            await update.message.reply_text("ماكو ملف طلبات بعد.")
            return
        await update.message.reply_document(
            document=storage.to_csv_bytes("applicants", headers=CSV_HEADERS),
            filename="applicants.csv",
            caption="ملف الطلبات - " + now_iso(),
        )
        return
    company = company_by_owner(user_id)
    if not company:
        await refuse_non_admin(update)
        return
    rows = [
        row
        for row in load_applications()
        if str(row.get("company_id", "")) == str(company["company_id"])
    ]
    if not rows:
        await update.message.reply_text("ماكو متقدمين على وظائفك بعد.")
        return
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer, fieldnames=CSV_HEADERS, extrasaction="ignore", restval=""
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key, "") for key in CSV_HEADERS})
    safe_name = re.sub(r"[^\w]+", "_", company["name"], flags=re.UNICODE).strip("_")
    await update.message.reply_document(
        document=buffer.getvalue().encode("utf-8-sig"),
        filename="applicants_{name}.csv".format(name=safe_name or "company"),
        caption="متقدمو {name}: {count} طلب - {stamp}".format(
            name=company["name"], count=len(rows), stamp=now_iso()
        ),
    )


async def broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await refuse_non_admin(update)
        return
    text = " ".join(context.args).strip()
    if not text:
        await update.message.reply_text(
            "الاستخدام: /broadcast نص الرسالة\nمثال: /broadcast فتح باب التقديم للشهر الحالي"
        )
        return
    if not known_broadcast_targets():
        await update.message.reply_text("ماكو مستخدمين مسجلين بعد.")
        return
    admin_id = update.effective_user.id
    await update.message.reply_text("جاري ارسال رسالتك لجميع المستخدمين...")

    async def _admin_broadcast():
        sent, failed, total = await broadcast_text(context.bot, text)
        try:
            await context.application.bot.send_message(
                chat_id=admin_id,
                text="خلص الإرسال: {sent} وصل | {failed} فشل | {total} مسجل".format(
                    sent=sent, failed=failed, total=total
                ),
            )
        except Exception:
            logger.warning("Admin broadcast report failed", exc_info=True)

    context.application.create_task(_admin_broadcast())


async def find_applicants(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await refuse_non_admin(update)
        return
    query = " ".join(context.args).strip()
    if not query:
        await update.message.reply_text(
            "الاستخدام: /find كلمة البحث\n"
            "مثال: /find 07712345678 او /find احمد"
        )
        return
    matches = search_applications(query)
    if not matches:
        await update.message.reply_text("ماكو نتائج مطابقة لـ: " + query)
        return
    shown = matches[-10:]
    header = "نتائج البحث عن {query}: {total} طلب (اعرض {shown})\n\n".format(
        query=query, total=len(matches), shown=len(shown)
    )
    blocks = [
        build_application_row(number, row)
        for number, row in enumerate(reversed(shown), start=1)
    ]
    for message in pack_blocks(header, blocks):
        await update.message.reply_text(message)


async def reply_to_applicant(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await refuse_non_admin(update)
        return
    args = context.args
    if len(args) < 2 or not args[0].lstrip("-").isdigit():
        await update.message.reply_text(
            "الاستخدام: /reply معرّف_المستخدم نص الرسالة\n"
            "مثال: /reply 123456789 مرحبا، طلبك وصل ومراجعناه"
        )
        return
    target_id = int(args[0])
    text = " ".join(args[1:]).strip()
    try:
        await context.bot.send_message(chat_id=target_id, text=text)
    except Exception:
        logger.warning("Reply to %s failed", target_id, exc_info=True)
        await update.message.reply_text(
            "ما گدرنا نوصل للمستخدم {target} - لازم يبدأ البوت بـ /start أول.".format(
                target=target_id
            )
        )
        return
    await update.message.reply_text("انرسل الرد لـ {target}".format(target=target_id))


def existing_backup_files():
    return [path for path in BACKUP_FILES if path.exists()]


async def send_backup_files(bot, chat_id):
    stamp = now_iso()
    for path in existing_backup_files():
        with path.open("rb") as handle:
            await bot.send_document(
                chat_id=chat_id,
                document=handle,
                filename=path.name,
                caption="{name} - نسخة {stamp}".format(name=path.name, stamp=stamp),
            )


async def backup_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await refuse_non_admin(update)
        return
    if not existing_backup_files():
        await update.message.reply_text("ماكو ملفات بيانات للنسخ بعد.")
        return
    try:
        await send_backup_files(context.bot, update.effective_chat.id)
    except Exception:
        logger.warning("Backup to %s failed", update.effective_chat.id, exc_info=True)
        await update.message.reply_text("صار خلل وقت ارسال النسخة، جرب مرة ثانية.")
        return
    await update.message.reply_text(
        "انرسل: {files}".format(
            files=", ".join(path.name for path in existing_backup_files())
        )
    )


async def daily_backup_job(context: ContextTypes.DEFAULT_TYPE):
    admin_ids = get_admin_chat_ids()
    files = existing_backup_files()
    if not admin_ids or not files:
        logger.info("Daily backup skipped: admins=%s files=%s", len(admin_ids), len(files))
        return
    for admin_id in admin_ids:
        try:
            await send_backup_files(context.bot, admin_id)
        except Exception:
            logger.warning("Daily backup to %s failed", admin_id, exc_info=True)


async def daily_digest_job(context: ContextTypes.DEFAULT_TYPE):
    cutoff = (
        datetime.now(ZoneInfo("Asia/Baghdad")) - timedelta(hours=24)
    ).isoformat()
    fresh = [
        row
        for row in load_applications()
        if (row.get("timestamp") or "") >= cutoff
    ]
    if not fresh:
        logger.info("Daily digest: no new applications in last 24h")
        return
    companies_hit = 0
    for company in get_companies():
        rows = [
            row
            for row in fresh
            if str(row.get("company_id", "")) == str(company.get("company_id", ""))
        ]
        if not rows:
            continue
        owner_raw = str(company.get("owner_user_id") or "").strip()
        if not owner_raw.lstrip("-").isdigit():
            continue
        companies_hit += 1
        lines = []
        for row in rows[:5]:
            lines.append(
                "- {name} | {job}".format(
                    name=row.get("full_name", "-"), job=row.get("job", "-")
                )
            )
        if len(rows) > 5:
            lines.append("- وايد غيرهم: {more}".format(more=len(rows) - 5))
        text = (
            "ملخص اليوم - {company}:\n"
            "{count} طلب جديد خلال آخر 24 ساعة:\n\n{lines}"
        ).format(
            company=company["name"], count=len(rows), lines="\n".join(lines)
        )
        try:
            await context.bot.send_message(
                chat_id=int(owner_raw), text=text
            )
        except Exception:
            logger.warning(
                "Daily digest to company %s failed",
                company.get("company_id"),
                exc_info=True,
            )
    admin_text = (
        "ملخص 24 ساعة - {studio}:\n"
        "{total} طلب جديد | {companies} شركة استلمت | {jobs} وظيفة مفتوحة"
    ).format(
        studio=STUDIO_NAME,
        total=len(fresh),
        companies=companies_hit,
        jobs=len(get_all_active_jobs()),
    )
    for admin_id in get_admin_chat_ids():
        try:
            await context.bot.send_message(chat_id=admin_id, text=admin_text)
        except Exception:
            logger.warning("Daily digest to admin %s failed", admin_id, exc_info=True)


async def tg_channel_post_job(context: ContextTypes.DEFAULT_TYPE):
    if not get_telegram_channels():
        return
    text = channel_digest.build_digest()
    if not text:
        logger.info("TG channel digest: nothing to post")
        return
    try:
        sent = await post_to_channels(context.bot, text)
        logger.info("TG channel digest posted to %s channel(s)", sent)
    except Exception:
        logger.warning("TG channel digest failed", exc_info=True)


async def wa_status_job(context: ContextTypes.DEFAULT_TYPE):
    load_env_file()
    enabled = (os.environ.get("WA_STATUS_ENABLED", "1") or "1").strip().lower()
    if enabled not in ("1", "true", "yes", "on"):
        logger.info("WA status disabled by config")
        return
    bridge = (
        os.environ.get("WHATSAPP_BRIDGE_URL", "") or "http://127.0.0.1:8788/send"
    ).strip()
    base = bridge[:-5] if bridge.endswith("/send") else bridge
    text = channel_digest.build_status_text()
    if not text:
        logger.info("WA status: nothing to post")
        return
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(base.rstrip("/") + "/status", json={"text": text})
        if resp.status_code == 200:
            logger.info("WA status posted (%s chars)", len(text))
        else:
            logger.warning(
                "WA status failed: %s %s", resp.status_code, resp.text[:200]
            )
    except Exception:
        logger.warning("WA status job error", exc_info=True)


def job_age_days(created_at):
    raw = (created_at or "").strip()
    if not raw:
        return None
    try:
        created = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if created.tzinfo is None:
        created = created.replace(tzinfo=ZoneInfo("Asia/Baghdad"))
    return (datetime.now(ZoneInfo("Asia/Baghdad")) - created).days


async def stale_job_reminder_job(context: ContextTypes.DEFAULT_TYPE):
    for company in get_companies():
        stale = []
        for job in get_company_jobs(company["company_id"]):
            if str(job.get("active", "1")) != "1":
                continue
            age = job_age_days(job.get("created_at", ""))
            if age is not None and age >= JOB_STALE_DAYS:
                stale.append((job, age))
        if not stale:
            continue
        lines = []
        for job, age in stale[:5]:
            lines.append(
                "#{jid} {title} (منذ {age} يوم)".format(
                    jid=job.get("job_id", "?"),
                    title=job.get("title", "بدون عنوان"),
                    age=age,
                )
            )
        text = (
            "تذكير - {company}:\n"
            "عندك {count} وظيفة مفتوحة من أكثر من {days} يوم:\n\n{lines}\n\n"
            "/closejob رقم - اقفلها إذا خلصت\n"
            "/mystats - احصائياتك الكاملة"
        ).format(
            company=company.get("name", "-"),
            count=len(stale),
            days=JOB_STALE_DAYS,
            lines="\n".join(lines),
        )
        owner_raw = str(company.get("owner_user_id") or "").strip()
        if not owner_raw.lstrip("-").isdigit():
            continue
        try:
            await context.bot.send_message(
                chat_id=int(owner_raw), text=text
            )
        except Exception:
            logger.warning(
                "Stale job reminder to company %s failed",
                company.get("company_id"),
                exc_info=True,
            )


def schedule_jobs(application):
    job_queue = getattr(application, "job_queue", None)
    if job_queue is None:
        logger.info("JobQueue missing, daily backup is disabled")
        return
    wake_grace = {"misfire_grace_time": 6 * 3600, "coalesce": True}
    job_queue.run_daily(
        daily_backup_job, time=DAILY_BACKUP_TIME, job_kwargs=wake_grace
    )
    logger.info("Daily backup scheduled at %s", DAILY_BACKUP_TIME.isoformat())
    job_queue.run_daily(
        daily_digest_job, time=DAILY_DIGEST_TIME, job_kwargs=wake_grace
    )
    logger.info("Daily digest scheduled at %s", DAILY_DIGEST_TIME.isoformat())
    job_queue.run_daily(
        seeker_digest_job, time=SEEKER_DIGEST_TIME, job_kwargs=wake_grace
    )
    logger.info("Seeker digest scheduled at %s", SEEKER_DIGEST_TIME.isoformat())
    job_queue.run_daily(
        seeker_evening_job, time=SEEKER_EVENING_TIME, job_kwargs=wake_grace
    )
    logger.info("Seeker evening alert scheduled at %s", SEEKER_EVENING_TIME.isoformat())
    job_queue.run_daily(
        tg_channel_post_job, time=TG_CHANNEL_POST_TIME, job_kwargs=wake_grace
    )
    logger.info("TG channel digest scheduled at %s", TG_CHANNEL_POST_TIME.isoformat())
    job_queue.run_daily(wa_status_job, time=WA_STATUS_TIME, job_kwargs=wake_grace)
    logger.info("WA status scheduled at %s", WA_STATUS_TIME.isoformat())
    job_queue.run_daily(
        stale_job_reminder_job, time=JOB_REMINDER_TIME, job_kwargs=wake_grace
    )
    logger.info("Stale job reminder scheduled at %s", JOB_REMINDER_TIME.isoformat())
    job_queue.run_daily(
        company_nudge_job, time=COMPANY_NUDGE_TIME, job_kwargs=wake_grace
    )
    logger.info("Company nudge scheduled at %s", COMPANY_NUDGE_TIME.isoformat())
    job_queue.run_repeating(
        feed_ingest_job,
        first=timedelta(seconds=30),
        interval=timedelta(hours=6),
        job_kwargs=wake_grace,
    )
    logger.info("Feed ingest scheduled every 6 hours (first run in 30s)")


def build_application():
    return (
        ApplicationBuilder()
        .token(get_bot_token())
        .persistence(PicklePersistence(filepath=str(PERSISTENCE_FILE)))
        .build()
    )


CONVERSATION_FALLBACKS = [
    CommandHandler("cancel", cancel_apply),
    CommandHandler("mycv", mycv_start),
    CommandHandler("start", start),
    CommandHandler("help", help_command),
    CommandHandler("jobs", jobs),
    CommandHandler("contact", contact),
    CommandHandler("admin", admin_help),
    CommandHandler("list", list_applicants),
    CommandHandler("stats", stats_command),
    CommandHandler("mystats", mystats_command),
    CommandHandler("mystatus", mystatus_command),
    CommandHandler("ref", ref_command),
    CommandHandler("share", share_command),
    CommandHandler("top", top_command),
    CommandHandler("export", export_applicants),
    CommandHandler("broadcast", broadcast_message),
    CommandHandler("find", find_applicants),
    CommandHandler("reply", reply_to_applicant),
    CommandHandler("backup", backup_data),
    CommandHandler("companies", companies_list),
    CommandHandler("myjobs", my_jobs),
    CommandHandler("myapplicants", my_applicants),
    CommandHandler("closejob", close_job),
    CommandHandler("openjob", open_job),
    CommandHandler("deletejob", delete_job),
    CommandHandler("findjob", find_jobs),
    CommandHandler("curatejob", curate_entry),
    CommandHandler("curatejobs", curate_jobs_list),
    CommandHandler("specialties", specialties_cmd),
    CommandHandler("wagroups", wa_groups_cmd),
    CommandHandler("waallow", wa_allow_cmd),
    CommandHandler("wadeny", wa_deny_cmd),
    CommandHandler("watest", wa_test_cmd),
    CommandHandler("wacap", wa_cap_cmd),
]


def register_handlers(application):
    apply_conversation = ConversationHandler(
        entry_points=[
            CommandHandler("apply", apply_start),
            CallbackQueryHandler(apply_job_entry, pattern=r"^applyjob:.+"),
            CallbackQueryHandler(apply_full_entry, pattern=r"^(applyfull:|job:).+"),
            CallbackQueryHandler(quick_apply_entry, pattern=r"^quick:.+"),
            CallbackQueryHandler(legacy_company_entry, pattern=r"^co:\d+$"),
        ],
        states={
            CV_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, cv_name)
            ],
            CV_PHONE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, cv_phone)
            ],
            CV_FILE: [
                MessageHandler(filters.Document.ALL, cv_receive_file),
                MessageHandler(filters.PHOTO, cv_receive_photo),
                CommandHandler("form", cv_form_command),
                MessageHandler(filters.TEXT & ~filters.COMMAND, cv_file_text),
            ],
            CV_EMAIL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, cv_email)
            ],
            CV_CITY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, cv_city)
            ],
            CV_EDU: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, cv_edu)
            ],
            CV_WORK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, cv_work)
            ],
            CV_SKILLS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, cv_skills)
            ],
            CV_LANGS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, cv_langs)
            ],
            CV_SUMMARY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, cv_summary)
            ],
            CV_CONFIRM: [
                CallbackQueryHandler(cv_send, pattern=r"^cv:send$"),
                CallbackQueryHandler(cv_cancel_button, pattern=r"^cv:cancel$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, cv_confirm_text),
            ],
        },
        fallbacks=CONVERSATION_FALLBACKS,
        allow_reentry=True,
        name="apply_cv",
        persistent=True,
    )

    company_conversation = ConversationHandler(
        entry_points=[CommandHandler("company", company_entry)],
        states={
            CO_REG_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, company_receive_name)
            ],
        },
        fallbacks=CONVERSATION_FALLBACKS,
        allow_reentry=True,
        name="company_reg",
        persistent=True,
    )

    post_conversation = ConversationHandler(
        entry_points=[CommandHandler("postjob", post_entry)],
        states={
            POST_CAPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, post_receive_caption)
            ],
        },
        fallbacks=CONVERSATION_FALLBACKS,
        allow_reentry=True,
        name="post_job",
        persistent=True,
    )

    curate_conversation = ConversationHandler(
        entry_points=[CommandHandler("curatejob", curate_entry)],
        states={
            CURATE_CAPTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, curate_receive_caption)
            ],
            CURATE_CHANNEL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, curate_receive_channel)
            ],
        },
        fallbacks=CONVERSATION_FALLBACKS,
        allow_reentry=True,
        name="curate_job",
        persistent=True,
    )

    verify_conversation = ConversationHandler(
        entry_points=[CommandHandler("verify", verify_entry)],
        states={
            VERIFY_EMAIL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, verify_receive_email)
            ],
            VERIFY_CODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, verify_receive_code)
            ],
        },
        fallbacks=[CommandHandler("verify", verify_entry)] + CONVERSATION_FALLBACKS,
        allow_reentry=True,
        name="company_verify",
        persistent=True,
    )

    mycv_conversation = ConversationHandler(
        entry_points=[
            CommandHandler("mycv", mycv_start),
            CallbackQueryHandler(mycv_start, pattern=r"^nav:mycv$"),
        ],
        states={
            MCV_SPEC: [
                CallbackQueryHandler(mcv_spec_pick, pattern=r"^mcvspec:"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, mcv_spec_text),
            ],
            MCV_CITY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, mcv_city)
            ],
            MCV_SKILLS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, mcv_skills)
            ],
        },
        fallbacks=CONVERSATION_FALLBACKS,
        allow_reentry=True,
        name="mycv_match",
        persistent=True,
    )

    application.add_handler(apply_conversation)
    application.add_handler(mycv_conversation)
    application.add_handler(company_conversation)
    application.add_handler(post_conversation)
    application.add_handler(curate_conversation)
    application.add_handler(verify_conversation)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("jobs", jobs))
    application.add_handler(
        CallbackQueryHandler(jobs_page, pattern=r"^jobspage:\d+$")
    )
    application.add_handler(
        CallbackQueryHandler(nav_button, pattern=r"^nav:(jobs|company|help)$")
    )
    application.add_handler(CommandHandler("contact", contact))
    application.add_handler(CommandHandler("admin", admin_help))
    application.add_handler(CommandHandler("list", list_applicants))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("mystats", mystats_command))
    application.add_handler(CommandHandler("mystatus", mystatus_command))
    application.add_handler(CommandHandler("ref", ref_command))
    application.add_handler(CommandHandler("share", share_command))
    application.add_handler(CommandHandler("top", top_command))
    application.add_handler(CommandHandler("export", export_applicants))
    application.add_handler(CommandHandler("broadcast", broadcast_message))
    application.add_handler(CommandHandler("find", find_applicants))
    application.add_handler(CommandHandler("reply", reply_to_applicant))
    application.add_handler(CommandHandler("backup", backup_data))
    application.add_handler(CommandHandler("companies", companies_list))
    application.add_handler(CommandHandler("myjobs", my_jobs))
    application.add_handler(CommandHandler("myapplicants", my_applicants))
    application.add_handler(CommandHandler("closejob", close_job))
    application.add_handler(CommandHandler("openjob", open_job))
    application.add_handler(CommandHandler("deletejob", delete_job))
    application.add_handler(CommandHandler("findjob", find_jobs))
    application.add_handler(CommandHandler("curatejobs", curate_jobs_list))
    application.add_handler(CommandHandler("specialties", specialties_cmd))
    application.add_handler(
        CallbackQueryHandler(specialty_button, pattern=r"^spec:")
    )
    application.add_handler(CommandHandler("match", match_cmd))
    application.add_handler(CommandHandler("prefs", prefs_cmd))
    application.add_handler(CommandHandler("follow", follow_cmd))
    application.add_handler(CommandHandler("wagroups", wa_groups_cmd))
    application.add_handler(CommandHandler("waallow", wa_allow_cmd))
    application.add_handler(CommandHandler("wadeny", wa_deny_cmd))
    application.add_handler(CommandHandler("watest", wa_test_cmd))
    application.add_handler(CommandHandler("wacap", wa_cap_cmd))
    application.add_handler(
        CallbackQueryHandler(wa_button_callback, pattern=r"^wa(on|off):")
    )
    application.add_handler(
        CallbackQueryHandler(
            decision_callback, pattern=r"^dec:(interview|contact):\d+:\d+$"
        )
    )
    application.add_handler(
        ChatMemberHandler(chat_membership_update, ChatMemberHandler.MY_CHAT_MEMBER)
    )
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_free_message)
    )
    application.add_error_handler(on_error)
    schedule_jobs(application)


if __name__ == "__main__":
    import time as sleep_time

    ensure_curated_company()
    print(STUDIO_NAME + " HR Bot is running...")
    while True:
        try:
            application = build_application()
            register_handlers(application)
            application.run_polling(allowed_updates=Update.ALL_TYPES)
            break
        except KeyboardInterrupt:
            break
        except Exception as exc:
            logger.error("Polling stopped (%s), rebuilding in 30s", exc, exc_info=True)
            sleep_time.sleep(30)
