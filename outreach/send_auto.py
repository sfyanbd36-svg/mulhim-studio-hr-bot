import csv
import os
import smtplib
from email.mime.text import MIMEText
from pathlib import Path

import httpx

try:
    from sectors import bot_template_for
except ImportError:
    from outreach.sectors import bot_template_for

BASE = Path(__file__).resolve().parent.parent
COMPANIES_CSV = BASE / "outreach" / "companies.csv"
TEMPLATE_FILE = BASE / "outreach" / "email_template.txt"
SENT_LOG = BASE / "outreach" / "sent.csv"
DEAD_LIST = BASE / "outreach" / "dead_emails.txt"


def load_env():
    env_path = BASE / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            import os

            os.environ.setdefault(key.strip(), value.strip())


def notify(text):
    import os

    token = os.environ.get("MULHIM_BOT_TOKEN", "").strip()
    admin = (os.environ.get("ADMIN_CHAT_IDS", "") or "").split(",")[0].strip()
    if not token or not admin:
        print("[notify skipped, no token/chat]: {t}".format(t=text))
        return
    try:
        httpx.post(
            "https://api.telegram.org/bot{token}/sendMessage".format(token=token),
            json={"chat_id": admin, "text": text},
            timeout=30,
        )
    except Exception as exc:
        print("[notify failed, ignored]: {e} | {t}".format(e=exc, t=text))


def send_one(to_addr, subject, body):
    sender = os.environ.get("OUTREACH_EMAIL", "").strip()
    password = os.environ.get("OUTREACH_APP_PASSWORD", "").strip()
    if not sender or not password:
        return False, "OUTREACH_EMAIL / OUTREACH_APP_PASSWORD missing in .env"
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to_addr
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
            server.login(sender, password)
            server.sendmail(sender, [to_addr], msg.as_string())
        return True, ""
    except Exception as exc:
        return False, str(exc)


def already_sent():
    known = set()
    if SENT_LOG.exists():
        with SENT_LOG.open(encoding="utf-8", newline="") as handle:
            known |= {row["email"].strip().lower() for row in csv.DictReader(handle)}
    if DEAD_LIST.exists():
        known |= {
            line.strip().lower()
            for line in DEAD_LIST.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
    return known


def log_sent(email, company):
    ready = SENT_LOG.exists() and SENT_LOG.stat().st_size > 0
    with SENT_LOG.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        if not ready:
            writer.writerow(["email", "company", "sent_at"])
        import time

        writer.writerow([email, company, time.strftime("%Y-%m-%d %H:%M:%S")])


def main():
    load_env()
    rows = list(csv.DictReader(COMPANIES_CSV.open(encoding="utf-8")))
    sent_before = already_sent()
    done = 0
    failed = 0
    total = len(rows)
    templates = {}
    for index, row in enumerate(rows, start=1):
        email = row["email"].strip()
        company = row["company"].strip()
        if email.lower() in sent_before:
            continue
        roles = row.get("roles") or ""
        tpl_path, subject_prefix = bot_template_for(roles)
        if tpl_path not in templates:
            templates[tpl_path] = tpl_path.read_text(encoding="utf-8")
        body = templates[tpl_path].format(roles=roles, company=company)
        body = body.replace("[اسمك]", "سفيان").strip()
        subject = subject_prefix + " - " + company
        ok, err = send_one(email, subject, body)
        if ok:
            log_sent(email, company)
            done += 1
            notify(
                "تم الارسال ({index}/{total}) - {company} <{email}>".format(
                    index=index, total=total, company=company, email=email
                )
            )
        else:
            failed += 1
            notify(
                "فشل الارسال لـ {company}: {err}".format(
                    company=company, err=err[:180]
                )
            )
    notify(
        "خلاص الاجراء - المرسل: {done} | الفاشل: {failed} | المجموع: {total}".format(
            done=done, failed=failed, total=total
        )
    )
    print("done={done} failed={failed} total={total}".format(done=done, failed=failed, total=total))


if __name__ == "__main__":
    main()
