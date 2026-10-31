"""Local read-only dashboard for mulhim-bot (127.0.0.1:8477)."""

import sqlite3
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "mulhim.db"
HOST = "127.0.0.1"
PORT = 8477

PAGE = """<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="60">
<title>ملهم - لوحة المتابعة</title>
<style>
  :root {{ --bg:#0f172a; --card:#1e293b; --line:#334155; --txt:#e2e8f0; --muted:#94a3b8; --accent:#38bdf8; --ok:#4ade80; }}
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ font-family:-apple-system,"Segoe UI",Tahoma,sans-serif; background:var(--bg); color:var(--txt); padding:24px; }}
  h1 {{ font-size:22px; margin-bottom:4px; }}
  .sub {{ color:var(--muted); font-size:13px; margin-bottom:20px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:12px; margin-bottom:24px; }}
  .card {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px; }}
  .card .num {{ font-size:28px; font-weight:700; color:var(--accent); }}
  .card .lbl {{ font-size:13px; color:var(--muted); margin-top:4px; }}
  table {{ width:100%; border-collapse:collapse; background:var(--card); border:1px solid var(--line); border-radius:12px; overflow:hidden; }}
  th, td {{ padding:10px 12px; text-align:right; font-size:14px; border-bottom:1px solid var(--line); }}
  th {{ color:var(--muted); font-weight:600; background:#16223a; }}
  tr:last-child td {{ border-bottom:none; }}
  .badge {{ display:inline-block; padding:2px 8px; border-radius:99px; font-size:12px; }}
  .on {{ background:#14532d; color:var(--ok); }}
  .off {{ background:#450a0a; color:#f87171; }}
  .verified {{ color:var(--ok); }}
  h2 {{ font-size:16px; margin:24px 0 10px; }}
  .empty {{ color:var(--muted); padding:14px; background:var(--card); border:1px solid var(--line); border-radius:12px; }}
  .chart {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:16px; }}
  .crow {{ display:flex; align-items:center; gap:10px; margin-bottom:7px; font-size:12px; }}
  .clabel {{ width:74px; color:var(--muted); text-align:left; direction:ltr; flex-shrink:0; }}
  .ctrack {{ flex:1; background:#16223a; border-radius:99px; height:16px; overflow:hidden; }}
  .cbar {{ height:100%; background:linear-gradient(90deg,var(--accent),#818cf8); border-radius:99px; min-width:3px; }}
  .cval {{ width:30px; text-align:center; color:var(--txt); font-weight:600; }}
</style>
</head>
<body>
<h1>ملهم - لوحة المتابعة</h1>
<div class="sub">تحديث تلقائي كل دقيقة | {stamp}</div>

<div class="grid">
  <div class="card"><div class="num">{companies}</div><div class="lbl">شركات</div></div>
  <div class="card"><div class="num">{jobs_active}</div><div class="lbl">وظائف شغالة</div></div>
  <div class="card"><div class="num">{jobs_closed}</div><div class="lbl">وظائف مقفلة</div></div>
  <div class="card"><div class="num">{apps}</div><div class="lbl">متقدمين</div></div>
  <div class="card"><div class="num">{apps_week}</div><div class="lbl">آخر 7 أيام</div></div>
  <div class="card"><div class="num">{users}</div><div class="lbl">مستخدمين</div></div>
</div>

<h2>الشركات</h2>
{companies_table}

<h2>الوظائف</h2>
{jobs_table}

<h2>أكثر الوظائف تلقائياً</h2>
{top_table}

<h2>الطلبات اليومية - آخر 14 يوم</h2>
{chart}
</body>
</html>"""


def fetch(query, params=()):
    conn = sqlite3.connect("file:{}?mode=ro".format(DB_PATH), uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in conn.execute(query, params).fetchall()]
    finally:
        conn.close()


def esc(value):
    return (
        str(value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_page():
    companies = fetch(
        "SELECT company_id, name, verified FROM companies ORDER BY company_id"
    )
    jobs = fetch(
        "SELECT job_id, company_id, title, active, created_at FROM company_jobs "
        "ORDER BY job_id DESC"
    )
    apps = fetch(
        "SELECT job, company, timestamp FROM applicants ORDER BY timestamp DESC"
    )
    users_count = len(fetch("SELECT user_id FROM users"))
    jobs_active = sum(1 for j in jobs if str(j["active"]) == "1")
    jobs_closed = len(jobs) - jobs_active
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    apps_week = sum(1 for a in apps if (a["timestamp"] or "")[:10] >= week_ago)

    company_names = {c["company_id"]: c["name"] for c in companies}
    if companies:
        rows = "".join(
            "<tr><td>#{id}</td><td>{name}</td><td>{v}</td></tr>".format(
                id=esc(c["company_id"]),
                name=esc(c["name"]),
                v='<span class="verified">موثّقة ✓</span>'
                if str(c["verified"]) == "1"
                else "غير موثّقة",
            )
            for c in companies
        )
        companies_table = (
            "<table><tr><th>#</th><th>الشركة</th><th>التوثيق</th></tr>{}</table>".format(
                rows
            )
        )
    else:
        companies_table = '<div class="empty">ماكو شركات بعد</div>'

    if jobs:
        rows = "".join(
            "<tr><td>#{jid}</td><td>{title}</td><td>{company}</td>"
            "<td>{age} يوم</td><td>{badge}</td></tr>".format(
                jid=esc(j["job_id"]),
                title=esc(j["title"]),
                company=esc(company_names.get(j["company_id"], j["company_id"])),
                age=age_days(j["created_at"]),
                badge='<span class="badge on">شغالة</span>'
                if str(j["active"]) == "1"
                else '<span class="badge off">مقفلة</span>',
            )
            for j in jobs[:25]
        )
        jobs_table = (
            "<table><tr><th>#</th><th>الوظيفة</th><th>الشركة</th><th>العمر</th>"
            "<th>الحالة</th></tr>{}</table>".format(rows)
        )
    else:
        jobs_table = '<div class="empty">ماكو وظائف بعد</div>'

    counter = {}
    for a in apps:
        counter[a["job"] or "بدون وظيفة"] = counter.get(a["job"] or "بدون وظيفة", 0) + 1
    if counter:
        ranked = sorted(counter.items(), key=lambda kv: -kv[1])[:10]
        rows = "".join(
            "<tr><td>{}</td><td>{}</td></tr>".format(esc(job), count)
            for job, count in ranked
        )
        top_table = "<table><tr><th>الوظيفة</th><th>المتقدمين</th></tr>{}</table>".format(
            rows
        )
    else:
        top_table = '<div class="empty">ماكو طلبات بعد</div>'

    daily = {}
    for a in apps:
        day = (a["timestamp"] or "")[:10]
        if day:
            daily[day] = daily.get(day, 0) + 1
    days = [
        (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        for i in range(13, -1, -1)
    ]
    peak = max([daily.get(d, 0) for d in days] + [1])
    bars = "".join(
        '<div class="crow"><span class="clabel">{d}</span>'
        '<div class="ctrack"><div class="cbar" style="width:{pct}%"></div></div>'
        '<span class="cval">{n}</span></div>'.format(
            d=day[5:], pct=max(round(daily.get(day, 0) * 100 / peak), 0), n=daily.get(day, 0)
        )
        for day in days
    )
    chart = '<div class="chart">{}</div>'.format(bars)

    return PAGE.format(
        stamp=datetime.now().strftime("%Y-%m-%d %H:%M"),
        companies=len(companies),
        jobs_active=jobs_active,
        jobs_closed=jobs_closed,
        apps=len(apps),
        apps_week=apps_week,
        users=users_count,
        companies_table=companies_table,
        jobs_table=jobs_table,
        top_table=top_table,
        chart=chart,
    )


def age_days(created_at):
    raw = (created_at or "").strip()
    if not raw:
        return "-"
    try:
        created = datetime.fromisoformat(raw)
    except ValueError:
        return "-"
    return max((datetime.now(created.tzinfo) if created.tzinfo else datetime.now()) - created, timedelta()).days


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/", "/index.html"):
            self.send_response(404)
            self.end_headers()
            return
        try:
            body = build_page().encode("utf-8")
        except Exception as exc:
            body = ("<h1>DB error</h1><pre>{}</pre>".format(esc(exc))).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


def main():
    server = HTTPServer((HOST, PORT), Handler)
    print("dashboard: http://{}:{}/".format(HOST, PORT), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
