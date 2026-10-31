import asyncio
import importlib.util
import os
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

import httpx

IAQ_UTC = timezone.utc
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
GENERIC_CITIES = {
    "",
    "-",
    "iraq",
    "remote",
    "not specified",
    "not mentioned",
    "not specified / not mentioned in the post text but implied as standard salary structure of the compa",
    "worldwide",
    "middle east",
}
OSQ_LIST_URL = "https://iq.opensooq.com/en/jobs/job-vacancies"
RW_RSS_URL = "https://reliefweb.int/jobs/rss.xml?search=Iraq"
TG_CHANNELS = ("IJobsIQ",)

CITY_ALIASES = {
    "بغداد": ["بغداد", "baghdad"],
    "البصرة": ["البصرة", "basra"],
    "أربيل": ["أربيل", "اربيل", "erbil", "arbil", "hawler"],
    "الموصل": ["الموصل", "موصل", "mosul", "ninawa"],
    "النجف": ["النجف", "najaf"],
    "كربلاء": ["كربلاء", "karbala"],
    "السليمانية": ["السليمانية", "سليمانية", "sulaymaniyah", "slemani"],
    "كركوك": ["كركوك", "kerbuk", "kirkuk"],
    "بابل": ["بابل", "babylon", "hillah"],
    "ديالى": ["ديالى", "دياله", "diyala", "baaquba"],
    "ميسان": ["ميسان", "maysan", "amara"],
    "ذي قار": ["ذي قار", "ذيقار", "dhi qar", "nasiriyah"],
    "الأنبار": ["الأنبار", "انبار", "anbar", "ramadi", "fallujah"],
    "صلاح الدين": ["صلاح الدين", "saladin", "tikrit", "tikrit"],
    "واسط": ["واسط", "wasit", "kut"],
    "الديوانية": ["الديوانية", "ديوانية", "diwaniya", "kafaf"],
    "ال Kut": ["kut"],
}

SKILL_ALIASES = {
    "محاسب": ["account", "accountant", "accounting", "finance", "مالية"],
    "محاسبة": ["account", "accountant", "accounting", "finance", "مالية"],
    "مهندس": ["engineer", "engineering", "مهندس"],
    "برمجة": ["developer", "programmer", "software", "engineering", "مطور"],
    "مبرمج": ["developer", "programmer", "software", "coder"],
    "مطور": ["developer", "programmer", "software"],
    "تصميم": ["design", "designer", "graphic", "ui ", "ux ", "تصميم"],
    "تسويق": ["marketing", "تسويق"],
    "مبيعات": ["sales", "sell", "commercial", "مبيعات"],
    "موارد بشرية": ["human resource", "recruitment", "hr ", "موارد"],
    "موارد": ["human resource", "recruitment", "hr "],
    "شبكات": ["network", "cisco", "it infrastructure", "شبكات"],
    "شبكة": ["network", "cisco", "شبكات"],
    "بيانات": ["data", "analytics", "database", "بيانات"],
    "معلم": ["teacher", "instructor", "lecturer", "معلم", "تدريس"],
    "تدريس": ["teacher", "instructor", "teach", "تدريس"],
    "سائق": ["driver", "سائق"],
    "ممرض": ["nurse", "nursing", "medical", "ممرض", "تمريض"],
    "تمريض": ["nurse", "nursing", "تمريض"],
    "قانون": ["legal", "law", "lawyer", "قانون"],
    "لوجستي": ["logistic", "warehouse", "supply", "لوجست"],
    "مخزون": ["warehouse", "inventory", "مخزن", "مخزون"],
    "خدمة عملاء": ["customer service", "call center", "دعم فني"],
    "دعم فني": ["technical support", "it support", "helpdesk"],
    "ميكانيكا": ["mechanic", "maintenance", "ميكانيك"],
    "كهرباء": ["electric", "electrical", "كهرباء"],
    "بناء": ["construction", "civil", "بناء"],
    "فني": ["technician", "technical", "فني"],
    "إداري": ["admin", "administration", "secretary", "إدار"],
    "اداري": ["admin", "administration", "secretary", "إدار"],
    "مدير": ["manager", "supervisor", "head of", "مدير"],
    "مندوب": ["representative", "promotion", "مندوب"],
    "شيف": ["chef", "cook", "شيف"],
}

STOPWORDS = {"و", "في", "من", "على", "الى", "إلى", "عن", "مع", "او", "أو", "a", "an", "the", "ل", "يا"}


def normalize(text):
    text = (text or "").lower()
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ى", "ي").replace("ة", "ه")
    return re.sub(r"[^0-9a-z؀-ۿ\s]", " ", text)


def normalize_title(title):
    return re.sub(r"\s+", " ", normalize(title)).strip()[:70]


def infer_city(*texts):
    joined = " ".join(t or "" for t in texts)
    low = joined.lower()
    for canonical, variants in CITY_ALIASES.items():
        for variant in variants:
            vl = variant.lower()
            if re.search(r"[a-z]", vl):
                if re.search(r"\b" + re.escape(vl) + r"\b", low):
                    return canonical
            elif variant and variant in joined:
                return canonical
    return ""


def resolve_city(city, *fallback_texts):
    cleaned = (city or "").strip()
    if cleaned.lower().rstrip(".") not in GENERIC_CITIES:
        return cleaned
    return infer_city(*fallback_texts) or cleaned


NORM_STOPWORDS = {normalize(word) for word in STOPWORDS}


def parse_keywords(raw):
    parts = re.split(r"[،,\n|/]+", raw or "")
    words = []
    for part in parts:
        for token in part.split():
            token = token.strip()
            if not token or len(token) < 2:
                continue
            if normalize(token) in NORM_STOPWORDS:
                continue
            words.append(token)
    seen = set()
    unique = []
    for word in words:
        key = normalize(word)
        if key not in seen:
            seen.add(key)
            unique.append(word)
    return unique


def city_terms(city):
    if not city:
        return []
    key = city.strip()
    for canonical, variants in CITY_ALIASES.items():
        if key == canonical or key in variants:
            return variants
    return [key]


def keyword_terms(keyword):
    key = keyword.strip()
    for table in (SKILL_ALIASES, CITY_ALIASES):
        if key in table:
            return table[key]
    if key.startswith("ال") and len(key) > 3:
        stem = key[2:]
        for table in (SKILL_ALIASES, CITY_ALIASES):
            if stem in table:
                return table[stem]
    return [key]


def _osq_posted_date(raw):
    try:
        if re.match(r"^\d{1,2}-\d{1,2}-\d{4}$", raw):
            day, month, year = raw.split("-")
            return "{y}-{m:02d}-{d:02d}".format(y=year, m=int(month), d=int(day))
        count = int(re.match(r"^(\d+)", raw).group(1))
        unit = re.search(r"minute|hour|day", raw).group(0)
        deltas = {"minute": {"minutes": count}, "hour": {"hours": count}, "day": {"days": count}}
        return (datetime.now(IAQ_UTC) - timedelta(**deltas[unit])).strftime("%Y-%m-%d")
    except Exception:
        return ""


def _parse_opensooq_list(html):
    jobs = []
    seen = set()
    pattern = re.compile(r'<a[^>]+href="(/en/job-posters/(\d+))"[^>]*>(.*?)</a>', re.S)
    for match in pattern.finditer(html):
        path, pid, inner = match.group(1), match.group(2), match.group(3)
        if pid in seen:
            continue
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", inner)).strip()
        if not text:
            continue
        head = text.split("Contract Type:")[0].strip()
        posted = ""
        stamp = re.match(
            r"^((?:\d+\s+(?:minute|hour|day)s?\s+ago)|\d{1,2}-\d{1,2}-\d{4})\s+",
            head,
        )
        if stamp:
            posted = _osq_posted_date(stamp.group(1))
            head = head[stamp.end():].strip()
        title = head.strip(" |·-")[:90].strip()
        if not title:
            continue
        seen.add(pid)
        emails = [e.lower() for e in EMAIL_RE.findall(text)]
        jobs.append(
            {
                "key": "osq-{pid}".format(pid=pid),
                "title": title,
                "company": "",
                "city": "",
                "text": text[:900],
                "source": "iq.opensooq.com",
                "url": "https://iq.opensooq.com" + path,
                "posted": posted or datetime.now(IAQ_UTC).strftime("%Y-%m-%d"),
                "apply": emails[0] if emails else "",
            }
        )
    return jobs


def fetch_opensooq(client, pages=3):
    jobs = []
    for page in range(1, pages + 1):
        url = OSQ_LIST_URL if page == 1 else "{u}?page={p}".format(u=OSQ_LIST_URL, p=page)
        try:
            html = client.get(url).text
        except Exception as exc:
            print("[opensooq] page {p}: {e}".format(p=page, e=exc))
            break
        found = _parse_opensooq_list(html)
        if not found:
            break
        jobs.extend(found)
    return jobs


def _parse_reliefweb_rss(xml_bytes):
    jobs = []
    try:
        root = ET.fromstring(xml_bytes)
    except Exception:
        return jobs
    for item in root.findall(".//item"):
        link = (item.findtext("link") or "").strip()
        id_match = re.search(r"/job/(\d+)", link)
        if not id_match:
            continue
        title = re.sub(r"\s+", " ", item.findtext("title") or "").strip()[:90]
        if not title:
            continue
        posted = ""
        try:
            posted = parsedate_to_datetime(item.findtext("pubDate") or "").date().isoformat()
        except Exception:
            posted = datetime.now(IAQ_UTC).strftime("%Y-%m-%d")
        company = (item.findtext("author") or "").strip()[:60]
        desc = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", item.findtext("description") or ""))
        emails = [e.lower() for e in EMAIL_RE.findall(desc)]
        jobs.append(
            {
                "key": "rw-{id}".format(id=id_match.group(1)),
                "title": title,
                "company": company,
                "city": "",
                "text": desc.strip()[:900],
                "source": "reliefweb.int",
                "url": link,
                "posted": posted,
                "apply": emails[0] if emails else "",
            }
        )
    return jobs


def fetch_reliefweb(client, pages=2):
    jobs = []
    for page in range(pages):
        url = RW_RSS_URL if page == 0 else "{u}&page={p}".format(u=RW_RSS_URL, p=page)
        try:
            payload = client.get(url).content
        except Exception as exc:
            print("[reliefweb] page {p}: {e}".format(p=page + 1, e=exc))
            break
        found = _parse_reliefweb_rss(payload)
        if not found:
            break
        jobs.extend(found)
    return jobs


def _tg_module():
    if getattr(_tg_module, "cached", None):
        return _tg_module.cached
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "userbot", "tg_client.py")
    spec = importlib.util.spec_from_file_location("mulhim_tg_client", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _tg_module.cached = module
    return module


async def fetch_tg_jobs(hours=48, limit_per_channel=25):
    jobs = []
    cutoff = datetime.now(IAQ_UTC) - timedelta(hours=hours)
    try:
        client = _tg_module()._client()
        await asyncio.wait_for(client.start(), timeout=30)
    except Exception as exc:
        print("[tg] login failed: {e}".format(e=exc))
        return jobs
    try:
        for channel in TG_CHANNELS:
            try:
                messages = await client.get_messages(channel, limit=limit_per_channel)
            except Exception as exc:
                print("[tg] {ch}: {e}".format(ch=channel, e=exc))
                continue
            for message in messages:
                text = (message.text or "").strip()
                if not text:
                    continue
                if message.date and message.date < cutoff:
                    break
                lines = [line.strip() for line in text.splitlines() if line.strip()]
                if not lines:
                    continue
                title = re.sub(r"[*_#`]", "", lines[0])
                title = re.sub(r"^[^0-9a-zA-Z؀-ۿ]+", "", title).strip()[:90]
                if not title:
                    continue
                emails = [e.lower() for e in EMAIL_RE.findall(text)]
                jobs.append(
                    {
                        "key": "tg-{ch}-{mid}".format(ch=channel, mid=message.id),
                        "title": title,
                        "company": "",
                        "city": "",
                        "text": re.sub(r"\s+", " ", text)[:900],
                        "source": "t.me/{ch}".format(ch=channel),
                        "url": "https://t.me/{ch}/{mid}".format(ch=channel, mid=message.id),
                        "posted": (message.date or datetime.now(IAQ_UTC)).date().isoformat(),
                        "apply": emails[0] if emails else "",
                    }
                )
    finally:
        await client.disconnect()
    return jobs


def fetch_fresh_jobs(hours=72, timeout=20.0):
    cutoff = datetime.now(IAQ_UTC) - timedelta(hours=hours)
    jobs = []
    seen = set()
    with httpx.Client(timeout=timeout, headers={"User-Agent": USER_AGENT}, follow_redirects=True) as client:
        for page in range(1, 5):
            try:
                data = client.get(
                    "https://ijobsiq.com/api/jobs?page={p}&limit=100".format(p=page)
                ).json()
            except Exception as exc:
                print("[ijobsiq] page {p}: {e}".format(p=page, e=exc))
                break
            rows = data.get("jobs") or []
            if not rows:
                break
            for row in rows:
                created = (row.get("createdAt") or "")[:10]
                try:
                    posted = datetime.strptime(created, "%Y-%m-%d").replace(tzinfo=IAQ_UTC)
                except ValueError:
                    posted = None
                if posted and posted < cutoff - timedelta(days=1):
                    continue
                text = "{t} {d}".format(t=row.get("title") or "", d=row.get("description") or "")
                emails = [e.lower() for e in EMAIL_RE.findall(row.get("description") or "")]
                job = {
                    "key": "ijq-{id}".format(id=row.get("id")),
                    "title": (row.get("title") or "").strip()[:90],
                    "company": (row.get("company") or "").strip()[:60],
                    "text": re.sub(r"\s+", " ", text)[:900],
                    "city": (row.get("location") or "").strip()[:60],
                    "source": "ijobsiq.com/jobs/{id}".format(id=row.get("id")),
                    "url": "https://ijobsiq.com/jobs/{id}".format(id=row.get("id")),
                    "posted": created,
                    "apply": emails[0] if emails else "",
                }
                if job["key"] not in seen and job["title"]:
                    seen.add(job["key"])
                    jobs.append(job)
            if len(rows) < 100:
                break
        try:
            feed = client.get(
                "https://www.arkadu-iq.org/feeds/posts/default?alt=json&max-results=40"
            ).json()
        except Exception as exc:
            print("[arkadu] {e}".format(e=exc))
            feed = {}
        for job in fetch_opensooq(client) + fetch_reliefweb(client):
            if job["key"] not in seen and job["title"]:
                seen.add(job["key"])
                jobs.append(job)
    for entry in feed.get("feed", {}).get("entry", []):
        published = (entry.get("published", {}).get("$t") or "")[:10]
        try:
            posted = datetime.strptime(published, "%Y-%m-%d").replace(tzinfo=IAQ_UTC)
        except ValueError:
            posted = None
        if posted and posted < cutoff - timedelta(days=1):
            continue
        content = re.sub(r"<[^>]+>", " ", (entry.get("content") or entry.get("summary") or {}).get("$t", ""))
        content = re.sub(r"\s+", " ", content.replace("&nbsp;", " ").replace("&amp;", "&"))
        title = re.sub(r"\s+", " ", entry.get("title", {}).get("$t") or "").strip()[:90]
        emails = [e.lower() for e in EMAIL_RE.findall(content)]
        url = ""
        for link in entry.get("link", []) or []:
            if link.get("rel") == "alternate":
                url = link.get("href", "")
                break
        job = {
            "key": "ark-{h}".format(h=(entry.get("id", {}).get("$t") or "")[-40:]),
            "title": title,
            "company": "",
            "text": content[:900],
            "city": "",
            "source": "arkadu-iq.org",
            "url": url,
            "posted": published,
            "apply": emails[0] if emails else "",
        }
        if job["key"] not in seen and job["title"]:
            seen.add(job["key"])
            jobs.append(job)
    return jobs


def score_job(job, keywords, city):
    haystack = normalize(
        "{title} {company} {text} {city}".format(
            title=job.get("title", ""),
            company=job.get("company", ""),
            text=job.get("text", ""),
            city=job.get("city", ""),
        )
    )
    reasons = []
    score = 0
    for term in city_terms(city):
        if term and normalize(term) in haystack:
            score += 4
            reasons.append("المدينة: " + city)
            break
    for keyword in keywords:
        matched = False
        for term in keyword_terms(keyword):
            needle = normalize(term).strip()
            if needle and needle in haystack:
                score += 3
                reasons.append(keyword)
                matched = True
                break
        if matched:
            continue
    if job.get("posted"):
        try:
            posted = datetime.strptime(job["posted"][:10], "%Y-%m-%d").replace(tzinfo=IAQ_UTC)
            age_days = max(0, (datetime.now(IAQ_UTC) - posted).days)
            score += max(0, 3 - age_days)
        except ValueError:
            pass
    return score, reasons[:3]


def recommend(jobs, keywords, city, limit=6, min_score=1):
    scored = []
    for job in jobs:
        score, reasons = score_job(job, keywords, city)
        if score >= min_score:
            scored.append((score, reasons, job))
    scored.sort(key=lambda item: (-item[0], item[2].get("posted") or ""))
    return scored[:limit]


def internal_jobs(rows):
    return [
        {
            "key": "local-{jid}".format(jid=row.get("job_id")),
            "title": row.get("title", ""),
            "company": row.get("company", ""),
            "text": row.get("caption", ""),
            "city": "",
            "source": "",
            "posted": (row.get("created_at") or "")[:10],
            "apply": "",
            "job_id": row.get("job_id"),
        }
        for row in rows
    ]
