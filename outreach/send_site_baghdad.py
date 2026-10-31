import csv
from pathlib import Path

from send_auto import already_sent, load_env, log_sent, notify, send_one

HERE = Path(__file__).resolve().parent
COMPANIES = HERE / "companies_baghdad.csv"
TEMPLATE = HERE / "email_template_site.txt"


def main():
    load_env()
    rows = list(csv.DictReader(COMPANIES.open(encoding="utf-8")))
    template = TEMPLATE.read_text(encoding="utf-8")
    sent_before = already_sent()
    total = len(rows)
    done = failed = skipped = 0
    for row in rows:
        email = row["email"].strip()
        company = row["company"].strip()
        if email.lower() in sent_before:
            print("skip (already sent):", email)
            skipped += 1
            continue
        body = template.format(roles=row["roles"].strip(), company=company).strip()
        subject = "تطوير مواقع وتطبيقات وواجهات - عرض تعاون | " + company
        ok, err = send_one(email, subject, body)
        if ok:
            log_sent(email, company)
            done += 1
            print("sent:", email, "|", company)
            notify(
                "بغداد-موقع: تم الارسال ({done}/{total}) - {company} <{email}>".format(
                    done=done, total=total, company=company, email=email
                )
            )
        else:
            failed += 1
            print("failed:", email, "|", err)
            notify("بغداد-موقع: فشل الارسال لـ {company}: {err}".format(company=company, err=err[:180]))
    print("done={done} failed={failed} skipped={skipped} total={total}".format(done=done, failed=failed, skipped=skipped, total=total))
    notify(
        "بغداد-موقع: خلص الاجراء - المرسل: {done} | الفاشل: {failed} | المتجاهل: {skipped} | المجموع: {total}".format(
            done=done, failed=failed, skipped=skipped, total=total
        )
    )


if __name__ == "__main__":
    main()
