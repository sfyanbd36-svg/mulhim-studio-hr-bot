from datetime import datetime
from urllib.parse import quote

import storage

BOT_LINK = "https://t.me/mulhimstudio_hr_bot?start=jobs"
SITE_URL = "https://sfyanbd36-svg.github.io/mulhim-jobs/"
MAX_ITEMS = 10


def _local_jobs(limit):
    rows = [
        r
        for r in storage.read_table("company_jobs")
        if str(r.get("active", "1")) == "1" and (r.get("title") or "").strip()
    ]
    rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    companies = {
        str(c.get("company_id", "")): c for c in storage.read_table("companies")
    }
    out = []
    for row in rows[:limit]:
        company = companies.get(str(row.get("company_id", "")), {})
        out.append(
            {
                "title": row.get("title", ""),
                "company": company.get("name", "") or "-",
                "city": "",
                "url": "",
            }
        )
    return out


def _feed_jobs(limit):
    rows = sorted(
        storage.read_table("feed_jobs"),
        key=lambda r: r.get("posted") or "",
        reverse=True,
    )
    out = []
    for row in rows[:limit]:
        out.append(
            {
                "title": row.get("title", ""),
                "company": row.get("company", "") or "-",
                "city": row.get("city", "") or "-",
                "url": row.get("url", ""),
            }
        )
    return out


def build_digest():
    local = _local_jobs(5)
    feed = _feed_jobs(MAX_ITEMS - len(local))
    today = datetime.now().strftime("%Y-%m-%d")
    lines = ["نشرة الوظائف اليومية - " + today, ""]
    index = 0
    for job in local:
        index += 1
        lines.append(
            "{i}. {title} - {company}{city}".format(
                i=index,
                title=job["title"][:90],
                company=job["company"],
                city=(" | " + job["city"]) if job["city"] and job["city"] != "-" else "",
            )
        )
    for job in feed:
        index += 1
        lines.append(
            "{i}. {title} - {company}{city}".format(
                i=index,
                title=job["title"][:90],
                company=job["company"],
                city=(" | " + job["city"]) if job["city"] and job["city"] != "-" else "",
            )
        )
        if job["url"]:
            lines.append(job["url"])
    if not index:
        return ""
    lines += [
        "",
        "المزيد وسيرة ذاتية PDF مجاناً: " + BOT_LINK,
        "الموقع: " + SITE_URL,
    ]
    return "\n".join(lines)


def build_share_text():
    return quote("نشرة وظائف العراق اليومية من ملهم - اشترك وتابع الجديد: " + BOT_LINK)


def build_status_text():
    items = (_local_jobs(3) + _feed_jobs(3))[:6]
    if not items:
        return ""
    today = datetime.now().strftime("%Y-%m-%d")
    lines = ["وظائف العراق - " + today, ""]
    for index, job in enumerate(items, start=1):
        city = job.get("city") or ""
        lines.append(
            "{i}. {title} - {company}{city}".format(
                i=index,
                title=job["title"][:70],
                company=job["company"],
                city=(" | " + city) if city and city != "-" else "",
            )
        )
    lines += [
        "",
        "سيرة PDF مجاناً وتنبيهات وظائف: " + BOT_LINK,
    ]
    return "\n".join(lines)
