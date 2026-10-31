import argparse
import csv
import json
import re
import sys
import time
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

try:
    from send_auto import already_sent, load_env, log_sent, notify, send_one
except ImportError:
    from outreach.send_auto import already_sent, load_env, log_sent, notify, send_one

try:
    from sectors import SITE_SUBJECT, bot_template_for, is_free_mail, is_iraq
except ImportError:
    from outreach.sectors import SITE_SUBJECT, bot_template_for, is_free_mail, is_iraq

try:
    from harvest_osm import leads as osm_leads
except ImportError:
    from outreach.harvest_osm import leads as osm_leads

try:
    from harvest_web import SALES_ROLE, WEB_ROLE as TECH_ROLE
except Exception:
    TECH_ROLE = re.compile(r"software|developer|programmer|\bit\b|network|digital|برمج|مطور|تطوير|تقنية", re.IGNORECASE)
    SALES_ROLE = re.compile(r"sales|marketing|تسويق|مبيعات", re.IGNORECASE)

OUTREACH = Path(__file__).resolve().parent
BASE = OUTREACH.parent
COMPANIES_CSV = OUTREACH / "companies.csv"
TEMPLATE_FILE = OUTREACH / "email_template.txt"
RUN_LOG = OUTREACH / "auto.log"

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
BAD_TLDS = {
    "png", "jpg", "jpeg", "gif", "webp", "svg", "css", "js", "html",
    "php", "xml", "json", "md", "txt", "pdf", "com/tr", "w3",
}
BAD_DOMAINS = (
    "example.", "w3.org", "schema.org", "googleapis", "gstatic",
    "blogger.com", "feedburner", "sentry", "localhost", "wordpress",
    "iraqi-jobs.com", "ijobsiq.com", "bayanjo", "joblist", "careerjet",
    "indeed.", "glassdoor.", "linkedin.com", "bayt.com", "naukri",
    "lnkd.in", "t.me", "telegram.me",
)
CUTOFF_DAYS = 14
SITE_CUTOFF_DAYS = 30
SITE_MANUAL_CSV = OUTREACH / "companies_baghdad.csv"
MAX_PAGES = 14
MAX_FEED_POSTS = 150


def log(msg):
    line = "{ts} {msg}".format(ts=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg=msg)
    with RUN_LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    print(line)


def clean_email(raw):
    email = raw.strip().strip(".,;:()<>").lower()
    if "@" not in email or ".." in email:
        return None
    domain = email.split("@", 1)[1]
    local = email.split("@", 1)[0]
    if domain.endswith(tuple(BAD_TLDS)):
        return None
    if any(bad in domain for bad in BAD_DOMAINS):
        return None
    if local.startswith("jobsiq") or "ijobs" in local or local.startswith("noreply"):
        return None
    return email


def http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


FREE_MAIL = ("gmail.com", "yahoo.", "hotmail.", "outlook.", "icloud.com", "proton")
EMAIL_PREFIX_PRIORITY = (
    "hr", "info", "careers", "career", "recruitment", "jobs", "job",
    "apply", "contact", "hiring",
)


def derive_company(email, fallback):
    name = (fallback or "").strip()
    if name and name.lower() not in ("not specified", "n/a", "none", "-"):
        return name
    domain = email.split("@", 1)[1]
    if any(domain.startswith(p) or domain == p for p in FREE_MAIL):
        return ""
    label = domain.split(".", 1)[0].replace("-", " ").replace("_", " ").strip()
    return " ".join(word.capitalize() for word in label.split()) or ""


def best_per_domain(rows):
    picked = {}
    for row in rows:
        domain = row["email"].split("@", 1)[1]
        local = row["email"].split("@", 1)[0]
        key = row["email"] if is_free_mail(domain) else domain
        rank = (
            0 if local in EMAIL_PREFIX_PRIORITY else 1,
            len(local),
        )
        current = picked.get(key)
        if current is None or rank < current[0]:
            picked[key] = (rank, row)
    return [value[1] for value in picked.values()]


def harvest_ijobs(cutoff):
    found = {}
    for page in range(1, MAX_PAGES + 1):
        try:
            data = http_json(
                "https://ijobsiq.com/api/jobs?page={p}&limit=100".format(p=page)
            )
        except Exception as exc:
            log("ijobs page {p} error: {e}".format(p=page, e=exc))
            break
        jobs = data.get("jobs") or []
        if not jobs:
            break
        stale_on_page = 0
        for job in jobs:
            created = (job.get("createdAt") or "")[:10]
            posted = datetime.strptime(created, "%Y-%m-%d").date() if created else None
            if posted and posted < cutoff:
                stale_on_page += 1
                continue
            for raw in EMAIL_RE.findall(
                (job.get("description") or "") + " " + (job.get("title") or "")
            ):
                email = clean_email(raw)
                if not email:
                    continue
                entry = found.setdefault(
                    email,
                    {
                        "email": email,
                        "company": derive_company(email, job.get("company"))
                        or (job.get("title") or "").strip()
                        or "شركة عراقية",
                        "roles": [],
                        "source": "ijobsiq.com/jobs/{id}".format(id=job.get("id")),
                        "posted": created,
                        "loc": (job.get("location") or ""),
                    },
                )
                title = (job.get("title") or "").strip()
                if title and title not in entry["roles"] and len(entry["roles"]) < 6:
                    entry["roles"].append(title)
        if stale_on_page >= 50:
            break
        time.sleep(0.4)
    return list(found.values())


def strip_html(text):
    text = re.sub(r"<[^>]+>", " ", text or "")
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    return re.sub(r"\s+", " ", text).strip()


def harvest_arkadu(cutoff):
    found = {}
    try:
        data = http_json(
            "https://www.arkadu-iq.org/feeds/posts/default?alt=json&max-results={n}".format(
                n=MAX_FEED_POSTS
            )
        )
    except Exception as exc:
        log("arkadu feed error: {e}".format(e=exc))
        return []
    for post in data.get("feed", {}).get("entry", []):
        published = (post.get("published", {}).get("$t") or "")[:10]
        try:
            posted = datetime.strptime(published, "%Y-%m-%d").date()
        except ValueError:
            posted = None
        if posted and posted < cutoff:
            continue
        title = strip_html(post.get("title", {}).get("$t", ""))[:120]
        content = strip_html(
            (post.get("content") or post.get("summary") or {}).get("$t", "")
        )
        company_match = re.search(r"اسم\s*الشركة\s+([^\u2022|.|،,]{2,70})", content)
        company = strip_html(company_match.group(1)) if company_match else title
        for raw in EMAIL_RE.findall(content):
            email = clean_email(raw)
            if not email:
                continue
            entry = found.setdefault(
                email,
                {
                    "email": email,
                    "company": company,
                    "roles": [],
                    "source": "arkadu-iq.org",
                    "posted": published,
                },
            )
            if title and title not in entry["roles"] and len(entry["roles"]) < 6:
                entry["roles"].append(title)
    return list(found.values())


def known_emails(paths):
    known = already_sent()
    for path in paths:
        if path.exists():
            with path.open(encoding="utf-8", newline="") as handle:
                known |= {row["email"].strip().lower() for row in csv.DictReader(handle)}
    return known


def append_companies(rows):
    if not rows:
        return
    ready = COMPANIES_CSV.exists() and COMPANIES_CSV.stat().st_size > 0
    with COMPANIES_CSV.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        if not ready:
            writer.writerow(["email", "company", "roles", "source", "posted"])
        for row in rows:
            roles_value = row["roles"]
            if not isinstance(roles_value, str):
                roles_value = "، ".join(roles_value)
            writer.writerow(
                [
                    row["email"],
                    row["company"],
                    roles_value or "وظائف متنوعة",
                    row["source"],
                    row["posted"],
                ]
            )


def sent_today_count():
    sent_path = OUTREACH / "sent.csv"
    if not sent_path.exists():
        return 0
    today = date.today().isoformat()
    count = 0
    with sent_path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if (row.get("sent_at") or "").startswith(today):
                count += 1
    return count


def pending_rows(sent_before):
    with COMPANIES_CSV.open(encoding="utf-8", newline="") as handle:
        return [
            row
            for row in csv.DictReader(handle)
            if row["email"].strip().lower() not in sent_before
        ]


def run_campaign(campaign, cap_run, cap_daily, cutoff, search_only):
    global COMPANIES_CSV, TEMPLATE_FILE

    COMPANIES_CSV = OUTREACH / (
        "companies_web.csv" if campaign == "site" else "companies.csv"
    )
    TEMPLATE_FILE = OUTREACH / (
        "email_template_site.txt" if campaign == "site" else "email_template.txt"
    )

    if campaign == "site":
        cutoff = date.today() - timedelta(days=SITE_CUTOFF_DAYS)

    leads = harvest_ijobs(cutoff) + harvest_arkadu(cutoff)
    if campaign == "bot":
        try:
            leads = leads + osm_leads()
        except Exception as exc:
            log("osm harvest error: {e}".format(e=str(exc)[:160]))
    if campaign == "site":
        picked = []
        for row in leads:
            text = " ".join(row["roles"])
            where = " ".join([text, row.get("company") or "", row.get("loc") or ""])
            if not text:
                continue
            if not is_iraq(where):
                continue
            picked.append(row)
        if SITE_MANUAL_CSV.exists():
            with SITE_MANUAL_CSV.open(encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    email = (row.get("email") or "").strip().lower()
                    if "@" not in email:
                        continue
                    picked.append(
                        {
                            "email": email,
                            "company": (row.get("company") or "").strip(),
                            "roles": [(row.get("roles") or "شركة بغداد").strip()],
                            "source": (row.get("source") or "manual").strip(),
                            "posted": (row.get("posted") or "")[:10],
                            "loc": "Baghdad",
                        }
                    )
        leads = picked
    leads = best_per_domain(leads)
    site_queue = OUTREACH / "companies_web.csv"
    bot_queue = OUTREACH / "companies.csv"
    known = known_emails([site_queue] if campaign == "site" else [bot_queue, site_queue])
    fresh = [row for row in leads if row["email"] not in known]
    append_companies(fresh)
    log(
        "search[{campaign}]: scanned={s} fresh={f} (ijobs+arkadu, cutoff {c})".format(
            campaign=campaign, s=len(leads), f=len(fresh), c=cutoff.isoformat()
        )
    )
    for row in fresh:
        log("  + {email} | {company}".format(email=row["email"], company=row["company"]))

    if search_only:
        return len(fresh)

    sent_before = already_sent()
    pending = pending_rows(sent_before)
    already_today = sent_today_count()
    budget = min(cap_run, max(0, cap_daily - already_today))

    done = 0
    failed = 0
    template = TEMPLATE_FILE.read_text(encoding="utf-8")
    template_cache = {TEMPLATE_FILE: template}
    for row in pending[:budget]:
        if campaign == "site":
            tpl = template
            subject = SITE_SUBJECT + " | " + row["company"]
        else:
            tpl_path, subject_prefix = bot_template_for(row["roles"])
            if tpl_path not in template_cache:
                template_cache[tpl_path] = tpl_path.read_text(encoding="utf-8")
            tpl = template_cache[tpl_path]
            subject = subject_prefix + " - " + row["company"]
        body = tpl.format(roles=row["roles"], company=row["company"])
        body = body.replace("[اسمك]", "سفيان").strip()
        ok, err = send_one(row["email"], subject, body)
        if ok:
            log_sent(row["email"], row["company"])
            done += 1
            notify(
                "تم الارسال [{campaign}] - {company} <{email}>".format(
                    campaign=campaign, company=row["company"], email=row["email"]
                )
            )
        else:
            failed += 1
            log("send failed: {email} | {err}".format(email=row["email"], err=err[:180]))
            notify(
                "فشل الارسال [{campaign}] لـ {company}: {err}".format(
                    campaign=campaign, company=row["company"], err=err[:180]
                )
            )
        time.sleep(2)

    summary = (
        "روتين تلقائي [{campaign}]: بحث +{fresh} جديد | ارسال {done} (فشل {failed}) | "
        "اليوم {t}/{cap} | مجموع الانتظار {pend}"
    ).format(
        campaign=campaign,
        fresh=len(fresh),
        done=done,
        failed=failed,
        t=already_today + done,
        cap=cap_daily,
        pend=max(0, len(pending) - budget),
    )
    log(summary)
    notify(summary)
    return len(fresh)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--search-only", action="store_true")
    parser.add_argument("--max", type=int, default=0, help="max sends this run")
    parser.add_argument("--campaign", choices=("bot", "site", "both"), default="both")
    args = parser.parse_args()

    load_env()
    import os

    cap_run = args.max or int(os.environ.get("OUTREACH_MAX_PER_RUN", "6"))
    cap_daily = int(os.environ.get("OUTREACH_DAILY_CAP", "12"))
    cutoff = date.today() - timedelta(days=CUTOFF_DAYS)

    campaigns = ("site", "bot") if args.campaign == "both" else (args.campaign,)
    for campaign in campaigns:
        run_campaign(campaign, cap_run, cap_daily, cutoff, args.search_only)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log("FATAL: {e}".format(e=exc))
        try:
            notify("روتين outreach طاح بخطأ: {e}".format(e=str(exc)[:180]))
        except Exception:
            pass
        sys.exit(1)
