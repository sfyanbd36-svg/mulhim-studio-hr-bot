import csv
import os
import smtplib
import ssl
import sys
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path

BASE = Path(__file__).resolve().parent
COMPANIES_CSV = BASE / "companies.csv"
TEMPLATE_FILE = BASE / "email_template.txt"
SENT_LOG = BASE / "sent.csv"
BOT_LINK = "https://t.me/mulhimstudio_hr_bot"
MAX_RECIPIENTS = 20
DELAY_SECONDS = 45

def load_env():
    env_path = BASE.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

def already_sent():
    if not SENT_LOG.exists():
        return set()
    with SENT_LOG.open(encoding="utf-8", newline="") as handle:
        return {row["email"].strip().lower() for row in csv.DictReader(handle)}

def log_sent(email, company):
    file_ready = SENT_LOG.exists() and SENT_LOG.stat().st_size > 0
    with SENT_LOG.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        if not file_ready:
            writer.writerow(["email", "company", "sent_at"])
        writer.writerow([email, company, time.strftime("%Y-%m-%d %H:%M:%S")])

def main():
    load_env()
    sender_email = os.environ.get("OUTREACH_EMAIL", "").strip()
    sender_password = os.environ.get("OUTREACH_APP_PASSWORD", "").strip()
    sender_name = os.environ.get("OUTREACH_FROM_NAME", "Mulhim Studio").strip()
    dry_run = "--send" not in sys.argv

    if not dry_run and (not sender_email or not sender_password):
        print("Missing OUTREACH_EMAIL / OUTREACH_APP_PASSWORD in .env or environment.")
        print("Gmail: Google Account > Security > 2-Step Verification > App passwords")
        sys.exit(1)

    template = TEMPLATE_FILE.read_text(encoding="utf-8")
    rows = list(csv.DictReader(COMPANIES_CSV.open(encoding="utf-8")))
    if len(rows) > MAX_RECIPIENTS:
        print("Refusing to send to %d recipients (max %d)." % (len(rows), MAX_RECIPIENTS))
        sys.exit(1)
    if dry_run:
        for row in rows:
            print("DRY-RUN would send to: %s | %s" % (row["email"], row["company"]))
        print("Dry-run complete (%d recipients). Add OUTREACH_EMAIL + OUTREACH_APP_PASSWORD then rerun with --send." % len(rows))
        sys.exit(0)

    sent_before = already_sent()
    context = ssl.create_default_context()
    server = smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context)
    server.login(sender_email, sender_password)

    sent = 0
    skipped = 0
    failed = 0
    for row in rows:
        email = row["email"].strip()
        company = row["company"].strip()
        if email.lower() in sent_before:
            print("SKIP (already sent):", email)
            skipped += 1
            continue
        body = template.format(roles=row["roles"], company=company)
        message = MIMEMultipart()
        message["From"] = formataddr((sender_name, sender_email))
        message["To"] = email
        message["Subject"] = "بوت توظيف مجاني للشركات العراقية - " + company
        message.attach(MIMEText(body, "plain", "utf-8"))
        if dry_run:
            print("DRY-RUN would send to:", email, "|", company)
            sent += 1
            continue
        try:
            server.sendmail(sender_email, [email], message.as_string())
            log_sent(email, company)
            print("SENT:", email, "|", company)
            sent += 1
            time.sleep(DELAY_SECONDS)
        except Exception as exc:
            print("FAILED:", email, "->", exc)
            failed += 1

    server.quit()
    print("Done. sent=%d skipped=%d failed=%d" % (sent, skipped, failed))
    print("Bot link used:", BOT_LINK)

if __name__ == "__main__":
    main()
