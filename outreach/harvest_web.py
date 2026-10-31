import csv
import json
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUTREACH = Path(__file__).resolve().parent
OUT_CSV = OUTREACH / "companies_web.csv"
SENT_LOG = OUTREACH / "sent.csv"

try:
    from sectors import is_iraq
except ImportError:
    from outreach.sectors import is_iraq

API = "https://ijobsiq.com/api/jobs?page={p}&limit=200"

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
BAD_TLDS = {"png", "jpg", "jpeg", "gif", "webp", "svg", "css", "js", "html", "php", "xml", "json", "md", "txt", "pdf", "w3"}
BAD_DOMAINS = (
    "example.", "w3.org", "schema.org", "googleapis", "gstatic", "blogger.com",
    "feedburner", "sentry", "localhost", "wordpress", "lnkd.in", "t.me",
    "telegram.me", "iraqi-jobs.com", "ijobsiq.com", "bayanjo", "joblist",
    "indeed.", "glassdoor.", "linkedin.com", "naukri", "careerjet", "bayt.com",
)

WEB_ROLE = re.compile(
    r"\bweb\b|website|web[\s-]?(?:design|develop|site)|front[\s-]?end|back[\s-]?end|"
    r"full[\s-]?stack|next\.?js|react(?:\.js| native)?|wordpress|shopify|wix|laravel|"
    r"flutter|ui[\s-]?ux|e-?commerce|cms|software|programmer|programming|developer|"
    r"mobile (?:app|application)|\bit\b|network|data(?:base)?|cloud|erp|crm|digital|"
    r"برمجيات|برمجة|مطور|تطوير|ويب|مواقع|موقع|واجهات|واجهة|تطبيقات|تطبيق|"
    r"تقنية معلومات|معلوماتية|شبكات|قواعد بيانات|رقمنة|رقمي",
    re.IGNORECASE,
)

SALES_ROLE = re.compile(
    r"sales|marketing|تسويق|مبيعات|consultant|مستشار|account|financial|محاسب|cashier|كاشير",
    re.IGNORECASE,
)

CUTOFF_DAYS = 21
MAX_PAGES = 20


def clean_email(raw):
    email = raw.strip().strip(".,;:()<>\"'").lower()
    if "@" not in email or ".." in email:
        return None
    domain = email.split("@", 1)[1]
    if domain.endswith(tuple(BAD_TLDS)):
        return None
    if any(bad in domain for bad in BAD_DOMAINS):
        return None
    return email


def fetch(page):
    req = urllib.request.Request(API.format(p=page), headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=40) as resp:
        return json.load(resp)


def already_sent():
    if not SENT_LOG.exists():
        return set()
    with SENT_LOG.open(encoding="utf-8", newline="") as handle:
        return {r["email"].strip().lower() for r in csv.DictReader(handle)}


def harvest(cutoff, skip=None):
    skip = skip or set()
    rows, seen = [], set()
    cutoff = datetime.fromisoformat(cutoff).replace(tzinfo=timezone.utc) if isinstance(cutoff, str) else cutoff

    for page in range(1, MAX_PAGES + 1):
        try:
            data = fetch(page)
        except Exception as exc:
            print("page {p} error: {e}".format(p=page, e=exc), file=sys.stderr)
            break
        jobs = data.get("jobs") or []
        if not jobs:
            break
        for job in jobs:
            title = re.sub(r"\[cite:\s*\d+\]", "", str(job.get("title") or ""))
            title = re.sub(r"[^\w\s\u0600-\u06FF./+-]", " ", title)
            title = " ".join(title.split())[:120]
            loc = (job.get("location") or "").lower()
            blob = " ".join(str(job.get(k) or "") for k in ("title", "description", "requirements", "category", "company", "location"))
            if not title or not WEB_ROLE.search(title):
                continue
            if SALES_ROLE.search(title):
                continue
            if not is_iraq("{loc} {blob}".format(loc=loc, blob=blob)):
                continue
            created = job.get("createdAt") or ""
            if created:
                try:
                    posted = datetime.fromisoformat(created.replace("Z", "+00:00"))
                    if posted.tzinfo is None:
                        posted = posted.replace(tzinfo=timezone.utc)
                    if posted < cutoff:
                        continue
                except (ValueError, TypeError):
                    pass
            for raw in EMAIL_RE.findall(blob):
                email = clean_email(raw)
                if not email or email in seen or email in skip:
                    continue
                seen.add(email)
                rows.append({
                    "email": email,
                    "company": (job.get("company") or "").strip() or "Not specified",
                    "roles": title[:120],
                    "source": "ijobsiq.com/jobs/{id}".format(id=job.get("id")),
                    "posted": (created or "")[:10],
                })
        if len(rows) >= 60:
            break
    rows.sort(key=lambda r: r["posted"], reverse=True)
    return rows


def main():
    rows = harvest(datetime.now(timezone.utc) - timedelta(days=CUTOFF_DAYS), skip=already_sent())
    with OUT_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["email", "company", "roles", "source", "posted"])
        writer.writeheader()
        writer.writerows(rows)
    print("matched={m} -> {f}".format(m=len(rows), f=OUT_CSV))


if __name__ == "__main__":
    main()
