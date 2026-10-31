import re
from pathlib import Path

OUTREACH = Path(__file__).resolve().parent

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
BAD_TLDS = {
    "png", "jpg", "jpeg", "gif", "webp", "svg", "css", "js", "html",
    "php", "xml", "json", "md", "txt", "pdf", "w3", "com/tr",
}
BAD_DOMAINS = (
    "example.", "w3.org", "schema.org", "googleapis", "gstatic", "localhost",
    "blogger.com", "feedburner", "sentry", "wordpress", "lnkd.in", "t.me",
    "telegram.me", "iraqi-jobs.com", "ijobsiq.com", "bayanjo", "joblist",
    "indeed.", "glassdoor.", "linkedin.com", "naukri", "careerjet", "bayt.com",
    "tripadvisor.", "facebook.", "instagram.", "twitter.", "x.com", "youtube.",
)

SECTOR_PATTERNS = {
    "food": re.compile(
        r"مطاعم|مطعم|مطابخ|مقاهي|مقهى|كافيه|كوفي|شيف|طباخ|نادل|بار[يی]ستا|"
        r"حلويات|معجنات|مخبز|عصائر|مشاوي|شاورما|بيتزا|برجر|فطور|بوفيه|"
        r"وجبات|مطبخ|آيس ?كريم|"
        r"restaurants?|caf[ée]s?|coffee|barista|chef|cooks?|waiters?|"
        r"kitchens?|fast[ -]?food|baker(y|ies)|juice|sweets?|ice[ -]?cream|"
        r"food court|pizzeria|kebab|shawarma",
        re.IGNORECASE,
    ),
    "retail": re.compile(
        r"محل|سوبر ?ماركت|بقالة|متجر|مبيعات|كاشير|مندوب|retail|shop|store|"
        r"supermarket|grocery|cashier|merchandis",
        re.IGNORECASE,
    ),
    "medical": re.compile(
        r"مستشفى|عيادة|صيدلية|ممرض|طبيب|طبيبة|معمل|medical|hospital|clinic|"
        r"pharmac|nurse|doctor|lab",
        re.IGNORECASE,
    ),
    "education": re.compile(
        r"مدرسة|معلم|أستاذ|مدرس|روضة|teacher|instructor|school|nursery|tutor",
        re.IGNORECASE,
    ),
    "hospitality": re.compile(
        r"فندق|إقامة|استقبال|hotel|resort|reception|guest|housekeep",
        re.IGNORECASE,
    ),
    "transport": re.compile(
        r"سائق|نقل|توصيل|مكوك|driver|taxi|delivery|courier|logistics|fleet",
        re.IGNORECASE,
    ),
    "construction": re.compile(
        r"بناء|مقاولات|نجار|حداد|دهان|electrician|plumber|welder|construction|"
        r"carpenter|mason|painter",
        re.IGNORECASE,
    ),
    "beauty": re.compile(
        r"صالون|حلاقة|تجميل|كوافير|salon|barber|beauty|spa",
        re.IGNORECASE,
    ),
    "tech": re.compile(
        r"برمج|مطور|تطوير|ويب|مواقع|تطبيق|تقنية|شبكات|مصمم|design|developer|"
        r"programmer|software|web|network|engineer|data|cloud|it\b",
        re.IGNORECASE,
    ),
    "sales": re.compile(
        r"تسويق|sales|marketing|محاسب|account|financial|consultant|مستشار",
        re.IGNORECASE,
    ),
}
SECTOR_LABELS = {
    "food": "مطاعم ومقاهي",
    "retail": "محلات وتجزئة",
    "medical": "صحية",
    "education": "تعليمية",
    "hospitality": "فنادق وضيافة",
    "transport": "نقل وتوصيل",
    "construction": "مقاولات وبناء",
    "beauty": "تجميل وصالونات",
    "tech": "تقنية",
    "sales": "مبيعات وتسويق",
}
AMENITY_LABELS = {
    "restaurant": "مطعم",
    "cafe": "مقهى",
    "fast_food": "وجبات سريعة",
    "food_court": "مطعم",
    "ice_cream": "آيس كريم",
}
GOVERNORATE_NAMES = (
    "بغداد", "البصرة", "الموصل", "موصل", "أربيل", "اربيل", "هولێر", "هەولێر",
    "ھەولێر", "السليمانية", "سلێمانی", "النجف", "كربلاء", "كركوك", "دهوك",
    "دهۆک", "زاخو", "Zakho", "واسط", "الكوت", "ديالى", "دياله", "بعقوبة",
    "ميسان", "العمارة", "ذي قار", "الناصرية", "الأنبار", "الرمادي", "الفلوجة",
    "الديوانية", "بابل", "تكريت", "صلاح الدين", "السماوة", "المثنى", "العراق",
    "baghdad", "basra", "mosul", "erbil", "arbil", "hawler", "sulaymaniyah",
    "slemani", "najaf", "karbala", "kirkuk", "duhok", "dohuk", "wasit", "kut",
    "diyala", "baquba", "maysan", "amara", "dhi qar", "nasiriyah", "anbar",
    "ramadi", "fallujah", "diwaniya", "hillah", "babylon", "tikrit", "saladin",
    "samawah", "muthanna", "iraq", "remote", "عن بعد", "عن بُعد",
)
IRAQ_RE = re.compile(
    "|".join(sorted((re.escape(name) for name in GOVERNORATE_NAMES), key=len, reverse=True)),
    re.IGNORECASE,
)
FREE_MAIL = ("gmail.com", "yahoo.", "hotmail.", "outlook.", "icloud.com", "proton")

DEFAULT_BOT_TEMPLATE = OUTREACH / "email_template.txt"
FOOD_BOT_TEMPLATE = OUTREACH / "email_template_food.txt"
DEFAULT_BOT_SUBJECT = "بوت توظيف مجاني للشركات العراقية"
FOOD_BOT_SUBJECT = "بوت توظيف مجاني للمطاعم والمقاهي العراقية"
SITE_SUBJECT = "تطوير مواقع وتطبيقات وواجهات - عرض تعاون"


def clean_email(raw):
    email = str(raw or "").strip().strip(".,;:()<>\"'").lower()
    if "@" not in email or ".." in email:
        return None
    domain = email.split("@", 1)[1]
    local = email.split("@", 1)[0]
    if not local or domain.endswith(tuple(BAD_TLDS)):
        return None
    if any(bad in domain for bad in BAD_DOMAINS):
        return None
    if re.search(r"\.(png|jpe?g|gif|webp|svg|css|js)$", local):
        return None
    return email


def emails_in(text):
    found = []
    for raw in EMAIL_RE.findall(str(text or "")):
        email = clean_email(raw)
        if email and email not in found:
            found.append(email)
    return found


def detect_sector(text):
    blob = str(text or "")
    for key, pattern in SECTOR_PATTERNS.items():
        if pattern.search(blob):
            return key
    return None


def is_iraq(text):
    return bool(IRAQ_RE.search(str(text or "")))


def is_free_mail(domain):
    domain = (domain or "").lower()
    return any(domain.startswith(prefix) or domain == prefix for prefix in FREE_MAIL)


def bot_template_for(roles):
    if detect_sector(roles) == "food":
        return FOOD_BOT_TEMPLATE, FOOD_BOT_SUBJECT
    return DEFAULT_BOT_TEMPLATE, DEFAULT_BOT_SUBJECT
