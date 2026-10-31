import html
import json
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import storage

SITE_REPO_DIR = Path.home() / "mulhim-jobs"
SITE_INDEX = SITE_REPO_DIR / "index.html"
REPO_REMOTE = "https://github.com/sfyanbd36-svg/mulhim-jobs.git"
SITE_URL = "https://sfyanbd36-svg.github.io/mulhim-jobs"
BOT_USERNAME = "mulhimstudio_hr_bot"
BOT_LINK = "https://t.me/" + BOT_USERNAME
BOT_JOBS = BOT_LINK + "?start=jobs"
BOT_COMPANY = BOT_LINK + "?start=company"
QR_URL = SITE_URL + "/qr.png"
INDEXNOW_KEY = "03f48873e9393cd1a716dbd8091f5c72"
INDEXNOW_KEY_FILE = "mulhim-indexnow-key.txt"
INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"

CITY_PAGES = [
    ("baghdad", "بغداد", ("بغداد", "Baghdad", "الكاظمية", "كاظمية")),
    ("basra", "البصرة", ("البصرة", "Basra")),
    ("mosul", "الموصل", ("الموصل", "موصل", "Mosul")),
    ("erbil", "أربيل", ("أربيل", "اربيل", "Erbil", "Arbil", "Hawler")),
    ("sulaymaniyah", "السليمانية", ("السليمانية", "سليمانية", "Sulaymaniyah", "Slemani", "sulaymanyah")),
    ("najaf", "النجف", ("النجف", "Najaf")),
    ("karbala", "كربلاء", ("كربلاء", "Karbala")),
    ("kirkuk", "كركوك", ("كركوك", "Kirkuk")),
    ("duhok", "دهوك", ("دهوك", "Duhok", "Dohuk")),
    ("kut", "الكوت", ("الكوت", "واسط", "Kut", "Wasit")),
    ("diyala", "ديالى", ("ديالى", "دياله", "Diyala", "بعقوبة", "Baquba")),
    ("amara", "العمارة", ("العمارة", "ميسان", "Maysan", "Amara")),
    ("nasiriyah", "الناصرية", ("الناصرية", "ذي قار", "Nasiriyah", "Dhi Qar")),
    ("ramadi", "الرمادي", ("الرمادي", "الأنبار", "Ramadi", "Anbar", "الفلوجة", "Fallujah")),
    ("diwaniya", "الديوانية", ("الديوانية", "Diwaniya")),
    ("hillah", "بابل", ("بابل", "Hillah", "Babylon")),
    ("tikrit", "تكريت", ("تكريت", "صلاح الدين", "Tikrit", "Saladin")),
]

NATIONWIDE = ("العراق", "Iraq", "Remote", "عن بعد", "عن بُعد", "-")

PROF_PAGES = [
    ("engineer", "مهندس", ("مهندس", "هندسة", "engineer", "engineering")),
    ("accountant", "محاسب", ("محاسب", "محاسبة", "accountant", "accounting")),
    ("developer", "مبرمج", ("مبرمج", "مطور", "برمجة", "developer", "programmer", "software")),
    ("nurse", "ممرض وطبيب", ("ممرض", "ممرضة", "طبيب", "طبي", "nurse", "medical", "doctor")),
    ("teacher", "معلم", ("معلم", "أستاذ", "مدرس", "teacher", "instructor", "تعليم")),
    ("sales", "مبيعات وتسويق", ("مبيعات", "مندوب", "تسويق", "sales", "marketing", "commercial")),
    ("driver", "سائق", ("سائق", "قيادة", "driver")),
    ("admin", "إداري وإنساني", ("إداري", "اداري", "سكرتير", "استقبال", "administrative", "secretary", "موارد بشرية", "hr ")),
    ("finance", "مالي ومصرفي", ("مصرفي", "بنك", "bank", "مالي", "مالية", "finance")),
    ("lawyer", "محام", ("محام", "قانون", "lawyer", "legal")),
    ("pharmacist", "صيدلي", ("صيدلي", "صيدل", "pharmacist", "pharmacy")),
    ("technician", "فني", ("فني", "تقني", "technician", "mechanic", "electric", "كهرباء", "ميكانيك")),
]


def _local_jobs():
    jobs = [
        row
        for row in storage.read_table("company_jobs")
        if str(row.get("active", "1")) == "1" and (row.get("title") or "").strip()
    ]
    jobs.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    companies = {
        str(c.get("company_id", "")): c for c in storage.read_table("companies")
    }
    out = []
    for job in jobs[:60]:
        company = companies.get(str(job.get("company_id", "")), {})
        out.append(
            {
                "title": job.get("title", ""),
                "company": company.get("name", "") or "-",
                "city": _city_from_caption(job.get("caption", "")),
                "url": "",
                "posted": (job.get("created_at") or "")[:10],
            }
        )
    return out


def _city_from_caption(caption):
    text = caption or ""
    for city in ("بغداد", "البصرة", "الموصل", "أربيل", "اربيل", "النجف", "كربلاء", "الكوت", "بابل", "دهوك", "السليمانية", "العمارة", "الناصرية", "الرمادي", "كاظمية", "الحاجب", "المحمودية", "كركوك", "ديالى", "دياله", "الديوانية", "واسط"):
        if city in text:
            return city
    return "العراق"


def _feed_jobs():
    rows = sorted(
        storage.read_table("feed_jobs"),
        key=lambda r: r.get("posted") or "",
        reverse=True,
    )
    out = []
    for row in rows[:400]:
        out.append(
            {
                "title": row.get("title", ""),
                "company": row.get("company", "") or "-",
                "city": row.get("city", "") or "-",
                "url": row.get("url", ""),
                "posted": (row.get("posted") or "")[:10],
            }
        )
    return out


def _in_city(city, aliases):
    text = (city or "").strip().lower()
    if not text or text == "-":
        return False
    return any(str(a).lower() in text for a in aliases)


def _is_nationwide(city):
    text = (city or "").strip()
    if not text or text == "-":
        return True
    return any(text == n or n.lower() in text.lower() for n in NATIONWIDE) and not any(
        _in_city(city, aliases) for _, _, aliases in CITY_PAGES
    )


def _card(job, source):
    url = job["url"]
    if url:
        action = (
            '<a class="btn" href="{u}" target="_blank" rel="noopener">افتح الوظيفة</a>'
        ).format(u=html.escape(url, quote=True))
    else:
        action = (
            '<a class="btn" href="{u}">قدّم عبر البوت</a>'
        ).format(u=BOT_JOBS)
    return (
        '<article class="card">'
        '<span class="src">{src}</span>'
        "<h2>{title}</h2>"
        '<p class="meta">{company} &middot; {city} &middot; {posted}</p>'
        "</article>"
        '<div class="row">{action}</div>'
    ).format(
        src=html.escape(source),
        title=html.escape(job["title"] or "بدون عنوان"),
        company=html.escape(job["company"] or "-"),
        city=html.escape(job["city"] or "-"),
        posted=html.escape(job["posted"] or "-"),
        action=action,
    )


STYLE = """:root {{ --bg:#0f1220; --card:#171b30; --line:#262c4a; --txt:#eef0ff; --mut:#9aa3c7; --acc:#5b8cff; --ok:#3ecf8e; }}
* {{ box-sizing:border-box; margin:0; padding:0; }}
body {{ background:var(--bg); color:var(--txt); font-family:"Segoe UI",Tahoma,Arial,sans-serif; line-height:1.6; }}
header {{ padding:48px 20px 36px; text-align:center; background:linear-gradient(160deg,#171b30,#0f1220); border-bottom:1px solid var(--line); }}
header h1 {{ font-size:2.1rem; }}
header .sub {{ color:var(--mut); margin-top:10px; font-size:1.05rem; }}
header .badges {{ display:flex; justify-content:center; gap:10px; flex-wrap:wrap; margin-top:18px; }}
header .badge {{ background:var(--card); border:1px solid var(--line); color:var(--mut); border-radius:999px; padding:6px 14px; font-size:.85rem; }}
header .ctas {{ display:flex; justify-content:center; gap:12px; flex-wrap:wrap; margin-top:22px; }}
header .cta {{ display:inline-block; padding:13px 26px; border-radius:12px; background:var(--acc); color:#fff; text-decoration:none; font-weight:700; }}
header .cta.alt {{ background:transparent; border:1px solid var(--line); color:var(--txt); }}
header .qr {{ margin-top:22px; }}
header .qr img {{ width:120px; height:120px; border-radius:12px; border:1px solid var(--line); background:#fff; padding:6px; }}
header .qr p {{ color:var(--mut); font-size:.8rem; margin-top:6px; }}
main {{ max-width:860px; margin:0 auto; padding:24px 16px 60px; }}
h2.section {{ margin:34px 0 14px; font-size:1.25rem; border-right:4px solid var(--acc); padding-right:10px; }}
.intro {{ color:var(--mut); margin:6px 0 10px; }}
.chips {{ display:flex; flex-wrap:wrap; gap:8px; margin:14px 0 6px; }}
.chip {{ background:var(--card); border:1px solid var(--line); color:var(--txt); border-radius:999px; padding:6px 14px; font-size:.88rem; text-decoration:none; }}
.chip:hover {{ border-color:var(--acc); }}
.chip.active {{ background:var(--acc); border-color:var(--acc); color:#fff; }}
.card {{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:14px 16px; margin-bottom:10px; }}
.card h2 {{ font-size:1.02rem; }}
.card .meta {{ color:var(--mut); font-size:.9rem; margin-top:4px; }}
.src {{ display:inline-block; font-size:.72rem; color:var(--ok); border:1px solid var(--ok); border-radius:999px; padding:1px 8px; margin-bottom:6px; }}
.row {{ display:flex; justify-content:flex-start; gap:10px; margin:-4px 0 14px; }}
.btn {{ background:var(--acc); color:#fff; text-decoration:none; border-radius:10px; padding:7px 14px; font-size:.88rem; font-weight:600; }}
.btn.muted {{ background:transparent; border:1px solid var(--line); color:var(--mut); cursor:default; }}
.faq {{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:16px; margin-bottom:12px; }}
.faq h3 {{ font-size:1rem; margin-bottom:6px; }}
.faq p {{ color:var(--mut); font-size:.92rem; }}
footer {{ border-top:1px solid var(--line); color:var(--mut); text-align:center; padding:22px 16px; font-size:.85rem; }}
footer a {{ color:var(--acc); text-decoration:none; }}
"""

PAGE = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
{gsc_meta}
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="canonical" href="{site_url}/">
<title>مهن - وظائف بغداد والعراق | بوت تيليجرام مجاني</title>
<meta name="description" content="وظائف محدثة ببغداد وجميع المحافظات العراقية + بوت تيليجرام مجاني لتلقي التنبيهات وعمل سيرة ذاتية PDF والتقديم على الوظائف.">
<meta property="og:title" content="مهن - وظائف العراق بمكان واحد">
<meta property="og:description" content="تابع الوظائف، قدّم بسيرة PDF جاهزة، وتوصل الوظائف لجوالك. مجاني.">
<meta property="og:type" content="website">
<meta property="og:url" content="{site_url}/">
<style>
{style}
</style>
</head>
<body>
<header>
  <h1>مهن &mdash; وظائف بغداد والعراق</h1>
  <p class="sub">وظائف محلية موثوقة + سوق التوظيف العراقي، محدّثة تلقائياً كل 6 ساعات</p>
  <div class="badges">
    <span class="badge">📄 سيرة ذاتية PDF مجانية</span>
    <span class="badge">🔔 تنبيهات يومية بالوظائف المناسبة</span>
    <span class="badge">🏢 للشركات: انشر وظيفتك برسالة وحدة</span>
  </div>
  <div class="ctas">
    <a class="cta" href="{bot_jobs}">💼 تصفّح الوظائف بالبوت</a>
    <a class="cta alt" href="{bot_company}">🏢 سجّل شركتك</a>
  </div>
  <div class="qr">
    <img src="{qr_url}" alt="QR للبوت" width="120" height="120">
    <p>امسح الكود بالموبايل وافتح البوت مباشرة</p>
  </div>
</header>
<main>
  <h2 class="section">وظائف حسب المدينة</h2>
  <div class="chips">{index_chips}</div>
  <h2 class="section">وظائف حسب التخصص</h2>
  <div class="chips">{prof_chips}</div>
  <p class="intro">ملخص الأسبوع: <a href="{week_url}">{week_title}</a></p>
  <h2 class="section">وظائف محلية {local_badge}</h2>
  {local_cards}
  <h2 class="section">سوق التوظيف {feed_badge}</h2>
  {feed_cards}
</main>
<footer>
  اعمل سيرة ذاتية PDF مجانية وتابع الوظائف عبر البوت &mdash;
  <a href="{bot_link}">@{bot_username}</a>
  <br>آخر تحديث: {now}
</footer>
</body>
</html>
"""

CITY_PAGE = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
{gsc_meta}
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="canonical" href="{site_url}/{slug}.html">
<title>وظائف {city} {count_badge}- {year} | ملهم</title>
<meta name="description" content="أحدث وظائف {city}: {desc_jobs} من الشركات المحلية وسوق التوظيف العراقي. سيرة ذاتية PDF مجانية وتنبيهات وظائف عبر البوت.">
<meta property="og:title" content="وظائف {city} {count_badge}| ملهم">
<meta property="og:description" content="تابع وظائف {city} المحدّثة كل 6 ساعات وقدّم بسيرة PDF جاهزة عبر البوت.">
<meta property="og:type" content="website">
<meta property="og:url" content="{site_url}/{slug}.html">
<style>
{style}
</style>
</head>
<body>
<header>
  <h1>وظائف {city}{h1_extra}</h1>
  <p class="sub">{city}: وظائف محلية + سوق التوظيف العراقي، محدّثة كل 6 ساعات</p>
  <div class="badges">
    <span class="badge">📄 سيرة ذاتية PDF مجانية</span>
    <span class="badge">🔔 تنبيهات وظائف {city} لجوالك</span>
    <span class="badge">🏢 الشركات تنشر مجاناً</span>
  </div>
  <div class="ctas">
    <a class="cta" href="{bot_jobs}">💼 وظائف {city} بالبوت</a>
    <a class="cta alt" href="{bot_company}">🏢 انشر وظيفة</a>
  </div>
  <div class="qr">
    <img src="{qr_url}" alt="QR للبوت" width="120" height="120">
    <p>امسح الكود وافتح البوت مباشرة</p>
  </div>
</header>
<main>
  <nav class="chips" aria-label="المدن">{chips}</nav>
  <div class="chips" aria-label="التخصصات">{prof_chips}</div>
  <p class="intro">{intro}</p>
  <h2 class="section">وظائف شاغرة بـ{city} {count_badge}</h2>
  {city_cards}
  <h2 class="section">وظائف تغطي العراق وعن بُعد {nationwide_badge}</h2>
  {nationwide_cards}
  <h2 class="section">كيف تحصل على وظائف {city}؟</h2>
  <div class="faq">
    <h3>كم وظيفة شاغرة بـ{city} حالياً؟</h3>
    <p>{faq_count_text}</p>
  </div>
  <div class="faq">
    <h3>كيف أتقدم على وظائف {city}؟</h3>
    <p>افتح بوت ملهم على تيليجرام، أرسل سيرتك (تصير PDF جاهزة تلقائياً) أو عبّي الاستمارة، وبعدها تتقدم على وظائف {city} بضغطة وحدة.</p>
  </div>
  <div class="faq">
    <h3>كيف أستقبل تنبيه بوظائف {city} الجديدة؟</h3>
    <p>اكتب /follow داخل البوت وحدّد {city} ومهاراتك - يوصلك 3 وظائف مناسبة كل يوم الساعة 11 صباحاً مجاناً.</p>
  </div>
  <h2 class="section">الشركات والوظائف</h2>
  <div class="row" style="margin-top:8px">
    <a class="btn" href="{bot_jobs}">تصفّح كل وظائف {city}</a>
    <a class="btn" href="{bot_company}">سجّل شركتك</a>
  </div>
</main>
<footer>
  <a href="{site_url}/">مهن - الرئيسية</a> &middot;
  <a href="{bot_link}">@{bot_username}</a>
  <br>آخر تحديث: {now}
</footer>
<script type="application/ld+json">{jsonld}</script>
</body>
</html>
"""

PROF_PAGE = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
{gsc_meta}
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="canonical" href="{site_url}/{slug}.html">
<title>وظائف {prof} في العراق {count_badge}- {year} | ملهم</title>
<meta name="description" content="أحدث وظائف {prof} في العراق: {desc_jobs} من الشركات ومنصات التوظيف. تابع التنبيهات وقدّم بسيرة PDF مجانية عبر بوت ملهم.">
<meta property="og:title" content="وظائف {prof} {count_badge}| ملهم">
<meta property="og:description" content="تابع وظائف {prof} المحدّثة كل 6 ساعات وقدّم بسيرة PDF جاهزة عبر البوت.">
<meta property="og:type" content="website">
<meta property="og:url" content="{site_url}/{slug}.html">
<style>
{style}
</style>
</head>
<body>
<header>
  <h1>وظائف {prof} {count_badge}</h1>
  <p class="sub">تخصص {prof}: وظائف محلية + سوق التوظيف العراقي، محدّثة كل 6 ساعات</p>
  <div class="badges">
    <span class="badge">📄 سيرة ذاتية PDF مجانية</span>
    <span class="badge">🔔 تنبيهات وظائف {prof} لجوالك</span>
    <span class="badge">🏢 الشركات تنشر مجاناً</span>
  </div>
  <div class="ctas">
    <a class="cta" href="{bot_jobs}">💼 وظائف {prof} بالبوت</a>
    <a class="cta alt" href="{bot_company}">🏢 انشر وظيفة</a>
  </div>
  <div class="qr">
    <img src="{qr_url}" alt="QR للبوت" width="120" height="120">
    <p>امسح الكود وافتح البوت مباشرة</p>
  </div>
</header>
<main>
  <nav class="chips" aria-label="التخصصات">{prof_chips}</nav>
  <p class="intro">{intro}</p>
  <h2 class="section">وظائف {prof} الشاغرة {count_badge}</h2>
  {jobs_cards}
  <h2 class="section">وظائف حسب المدينة</h2>
  <div class="chips">{city_chips}</div>
  <h2 class="section">كيف تحصل على وظائف {prof}؟</h2>
  <div class="faq">
    <h3>كم وظيفة {prof} شاغرة حالياً؟</h3>
    <p>{faq_count_text}</p>
  </div>
  <div class="faq">
    <h3>كيف أستقبل تنبيه بوظائف {prof} الجديدة؟</h3>
    <p>افتح بوت ملهم على تيليجرام، اكتب /prefs ثم /follow وحدد تخصصك {prof} - يوصلك ملخص الوظائف المناسبة مجاناً كل يوم.</p>
  </div>
  <div class="row" style="margin-top:8px">
    <a class="btn" href="{bot_jobs}">تصفّح كل وظائف {prof}</a>
    <a class="btn" href="{bot_company}">سجّل شركتك</a>
  </div>
</main>
<footer>
  <a href="{site_url}/">مهن - الرئيسية</a> &middot;
  <a href="{bot_link}">@{bot_username}</a>
  <br>آخر تحديث: {now}
</footer>
<script type="application/ld+json">{jsonld}</script>
</body>
</html>
"""

COMBO_PAGE = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
{gsc_meta}
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="canonical" href="{site_url}/{slug}.html">
<title>وظائف {prof} في {city} {count_badge}- {year} | ملهم</title>
<meta name="description" content="أحدث وظائف {prof} في {city}: {desc_jobs} من الشركات ومنصات التوظيف العراقية. تنبيهات مجاناً وسيرة ذاتية PDF عبر بوت ملهم.">
<meta property="og:title" content="وظائف {prof} في {city} {count_badge}| ملهم">
<meta property="og:description" content="تابع وظائف {prof} في {city} المحدّثة كل 6 ساعات وقدّم بسيرة PDF جاهزة عبر البوت.">
<meta property="og:type" content="website">
<meta property="og:url" content="{site_url}/{slug}.html">
<style>
{style}
</style>
</head>
<body>
<header>
  <h1>وظائف {prof} في {city} {count_badge}</h1>
  <p class="sub">{prof} في {city}: وظائف محلية + سوق التوظيف العراقي، محدّثة كل 6 ساعات</p>
  <div class="badges">
    <span class="badge">📄 سيرة ذاتية PDF مجانية</span>
    <span class="badge">🔔 تنبيهات {prof} لجوالك</span>
    <span class="badge">🏢 الشركات تنشر مجاناً</span>
  </div>
  <div class="ctas">
    <a class="cta" href="{bot_jobs}">💼 وظائف {prof} بالبوت</a>
    <a class="cta alt" href="{bot_company}">🏢 انشر وظيفة</a>
  </div>
</header>
<main>
  <nav class="chips" aria-label="تخصصات المدينة">{prof_chips}</nav>
  <p class="intro">{intro}</p>
  <h2 class="section">وظائف {prof} بـ{city} {count_badge}</h2>
  {jobs_cards}
  <h2 class="section">وظائف {prof} بكل العراق {other_badge}</h2>
  {other_cards}
  <h2 class="section">صفحات أخرى</h2>
  <div class="chips" aria-label="المدن">{city_chips}</div>
  <div class="faq">
    <h3>كيف أستقبل تنبيهات {prof} في {city}؟</h3>
    <p>افتح بوت ملهم على تيليجرام، اكتب /prefs {city} ثم /follow - يوصلك ملخص الوظائف المناسبة مجاناً كل يوم.</p>
  </div>
  <div class="row" style="margin-top:8px">
    <a class="btn" href="{city_url}">كل وظائف {city}</a>
    <a class="btn" href="{prof_url}">كل وظائف {prof}</a>
  </div>
</main>
<footer>
  <a href="{site_url}/">مهن - الرئيسية</a> &middot;
  <a href="{bot_link}">@{bot_username}</a>
  <br>آخر تحديث: {now}
</footer>
<script type="application/ld+json">{jsonld}</script>
</body>
</html>
"""

ARTICLE_PAGE = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
{gsc_meta}
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="canonical" href="{site_url}/{slug}.html">
<title>{title} | ملهم</title>
<meta name="description" content="{description}">
<meta property="og:title" content="{title} | ملهم">
<meta property="og:description" content="{description}">
<meta property="og:type" content="article">
<meta property="og:url" content="{site_url}/{slug}.html">
<style>
{style}
</style>
</head>
<body>
<header>
  <h1>{title}</h1>
  <p class="sub">تقرير أسبوعي مولّد تلقائياً من بيانات وظائف العراق على ملهم</p>
</header>
<main>
  <p class="intro">{intro}</p>
  <h2 class="section">أكثر التخصصات طلباً هذا الأسبوع</h2>
  {prof_cards}
  <h2 class="section">أكثر المحافظات نشاطاً</h2>
  {city_cards}
  <div class="row" style="margin-top:14px">
    <a class="btn" href="{bot_jobs}">تصفّح كل الوظائف بالبوت</a>
    <a class="btn" href="{bot_company}">انشر وظيفتك مجاناً</a>
  </div>
</main>
<footer>
  <a href="{site_url}/">مهن - الرئيسية</a> &middot;
  <a href="{bot_link}">@{bot_username}</a>
  <br>آخر تحديث: {now}
</footer>
<script type="application/ld+json">{jsonld}</script>
</body>
</html>
"""


def _env(name):
    value = (os.environ.get(name, "") or "").strip()
    if value:
        return value
    env_path = Path(__file__).resolve().parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith(name + "="):
                return line.partition("=")[2].strip()
    return ""


def _gsc_meta():
    code = _env("GSC_SITE_VERIFY")
    if not code:
        return ""
    return '<meta name="google-site-verification" content="{c}">'.format(
        c=html.escape(code, quote=True)
    )


def _job_jsonld(job, position, city_name):
    posted = _parse_date(job.get("posted"))
    item = {
        "@type": "JobPosting",
        "title": job.get("title") or "وظيفة",
        "description": "{title} لدى {company} في {city}.".format(
            title=job.get("title") or "",
            company=job.get("company") or "-",
            city=city_name,
        ),
        "datePosted": posted.strftime("%Y-%m-%d"),
        "validThrough": (posted + timedelta(days=30)).strftime("%Y-%m-%d"),
        "employmentType": "FULL_TIME",
        "hiringOrganization": {
            "@type": "Organization",
            "name": job.get("company") or "-",
        },
        "jobLocation": {
            "@type": "Place",
            "address": {
                "@type": "PostalAddress",
                "addressLocality": city_name,
                "addressCountry": "IQ",
            },
        },
        "url": job.get("url") or BOT_JOBS,
    }
    return {"@type": "ListItem", "position": position, "item": item}


def _parse_date(value):
    text = (value or "").strip()[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return datetime.now()


def _chips(active_slug=""):
    out = []
    for slug, name, _ in CITY_PAGES:
        cls = ' class="chip active"' if slug == active_slug else ' class="chip"'
        out.append(
            '<a{cls} href="{slug}.html">وظائف {name}</a>'.format(
                cls=cls, slug=slug, name=html.escape(name)
            )
        )
    return "".join(out)


def _badge(count):
    return "({n}) ".format(n=count) if count else ""


def _prof_chips(active_slug=""):
    out = []
    for slug, name, _ in PROF_PAGES:
        cls = ' class="chip active"' if slug == active_slug else ' class="chip"'
        out.append(
            '<a{cls} href="{slug}.html">وظائف {name}</a>'.format(
                cls=cls, slug=slug, name=html.escape(name)
            )
        )
    return "".join(out)


def _matches_prof(job, terms):
    text = ((job.get("title") or "") + " " + (job.get("company") or "")).lower()
    return any(str(t).lower() in text for t in terms)


def _prof_chips_for_city(city_slug, city_name):
    out = []
    for pslug, pname, _ in PROF_PAGES:
        out.append(
            '<a class="chip" href="{c}-{p}.html">وظائف {pn} بـ{cn}</a>'.format(
                c=city_slug, p=pslug, pn=html.escape(pname), cn=html.escape(city_name)
            )
        )
    return "".join(out)


def _city_chips_for_prof(prof_slug):
    out = []
    for cslug, cname, _ in CITY_PAGES:
        out.append(
            '<a class="chip" href="{c}-{p}.html">{cn}</a>'.format(
                c=cslug, p=prof_slug, cn=html.escape(cname)
            )
        )
    return "".join(out)


def _combo_slugs():
    return [
        "{c}-{p}".format(c=cslug, p=pslug)
        for cslug, _, _ in CITY_PAGES
        for pslug, _, _ in PROF_PAGES
    ]


def week_slug(today=None):
    today = today or datetime.now()
    iso = today.isocalendar()
    return "week-{y}-w{w:02d}".format(y=iso[0], w=iso[1])


def build_page():
    local = _local_jobs()
    feed_jobs = _feed_jobs()
    return PAGE.format(
        site_url=SITE_URL,
        gsc_meta=_gsc_meta(),
        style=STYLE,
        bot_jobs=BOT_JOBS,
        bot_company=BOT_COMPANY,
        bot_link=BOT_LINK,
        bot_username=BOT_USERNAME,
        qr_url=QR_URL,
        index_chips=_chips(),
        prof_chips=_prof_chips(),
        week_url="{base}/{slug}.html".format(base=SITE_URL, slug=week_slug()),
        week_title="أكثر التخصصات طلباً هذا الأسبوع",
        local_n=len(local),
        feed_n=len(feed_jobs),
        local_badge=_badge(len(local)),
        feed_badge=_badge(len(feed_jobs)),
        local_cards="\n".join(_card(j, "محلية") for j in local) or "<p>لا توجد وظائف محلية الآن.</p>",
        feed_cards="\n".join(_card(j, "السوق") for j in feed_jobs) or "<p>لا توجد وظائف سوق الآن.</p>",
        now=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )


def build_city_page(slug, city_name, aliases):
    local = _local_jobs()
    feed_jobs = _feed_jobs()
    city_local = [j for j in local if _in_city(j.get("city"), aliases)]
    city_feed = [j for j in feed_jobs if _in_city(j.get("city"), aliases)]
    nationwide = [
        j
        for j in (local + feed_jobs)
        if _is_nationwide(j.get("city")) and not _in_city(j.get("city"), aliases)
    ]
    city_jobs = city_local + city_feed
    count = len(city_jobs)
    count_badge = _badge(count)
    desc_jobs = (
        "{count} فرصة شاغرة محدّثة اليوم".format(count=count)
        if count
        else "وظائف محدّثة تلقائياً كل 6 ساعات"
    )
    h1_extra = " — {count} فرصة شاغرة".format(count=count) if count else ""
    faq_count_text = (
        "عدد الوظائف المحدّثة بـ{c} على هذه الصفحة {n}، تتجدد تلقائياً كل 6 ساعات "
        "من الشركات المحلية ومنصات التوظيف العراقية.".format(c=city_name, n=count)
        if count
        else "لا توجد فرصة مدرجة بـ{c} حالياً - تتم تحديث الصفحة تلقائياً كل 6 ساعات "
        "فور نزول وظائف جديدة.".format(c=city_name)
    )
    intro = (
        "تابع أحدث وظائف {city} بمكان واحد: {count} فرصة شاغرة حالياً من الشركات "
        "المحلية ومنصات التوظيف العراقية، تتحدّث تلقائياً كل 6 ساعات - مع سيرة ذاتية "
        "PDF مجانية وتنبيهات مجاناً لجوالك عبر بوت ملهم على تيليجرام."
    ).format(city=city_name, count=count)
    if not count:
        intro = (
            "تابع أحدث وظائف {city} - الصفحة تتجدد تلقائياً كل 6 ساعات فور نزول "
            "وظائف جديدة من الشركات المحلية ومنصات التوظيف، مع تنبيهات مجاناً لجوالك "
            "عبر بوت ملهم على تيليجرام."
        ).format(city=city_name)
    jsonld = json.dumps(
        {
            "@context": "https://schema.org",
            "@type": "CollectionPage",
            "name": "وظائف {c}".format(c=city_name),
            "url": "{base}/{slug}.html".format(base=SITE_URL, slug=slug),
            "inLanguage": "ar",
            "isPartOf": {"@type": "WebSite", "name": "مهن", "url": SITE_URL + "/"},
            "mainEntity": {
                "@type": "ItemList",
                "numberOfItems": count,
                "itemListElement": [
                    _job_jsonld(j, i + 1, city_name)
                    for i, j in enumerate(city_jobs[:15])
                ],
            },
        },
        ensure_ascii=False,
    )
    return CITY_PAGE.format(
        site_url=SITE_URL,
        gsc_meta=_gsc_meta(),
        slug=slug,
        city=city_name,
        count=count,
        count_badge=count_badge,
        desc_jobs=desc_jobs,
        h1_extra=h1_extra,
        faq_count_text=faq_count_text,
        year=datetime.now().year,
        style=STYLE,
        chips=_chips(slug),
        prof_chips=_prof_chips_for_city(slug, city_name),
        bot_jobs=BOT_JOBS,
        bot_company=BOT_COMPANY,
        bot_link=BOT_LINK,
        bot_username=BOT_USERNAME,
        qr_url=QR_URL,
        intro=intro,
        city_n=count,
        city_cards="\n".join(
            [_card(j, "محلية") for j in city_local] + [_card(j, "السوق") for j in city_feed]
        )
        or "<p>لا توجد وظائف بـ{c} الآن - تابع قسم العراق بالأسفل.".format(c=city_name),
        nationwide_n=len(nationwide),
        nationwide_badge=_badge(len(nationwide)),
        nationwide_cards="\n".join(_card(j, "تغطي العراق") for j in nationwide[:6])
        or "<p>لا توجد وظائف مفتوحة لكل العراق الآن.</p>",
        jsonld=jsonld,
        now=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )


def build_city_files():
    return {
        "{slug}.html".format(slug=slug): build_city_page(slug, name, aliases)
        for slug, name, aliases in CITY_PAGES
    }


def build_prof_page(slug, prof_name, terms):
    local = _local_jobs()
    feed_jobs = _feed_jobs()
    prof_jobs = [j for j in local + feed_jobs if _matches_prof(j, terms)]
    count = len(prof_jobs)
    count_badge = _badge(count)
    desc_jobs = (
        "{count} فرصة شاغرة محدّثة اليوم".format(count=count)
        if count
        else "وظائف محدّثة تلقائياً كل 6 ساعات"
    )
    faq_count_text = (
        "عدد الوظائف المحدّثة لتخصص {p} على هذه الصفحة {c}، تتجدد تلقائياً كل 6 ساعات "
        "من الشركات ومنصات التوظيف العراقية.".format(p=prof_name, c=count)
        if count
        else "لا توجد فرصة مدرجة لتخصص {p} حالياً - تتم تحديث الصفحة تلقائياً كل 6 ساعات "
        "فور نزول وظائف جديدة لهذا التخصص.".format(p=prof_name)
    )
    intro = (
        "تابع أحدث وظائف {prof} بمكان واحد: {count} فرصة شاغرة حالياً، "
        "تتحدّث تلقائياً كل 6 ساعات - مع سيرة ذاتية PDF مجانية وتنبيهات مجاناً "
        "لجوالك عبر بوت ملهم على تيليجرام."
    ).format(prof=prof_name, count=count)
    if not count:
        intro = (
            "تابع أحدث وظائف {prof} في العراق - التخصص يتجدد تلقائياً كل 6 ساعات من "
            "الشركات ومنصات التوظيف، مع تنبيهات مجاناً لجوالك عبر بوت ملهم على تيليجرام."
        ).format(prof=prof_name)
    jsonld = json.dumps(
        {
            "@context": "https://schema.org",
            "@type": "CollectionPage",
            "name": "وظائف {p}".format(p=prof_name),
            "url": "{base}/{slug}.html".format(base=SITE_URL, slug=slug),
            "inLanguage": "ar",
            "isPartOf": {"@type": "WebSite", "name": "مهن", "url": SITE_URL + "/"},
            "mainEntity": {
                "@type": "ItemList",
                "numberOfItems": count,
                "itemListElement": [
                    _job_jsonld(j, i + 1, j.get("city") or "العراق")
                    for i, j in enumerate(prof_jobs[:15])
                ],
            },
        },
        ensure_ascii=False,
    )
    return PROF_PAGE.format(
        site_url=SITE_URL,
        gsc_meta=_gsc_meta(),
        slug=slug,
        prof=prof_name,
        count=count,
        count_badge=count_badge,
        desc_jobs=desc_jobs,
        faq_count_text=faq_count_text,
        year=datetime.now().year,
        style=STYLE,
        prof_chips=_prof_chips(slug),
        city_chips=_city_chips_for_prof(slug),
        bot_jobs=BOT_JOBS,
        bot_company=BOT_COMPANY,
        bot_link=BOT_LINK,
        bot_username=BOT_USERNAME,
        qr_url=QR_URL,
        intro=intro,
        jobs_n=count,
        jobs_cards="\n".join(_card(j, "مطابق للتخصص") for j in prof_jobs)
        or "<p>لا توجد وظائف تخصص {p} مدرجة حالياً - تابع البوت، الجديد يوصل تلقائياً.</p>".format(p=prof_name),
        jsonld=jsonld,
        now=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )


def build_prof_files():
    return {
        "{slug}.html".format(slug=slug): build_prof_page(slug, name, terms)
        for slug, name, terms in PROF_PAGES
    }


def build_combo_page(city_slug, city_name, aliases, prof_slug, prof_name, terms):
    local = _local_jobs()
    feed_jobs = _feed_jobs()
    base = local + feed_jobs
    label = "{p} في {c}".format(p=prof_name, c=city_name)
    combo = [
        j
        for j in base
        if _in_city(j.get("city"), aliases) and _matches_prof(j, terms)
    ]
    other = [j for j in base if _matches_prof(j, terms) and j not in combo]
    count = len(combo)
    count_badge = _badge(count)
    desc_jobs = (
        "{count} فرصة شاغرة محدّثة اليوم".format(count=count)
        if count
        else "وظائف محدّثة تلقائياً كل 6 ساعات"
    )
    intro = (
        "تابع أحدث وظائف {label}: {count} فرصة شاغرة حالياً، تتحدّث تلقائياً كل 6 ساعات "
        "- مع تنبيهات مجاناً لجوالك وسيرة ذاتية PDF عبر بوت ملهم."
    ).format(label=label, count=count)
    if not count:
        intro = (
            "لا توجد فرصة {label} مدرجة حالياً - الصفحة تتجدد تلقائياً كل 6 ساعات فور "
            "نزول وظيفة مناسبة، وتلقى تنبيهاً فوراً عبر بوت ملهم."
        ).format(label=label)
    jsonld = json.dumps(
        {
            "@context": "https://schema.org",
            "@type": "CollectionPage",
            "name": "وظائف {l}".format(l=label),
            "url": "{base}/{c}-{p}.html".format(base=SITE_URL, c=city_slug, p=prof_slug),
            "inLanguage": "ar",
            "isPartOf": {"@type": "WebSite", "name": "مهن", "url": SITE_URL + "/"},
            "mainEntity": {
                "@type": "ItemList",
                "numberOfItems": count,
                "itemListElement": [
                    _job_jsonld(j, i + 1, city_name) for i, j in enumerate(combo[:15])
                ],
            },
        },
        ensure_ascii=False,
    )
    return COMBO_PAGE.format(
        site_url=SITE_URL,
        gsc_meta=_gsc_meta(),
        slug="{c}-{p}".format(c=city_slug, p=prof_slug),
        prof=prof_name,
        city=city_name,
        count_badge=count_badge,
        desc_jobs=desc_jobs,
        year=datetime.now().year,
        style=STYLE,
        prof_chips=_prof_chips_for_city(city_slug, city_name),
        city_chips=_city_chips_for_prof(prof_slug),
        bot_jobs=BOT_JOBS,
        bot_company=BOT_COMPANY,
        bot_link=BOT_LINK,
        bot_username=BOT_USERNAME,
        intro=intro,
        jobs_n=count,
        jobs_cards="\n".join(_card(j, "مطابق للتخصص والمدينة") for j in combo)
        or "<p>ماكو وظيفة {p} بـ{c} حالياً - راقب هذي الصفحة، تتحدث لحالها.".format(
            p=prof_name, c=city_name
        ),
        other_n=len(other),
        other_badge=_badge(len(other)),
        other_cards="\n".join(_card(j, "تغطي العراق") for j in other[:6])
        or "<p>لا توجد وظائف {p} مدرجة حالياً بكل العراق.</p>".format(p=prof_name),
        city_url="{base}/{slug}.html".format(base=SITE_URL, slug=city_slug),
        prof_url="{base}/{slug}.html".format(base=SITE_URL, slug=prof_slug),
        jsonld=jsonld,
        now=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )


def build_combo_files():
    files = {}
    for cslug, cname, aliases in CITY_PAGES:
        for pslug, pname, terms in PROF_PAGES:
            slug = "{c}-{p}".format(c=cslug, p=pslug)
            files[slug + ".html"] = build_combo_page(
                cslug, cname, aliases, pslug, pname, terms
            )
    return files


def build_weekly_article():
    local = _local_jobs()
    feed_jobs = _feed_jobs()
    base = local + feed_jobs
    prof_counts = []
    for slug, name, terms in PROF_PAGES:
        prof_counts.append((sum(1 for j in base if _matches_prof(j, terms)), slug, name))
    prof_counts.sort(reverse=True)
    city_counts = []
    for slug, name, aliases in CITY_PAGES:
        city_counts.append(
            (sum(1 for j in base if _in_city(j.get("city"), aliases)), slug, name)
        )
    city_counts.sort(reverse=True)
    slug = week_slug()
    today = datetime.now()
    iso = today.isocalendar()
    title = "أكثر الوظائف طلباً في العراق - الأسبوع {y}-W{w:02d}".format(
        y=iso[0], w=iso[1]
    )
    description = (
        "تقرير أسبوعي عن أكثر التخصصات والمحافظات طلباً على الوظائف في العراق "
        "({date}) - مولّد تلقائياً من بيانات ملهم."
    ).format(date=today.strftime("%Y-%m-%d"))
    intro = (
        "هذا التقرير يعتمد على {n} وظيفة منشورة على ملهم هذا الأسبوع: أكثر التخصصات "
        "طلباً وأكثر المحافظات نشاطاً، مع روابط مباشرة لكل صفحة تخصص."
    ).format(n=len(base))

    def prof_lines(counts):
        out = []
        for count, pslug, pname in counts[:8]:
            if count <= 0:
                continue
            out.append(
                '<div class="card"><h2><a href="{s}.html">وظائف {n}</a> — {c} فرصة</h2></div>'.format(
                    s=pslug, n=html.escape(pname), c=count
                )
            )
        return "".join(out) or "<p>ماكو بيانات كافية هالأسبوع - تابعنا.</p>"

    def city_lines(counts):
        out = []
        for count, cslug, cname in counts[:6]:
            if count <= 0:
                continue
            out.append(
                '<div class="card"><h2><a href="{s}.html">وظائف {n}</a> — {c} فرصة</h2></div>'.format(
                    s=cslug, n=html.escape(cname), c=count
                )
            )
        return "".join(out) or "<p>ماكو بيانات كافية هالأسبوع - تابعنا.</p>"

    jsonld = json.dumps(
        {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": title,
            "datePublished": today.strftime("%Y-%m-%d"),
            "inLanguage": "ar",
            "publisher": {"@type": "Organization", "name": "مهن"},
            "url": "{base}/{s}.html".format(base=SITE_URL, s=slug),
        },
        ensure_ascii=False,
    )
    return ARTICLE_PAGE.format(
        site_url=SITE_URL,
        gsc_meta=_gsc_meta(),
        slug=slug,
        title=title,
        description=description,
        intro=intro,
        style=STYLE,
        prof_cards=prof_lines(prof_counts),
        city_cards=city_lines(city_counts),
        bot_jobs=BOT_JOBS,
        bot_company=BOT_COMPANY,
        bot_link=BOT_LINK,
        bot_username=BOT_USERNAME,
        jsonld=jsonld,
        now=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )


def build_sitemap():
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        "<url><loc>{base}/</loc><lastmod>{d}</lastmod>"
        "<changefreq>daily</changefreq><priority>1.0</priority></url>".format(
            base=SITE_URL, d=today
        ),
    ]
    for slug, name, _ in CITY_PAGES:
        lines.append(
            "<url><loc>{base}/{slug}.html</loc><lastmod>{d}</lastmod>"
            "<changefreq>daily</changefreq><priority>0.8</priority></url>".format(
                base=SITE_URL, slug=slug, d=today
            )
        )
    for slug, name, _ in PROF_PAGES:
        lines.append(
            "<url><loc>{base}/{slug}.html</loc><lastmod>{d}</lastmod>"
            "<changefreq>daily</changefreq><priority>0.7</priority></url>".format(
                base=SITE_URL, slug=slug, d=today
            )
        )
    for slug in _combo_slugs():
        lines.append(
            "<url><loc>{base}/{slug}.html</loc><lastmod>{d}</lastmod>"
            "<changefreq>daily</changefreq><priority>0.6</priority></url>".format(
                base=SITE_URL, slug=slug, d=today
            )
        )
    for week_file in sorted(SITE_REPO_DIR.glob("week-*.html")):
        lines.append(
            "<url><loc>{base}/{name}</loc><lastmod>{d}</lastmod>"
            "<changefreq>weekly</changefreq><priority>0.5</priority></url>".format(
                base=SITE_URL, name=week_file.name, d=today
            )
        )
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


def build_robots():
    return (
        "User-agent: *\nAllow: /\n\n"
        "Sitemap: {base}/sitemap.xml\n".format(base=SITE_URL)
    )


def _indexnow_urls():
    urls = [SITE_URL + "/"] + [
        SITE_URL + "/" + slug + ".html" for slug, _, _ in CITY_PAGES
    ] + [SITE_URL + "/" + slug + ".html" for slug, _, _ in PROF_PAGES]
    urls += [SITE_URL + "/" + slug + ".html" for slug in _combo_slugs()]
    urls += [SITE_URL + "/" + f.name for f in sorted(SITE_REPO_DIR.glob("week-*.html"))]
    return urls


def submit_indexnow(urls=None):
    import urllib.request

    payload = json.dumps(
        {
            "host": "sfyanbd36-svg.github.io",
            "key": INDEXNOW_KEY,
            "keyLocation": SITE_URL + "/" + INDEXNOW_KEY_FILE,
            "urlList": urls or _indexnow_urls(),
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        INDEXNOW_ENDPOINT,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status in (200, 202)
    except Exception as exc:
        print("indexnow failed:", exc)
        return False


def _git(*args, cwd):
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=60,
    )


def ensure_repo():
    if not (SITE_REPO_DIR / ".git").exists():
        SITE_REPO_DIR.parent.mkdir(parents=True, exist_ok=True)
        r = _git("clone", REPO_REMOTE, str(SITE_REPO_DIR), cwd=SITE_REPO_DIR.parent)
        if r.returncode != 0:
            return False, r.stderr.strip()
    return True, ""


def publish_site():
    ok, err = ensure_repo()
    if not ok:
        return "clone failed: " + err
    written = []
    week_file = week_slug() + ".html"
    (SITE_REPO_DIR / week_file).write_text(build_weekly_article(), encoding="utf-8")
    written.append(week_file)
    written.append("index.html")
    SITE_INDEX.write_text(build_page(), encoding="utf-8")
    for filename, content in build_city_files().items():
        (SITE_REPO_DIR / filename).write_text(content, encoding="utf-8")
        written.append(filename)
    for filename, content in build_prof_files().items():
        (SITE_REPO_DIR / filename).write_text(content, encoding="utf-8")
        written.append(filename)
    for filename, content in build_combo_files().items():
        (SITE_REPO_DIR / filename).write_text(content, encoding="utf-8")
        written.append(filename)
    (SITE_REPO_DIR / "sitemap.xml").write_text(build_sitemap(), encoding="utf-8")
    (SITE_REPO_DIR / "robots.txt").write_text(build_robots(), encoding="utf-8")
    (SITE_REPO_DIR / INDEXNOW_KEY_FILE).write_text(INDEXNOW_KEY, encoding="utf-8")
    written += ["sitemap.xml", "robots.txt", INDEXNOW_KEY_FILE]
    qr_src = Path(__file__).resolve().parent / "marketing" / "qr.png"
    qr_dst = SITE_REPO_DIR / "qr.png"
    if qr_src.exists():
        qr_dst.write_bytes(qr_src.read_bytes())
    _git("add", *written, cwd=SITE_REPO_DIR)
    if qr_src.exists():
        _git("add", "qr.png", cwd=SITE_REPO_DIR)
    status = _git("status", "--porcelain", cwd=SITE_REPO_DIR)
    if not status.stdout.strip():
        return "no changes"
    _git("-c", "user.name=mulhim-bot", "-c", "user.email=sfyanbd36@gmail.com",
         "commit", "-m", "Update jobs site " + datetime.now().isoformat(timespec="seconds"),
         cwd=SITE_REPO_DIR)
    push = _git("push", "origin", "HEAD", cwd=SITE_REPO_DIR)
    if push.returncode != 0:
        return "push failed: " + push.stderr.strip()
    submitted = submit_indexnow()
    return "published" + ("" if submitted else " (indexnow delayed)")


if __name__ == "__main__":
    print(publish_site())
