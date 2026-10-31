import csv
import sys
from pathlib import Path

PAIRS = (("sent.csv", "email"), ("companies_web.csv", "email"))


def load(path):
    if not path.exists() or path.stat().st_size == 0:
        return [], []
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = list(reader.fieldnames or [])
        return [row for row in reader], fields


def save(path, rows, fields):
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def merge(local_dir, remote_dir):
    for name, key in PAIRS:
        local_path = local_dir / name
        remote_path = remote_dir / name
        local_rows, local_fields = load(local_path)
        remote_rows, remote_fields = load(remote_path)
        fields = list(local_fields) or list(remote_fields)
        for field in remote_fields:
            if field not in fields:
                fields.append(field)
        if not fields:
            continue
        merged, seen = [], set()
        for row in local_rows + remote_rows:
            value = (row.get(key) or "").strip().lower()
            if not value or value in seen:
                continue
            seen.add(value)
            merged.append(row)
        save(local_path, merged, fields)
        save(remote_path, merged, fields)
        print(
            "{n}: merged={m} (local={l} remote={r})".format(
                n=name, m=len(merged), l=len(local_rows), r=len(remote_rows)
            )
        )


def main():
    merge(Path(sys.argv[1]), Path(sys.argv[2]))


if __name__ == "__main__":
    main()
