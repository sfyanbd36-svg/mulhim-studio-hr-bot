import csv
import urllib.parse
from pathlib import Path

BASE = Path(__file__).resolve().parent
rows = list(csv.DictReader((BASE / "companies.csv").open(encoding="utf-8")))
template = (BASE / "email_template.txt").read_text(encoding="utf-8")

cards = []
for index, row in enumerate(rows, start=1):
    body = template.format(roles=row["roles"], company=row["company"])
    body = body.replace("[اسمك]", "سفيان").strip()
    subject = "بوت توظيف مجاني للشركات العراقية - " + row["company"]
    gmail_url = (
        "https://mail.google.com/mail/?view=cm&fs=1"
        "&to=" + urllib.parse.quote(row["email"])
        + "&su=" + urllib.parse.quote(subject)
        + "&body=" + urllib.parse.quote(body)
    )
    mailto_url = (
        "mailto:" + row["email"]
        + "?subject=" + urllib.parse.quote(subject)
        + "&body=" + urllib.parse.quote(body)
    )
    cards.append(
        """
<div class="card">
  <h2>{index}. {company}</h2>
  <p class="email">{email}</p>
  <p class="roles">الوظائف: {roles}</p>
  <p class="actions">
    <a class="btn" href="{gmail}" target="_blank">افتح بجيميل وابعث</a>
    <a class="btn alt" href="{mailto}">افتح بتطبيق البريد</a>
  </p>
  <details>
    <summary>أو انسخ الرسالة يدوياً</summary>
    <pre>{body}</pre>
  </details>
</div>
""".format(
            index=index,
            company=row["company"].replace("&", "&amp;"),
            email=row["email"],
            roles=row["roles"].replace("&", "&amp;"),
            gmail=gmail_url,
            mailto=mailto_url,
            body=body.replace("&", "&amp;").replace("<", "&lt;"),
        )
    )

html = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<title>ارسل لشركات التوظيف - Mulhim Studio</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", sans-serif; background: #f4f6f8; color: #1f2937; margin: 0; padding: 24px; }}
  .wrap {{ max-width: 760px; margin: 0 auto; }}
  h1 {{ color: #14532d; font-size: 22px; }}
  .note {{ background: #ffffff; border: 1px solid #d1d5db; border-radius: 10px; padding: 14px 18px; line-height: 1.7; box-shadow: 0 1px 3px rgba(0,0,0,.06); }}
  .card {{ background: #ffffff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 16px 18px; margin: 14px 0; box-shadow: 0 1px 3px rgba(0,0,0,.05); }}
  .card h2 {{ margin: 0 0 6px; font-size: 17px; color: #111827; }}
  .email {{ direction: ltr; text-align: left; color: #6b7280; margin: 4px 0; font-family: monospace; }}
  .roles {{ color: #374151; margin: 6px 0 10px; font-size: 14px; }}
  .btn {{ display: inline-block; background: #15803d; color: #fff; text-decoration: none; padding: 10px 16px; border-radius: 8px; margin-left: 8px; font-size: 14px; }}
  .btn.alt {{ background: #6b7280; }}
  .btn:hover {{ filter: brightness(1.08); }}
  details {{ margin-top: 10px; color: #4b5563; }}
  pre {{ direction: rtl; text-align: right; white-space: pre-wrap; background: #f3f4f6; padding: 12px; border-radius: 8px; font-size: 13px; line-height: 1.6; border: 1px solid #e5e7eb; }}
</style>
</head>
<body>
<div class="wrap">
  <h1>ارسل البوت لـ {count} شركة عراقية محتاجة موظفين</h1>
  <div class="note">
    الطريقة: اضغط <b>افتح بجيميل وابعث</b> → يفتح تبويب بالرسالة جاهزة → اضغط <b>Send</b> → ارجع لهني للشركة اللي بعدها.<br>
    لازم تكون مسجل دخول بجيميل بالمتصفح. إذا مو، استخدم زر تطبيق البريد أو انسخ الرسالة.
  </div>
  {cards}
</div>
</body>
</html>
""".format(count=len(cards), cards="\n".join(cards))

(BASE / "send_manual.html").write_text(html, encoding="utf-8")
print("written:", BASE / "send_manual.html", "cards:", len(cards))
