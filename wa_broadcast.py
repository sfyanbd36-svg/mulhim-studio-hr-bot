"""WhatsApp group broadcast with ban-safety limits."""

import asyncio
import json
import logging
import os
import random
from datetime import date, datetime
from pathlib import Path

import httpx

import storage

logger = logging.getLogger("mulhim-wa")

BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "wa_broadcast_state.json"

HEADERS = ["jid", "name", "size", "allowed", "last_sent", "added_at"]

BRIDGE_BASE = os.environ.get("WA_BRIDGE_URL", "http://127.0.0.1:8788").rstrip("/")
if BRIDGE_BASE.endswith("/send"):
    BRIDGE_BASE = BRIDGE_BASE[: -len("/send")]

MAX_GROUPS_PER_RUN = int(os.environ.get("WA_BROADCAST_MAX_GROUPS", "2"))
MAX_SENDS_PER_DAY = int(os.environ.get("WA_BROADCAST_DAILY_CAP", "4"))
DELAY_MIN = int(os.environ.get("WA_BROADCAST_DELAY_MIN", "90"))
DELAY_MAX = int(os.environ.get("WA_BROADCAST_DELAY_MAX", "240"))

TEMPLATES = [
    "وظائف جديدة بالعراق اليوم:\n\n{lines}\n\nتابع كل الوظائف وقدم مباشرة عبر البوت: {bot}\nالموقع: {site}",
    "فرص شغل جديدة نزلت هسه:\n\n{lines}\n\nتصفّح وظائف أكثر وسجّل ببوت مجاني: {bot}",
    "توظيف اليوم — وظائف جديدة:\n\n{lines}\n\nقدّم بسيرة PDF جاهزة من البوت: {bot}",
    "وظائف جديدة بالسوق العراقي:\n\n{lines}\n\nالبوت ينشر الوظائف كل 6 ساعات: {bot}\n{site}",
]

storage.register_schema("wa_groups", HEADERS)


def load_groups():
    return storage.read_table("wa_groups", HEADERS)


def allowed_groups():
    return [g for g in load_groups() if str(g.get("allowed", "")) == "1"]


def set_group_allowed(jid, allowed, name="", size=""):
    jid = str(jid).strip()
    if not jid.endswith("@g.us"):
        return False
    existing = None
    for row in load_groups():
        if str(row.get("jid", "")) == jid:
            existing = row
            break
    if existing is None:
        existing = {
            "jid": jid,
            "name": name or jid,
            "size": str(size or ""),
            "allowed": "1" if allowed else "0",
            "last_sent": "",
            "added_at": datetime.now().isoformat(timespec="seconds"),
        }
        storage.insert_rows("wa_groups", HEADERS, [existing])
    else:
        storage.update_rows(
            "wa_groups",
            {
                "allowed": "1" if allowed else "0",
                "name": name or existing.get("name", ""),
                "size": str(size or existing.get("size", "")),
            },
            "jid",
            jid,
        )
    return True


async def fetch_bridge_groups():
    url = BRIDGE_BASE + "/groups"
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(url)
        response.raise_for_status()
        data = response.json()
    if not data.get("ok"):
        raise RuntimeError(data.get("error") or "bridge error")
    return data.get("groups") or []


async def send_group_message(jid, text):
    url = BRIDGE_BASE + "/send_group"
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(url, json={"jid": jid, "text": text})
        data = response.json() if response.content else {}
        if response.status_code != 200 or not data.get("ok"):
            raise RuntimeError(data.get("error") or "send failed")


async def send_dm(phone, text):
    url = BRIDGE_BASE + "/send"
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(url, json={"phone": phone, "text": text})
        data = response.json() if response.content else {}
        return response.status_code == 200 and bool(data.get("ok"))


def _load_state():
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_state(state):
    STATE_FILE.write_text(json.dumps(state), encoding="utf-8")


def sends_today():
    state = _load_state()
    if state.get("date") == date.today().isoformat():
        return int(state.get("count", 0))
    return 0


def _bump_today():
    state = _load_state()
    today = date.today().isoformat()
    count = int(state.get("count", 0)) + 1 if state.get("date") == today else 1
    _save_state({"date": today, "count": count})
    return count


def build_digest(jobs, bot_link, site_url):
    lines = []
    for i, job in enumerate(jobs[:5], start=1):
        title = (job.get("title") or "")[:70]
        company = (job.get("company") or "")[:40]
        lines.append("{i}) {title} - {company}".format(i=i, title=title, company=company))
    template = random.choice(TEMPLATES)
    return template.format(
        lines="\n".join(lines),
        bot=bot_link,
        site=site_url,
    )


async def broadcast_digest(jobs, bot_link, site_url):
    groups = allowed_groups()
    if not groups:
        return {"sent": 0, "reason": "no allowed groups"}
    remaining = MAX_SENDS_PER_DAY - sends_today()
    if remaining <= 0:
        return {"sent": 0, "reason": "daily cap reached"}
    target_count = min(MAX_GROUPS_PER_RUN, remaining, len(groups))
    random.shuffle(groups)
    text = build_digest(jobs, bot_link, site_url)
    sent = 0
    errors = []
    for group in groups[:target_count]:
        jid = str(group.get("jid", ""))
        try:
            await send_group_message(jid, text)
        except Exception as exc:
            logger.warning("WA group send failed to %s: %s", jid, exc)
            errors.append(jid)
            if sent == 0 and len(errors) >= 2:
                break
            continue
        sent += 1
        _bump_today()
        storage.update_rows(
            "wa_groups",
            {"last_sent": datetime.now().isoformat(timespec="seconds")},
            "jid",
            jid,
        )
        logger.info("WA group broadcast ok: %s (%s/%s)", group.get("name") or jid, sent, target_count)
        if sent < target_count:
            await asyncio.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
    return {"sent": sent, "errors": errors}
