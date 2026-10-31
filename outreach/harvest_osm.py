import csv
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from sectors import AMENITY_LABELS, emails_in
except ImportError:
    from outreach.sectors import AMENITY_LABELS, emails_in

OUTREACH = Path(__file__).resolve().parent
POI_CACHE = OUTREACH / "osm_pois.json"
WEB_STATE = OUTREACH / "osm_web_done.json"
SENT_LOG = OUTREACH / "sent.csv"
QUEUE_CSVS = (OUTREACH / "companies.csv", OUTREACH / "companies_web.csv")

MIRRORS = (
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.osm.jp/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
)
USER_AGENT = "mulhim-jobbot-outreach/1.0 (contact: sfyanbd36@gmail.com)"
CACHE_MAX_AGE = timedelta(hours=20)
HOP_DELAY = 1.2
HOP_TIMEOUT = 15
WEB_ATTEMPTS_MAX = 3
AMENITIES = "restaurant|cafe|fast_food|food_court|ice_cream"


def build_query():
    amenity = 'nwr["amenity"~"^({a})$"](area.iq)'.format(a=AMENITIES)
    parts = [
        "[out:json][timeout:75];",
        'area["ISO3166-1"="IQ"][admin_level=2]->.iq;',
        "(",
    ]
    for tag in ("contact:email", "email", "website", "contact:website"):
        parts.append('{p}["{t}"];'.format(p=amenity, t=tag))
    parts.append(");out tags;")
    return "".join(parts)


def log(msg):
    print("{ts} {msg}".format(ts=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg=msg))


def fetch_pois(force=False):
    if not force and POI_CACHE.exists():
        try:
            cached = json.loads(POI_CACHE.read_text(encoding="utf-8"))
            fetched_at = datetime.fromisoformat(cached["fetched_at"])
            if fetched_at.tzinfo is None:
                fetched_at = fetched_at.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - fetched_at < CACHE_MAX_AGE:
                return cached.get("elements") or []
        except Exception:
            pass
    body = urllib.parse.urlencode({"data": build_query()}).encode()
    for mirror in MIRRORS:
        try:
            req = urllib.request.Request(
                mirror,
                data=body,
                headers={
                    "User-Agent": USER_AGENT,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            with urllib.request.urlopen(req, timeout=85) as resp:
                data = json.load(resp)
            elements = data.get("elements") or []
            if not elements:
                continue
            POI_CACHE.write_text(
                json.dumps(
                    {"fetched_at": datetime.now(timezone.utc).isoformat(), "elements": elements}
                ),
                encoding="utf-8",
            )
            log("osm: fetched {n} pois via {m}".format(n=len(elements), m=mirror))
            return elements
        except Exception as exc:
            log("osm: mirror {m} failed: {e}".format(m=mirror, e=str(exc)[:120]))
    log("osm: no mirror answered, using stale/empty cache")
    if POI_CACHE.exists():
        try:
            return json.loads(POI_CACHE.read_text(encoding="utf-8")).get("elements") or []
        except Exception:
            return []
    return []


def known_emails():
    known = set()
    for path in (SENT_LOG,) + QUEUE_CSVS:
        if not path.exists() or path.stat().st_size == 0:
            continue
        try:
            with path.open(encoding="utf-8", newline="") as handle:
                known |= {
                    (row.get("email") or "").strip().lower()
                    for row in csv.DictReader(handle)
                }
        except Exception:
            continue
    known.discard("")
    return known


def load_web_state():
    if WEB_STATE.exists():
        try:
            state = json.loads(WEB_STATE.read_text(encoding="utf-8"))
            if isinstance(state, dict):
                return state
        except Exception:
            pass
    return {}


def save_web_state(state):
    WEB_STATE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def robots_allowed(url):
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https"):
        return False
    robots_url = "{s}://{n}/robots.txt".format(s=parts.scheme, n=parts.netloc)
    try:
        req = urllib.request.Request(robots_url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=8) as resp:
            text = resp.read(60000).decode("utf-8", "ignore")
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            return False
        return True
    except Exception:
        return True
    applies = False
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        lower = line.lower()
        if lower.startswith("user-agent"):
            applies = "*" in line
        elif applies and lower.startswith("disallow"):
            target = line.partition(":")[2].strip()
            if target in ("", "/"):
                if target == "/":
                    return False
    return True


def page_emails(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=HOP_TIMEOUT) as resp:
        raw = resp.read(600000)
    return emails_in(raw.decode("utf-8", "ignore"))


def poi_row(poi, email):
    tags = poi.get("tags") or {}
    amenity = str(tags.get("amenity") or "restaurant")
    label = AMENITY_LABELS.get(amenity, "مطعم")
    city = (tags.get("addr:city") or "").strip()
    name = (tags.get("name") or "").strip().replace("\n", " ")[:60]
    company = name or "{l} {c}".format(l=label, c=city).strip()
    roles = "{l} - {c}".format(l=label, c=city) if city else label
    return {
        "email": email,
        "company": company,
        "roles": [roles],
        "source": "openstreetmap.org/{t}/{i}".format(
            t=poi.get("type") or "node", i=poi.get("id")
        ),
        "posted": "",
        "loc": city,
    }


def leads(max_hops=None):
    import os

    if max_hops is None:
        max_hops = int(os.environ.get("OSM_WEB_HOP_PER_RUN", "12"))
    pois = fetch_pois()
    if not pois:
        return []
    known = known_emails()
    state = load_web_state()
    rows = []
    hops = 0
    for poi in pois:
        tags = poi.get("tags") or {}
        direct = emails_in(
            "{a} {b}".format(a=tags.get("contact:email") or "", b=tags.get("email") or "")
        )
        if direct:
            email = direct[0]
            if email not in known:
                known.add(email)
                rows.append(poi_row(poi, email))
            continue
        website = (tags.get("website") or tags.get("contact:website") or "").strip()
        if not website or not website.startswith(("http://", "https://")):
            continue
        if website in state and state[website] >= WEB_ATTEMPTS_MAX:
            continue
        if hops >= max_hops:
            continue
        hops += 1
        found = None
        if robots_allowed(website):
            try:
                found = (page_emails(website) or [None])[0]
            except Exception:
                found = None
        state[website] = state.get(website, 0) + 1
        time.sleep(HOP_DELAY)
        if found and found not in known:
            known.add(found)
            rows.append(poi_row(poi, found))
    save_web_state(state)
    if rows or hops:
        log("osm: fresh={n} website_hops={h} (pois={p})".format(n=len(rows), h=hops, p=len(pois)))
    return rows


if __name__ == "__main__":
    fresh = leads()
    for row in fresh:
        print("{e} | {c} | {r}".format(e=row["email"], c=row["company"], r=row["roles"]))
    print("fresh={n}".format(n=len(fresh)))
