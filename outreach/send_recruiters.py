import csv
from pathlib import Path

from send_auto import already_sent, load_env, log_sent, notify, send_one

HERE = Path(__file__).resolve().parent
TARGETS = HERE / "companies_web.csv"
TEMPLATE = HERE / "email_template_partner.txt"
WANTED = {
    "info_iraq@ses-iraq.com",
    "info@taeen.iq",
    "info@alshaybaa.com",
}
SUBJECT_PREFIX = "شراكة نشر شواغركم بالبوت - "


def main():
    load_env()
    rows = list(csv.DictReader(TARGETS.open(encoding="utf-8")))
    template = TEMPLATE.read_text(encoding="utf-8")
    sent_before = already_sent()
    picked = [r for r in rows if r["email"].strip().lower() in WANTED]
    done = failed = skipped = 0
    total = len(picked)
    for row in picked:
        email = row["email"].strip()
        company = row["company"].strip()
        if email.lower() in sent_before:
            print("skip (already sent):", email)
            skipped += 1
            continue
        body = template.format(company=company).strip()
        ok, err = send_one(email, SUBJECT_PREFIX + company, body)
        if ok:
            log_sent(email, company)
            done += 1
            print("sent:", email, "|", company)
            notify(
                "شركات-توظيف: تم الارسال ({done}/{total}) - {company} <{email}>".format(
                    done=done, total=total, company=company, email=email
                )
            )
        else:
            failed += 1
            print("failed:", email, "|", err)
            notify(
                "شركات-توظيف: فشل الارسال لـ {company}: {err}".format(
                    company=company, err=err[:180]
                )
            )
    print(
        "done={done} failed={failed} skipped={skipped} total={total}".format(
            done=done, failed=failed, skipped=skipped, total=total
        )
    )
    notify(
        "شركات-توظيف: خلص الاجراء - المرسل: {done} | الفاشل: {failed} | المتجاهل: {skipped} | المجموع: {total}".format(
            done=done, failed=failed, skipped=skipped, total=total
        )
    )


if __name__ == "__main__":
    main()
