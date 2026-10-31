import csv
import os
import sqlite3
import threading
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("MULHIM_DB") or (BASE_DIR / "mulhim.db"))

_lock = threading.RLock()
_local = threading.local()
_schemas = {}
_bootstrapped = False
_bootstrapping = False


def table_name(path):
    name = Path(path).name
    if name.endswith(".csv"):
        name = name[:-4]
    return name


def register_schema(name, headers, csv_path=None, legacy_experience=False):
    _schemas[name] = {
        "headers": list(headers),
        "csv_path": Path(csv_path) if csv_path else None,
        "legacy_experience": legacy_experience,
    }


def _conn():
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(str(DB_PATH), timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return conn


def _ensure_table(name, headers, conn):
    cols = ", ".join('"{}" TEXT NOT NULL DEFAULT \'\''.format(h) for h in headers)
    conn.execute(
        'CREATE TABLE IF NOT EXISTS "{}" ('
        '"_rowid_" INTEGER PRIMARY KEY AUTOINCREMENT, '
        "{}"
        ")".format(name, cols)
    )
    existing = {row[1] for row in conn.execute('PRAGMA table_info("{}")'.format(name))}
    for header in headers:
        if header not in existing:
            conn.execute(
                'ALTER TABLE "{}" ADD COLUMN "{}" TEXT NOT NULL DEFAULT \'\''.format(
                    name, header
                )
            )


def _migrate_csv(name, schema, conn):
    csv_path = schema["csv_path"]
    headers = schema["headers"]
    if csv_path is None or not csv_path.exists() or csv_path.stat().st_size == 0:
        return 0
    count = conn.execute('SELECT COUNT(*) FROM "{}"'.format(name)).fetchone()[0]
    if count:
        return 0
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        old_rows = list(csv.DictReader(handle))
    if not old_rows:
        return 0
    rows = []
    for old_row in old_rows:
        new_row = {key: (old_row.get(key) or "") for key in headers}
        if schema["legacy_experience"] and not new_row.get("work_experience"):
            new_row["work_experience"] = old_row.get("experience") or ""
        rows.append(new_row)
    insert_rows(name, headers, rows, conn=conn)
    return len(rows)


def bootstrap():
    global _bootstrapped, _bootstrapping
    if _bootstrapped or _bootstrapping:
        return
    with _lock:
        if _bootstrapped or _bootstrapping:
            return
        _bootstrapping = True
        try:
            conn = _conn()
            for name, schema in _schemas.items():
                _ensure_table(name, schema["headers"], conn)
                migrated = _migrate_csv(name, schema, conn)
                if migrated:
                    print(
                        "storage: migrated {} rows -> {}".format(migrated, name),
                        flush=True,
                    )
            conn.commit()
            _bootstrapped = True
        finally:
            _bootstrapping = False


def read_table(name, headers=None):
    bootstrap()
    with _lock:
        conn = _conn()
        exists = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone()[0]
        if not exists:
            return []
        if headers:
            _ensure_table(name, headers, conn)
            conn.commit()
        rows = conn.execute('SELECT * FROM "{}"'.format(name)).fetchall()
        keys = {row[1] for row in conn.execute('PRAGMA table_info("{}")'.format(name))}
        keys.discard("_rowid_")
        keys = list(keys)
        result = []
        for row in rows:
            item = {key: (row[key] if row[key] is not None else "") for key in keys}
            result.append(item)
        return result


def insert_rows(name, headers, rows, legacy_experience=False, conn=None):
    bootstrap()
    if not rows:
        return 0
    owns_lock = True
    if conn is not None:
        owns_lock = False
    with _lock:
        target = conn or _conn()
        _ensure_table(name, headers, target)
        clean_rows = []
        for row in rows:
            item = {}
            for key in headers:
                value = row.get(key, "")
                item[key] = "" if value is None else str(value)
            if legacy_experience and not item.get("work_experience"):
                item["work_experience"] = str(row.get("experience") or "")
            clean_rows.append(item)
        columns = ", ".join('"{}"'.format(h) for h in headers)
        placeholders = ", ".join("?" for _ in headers)
        sql = 'INSERT INTO "{}" ({}) VALUES ({})'.format(name, columns, placeholders)
        target.executemany(
            sql, [[row[header] for header in headers] for row in clean_rows]
        )
        if owns_lock:
            target.commit()
        else:
            target.commit()
        return len(clean_rows)


def update_rows(name, set_values, where_column, where_value):
    bootstrap()
    with _lock:
        conn = _conn()
        sets = ", ".join('"{}"=?'.format(k) for k in set_values)
        params = [str(v) for v in set_values.values()]
        params.append(str(where_value))
        cur = conn.execute(
            'UPDATE "{}" SET {} WHERE "{}"=?'.format(name, sets, where_column),
            params,
        )
        conn.commit()
        return cur.rowcount


def delete_rows(name, conditions):
    bootstrap()
    if not conditions:
        return 0
    with _lock:
        conn = _conn()
        exists = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone()[0]
        if not exists:
            return 0
        where = " AND ".join('"{}"=?'.format(k) for k in conditions)
        params = [str(v) for v in conditions.values()]
        cur = conn.execute('DELETE FROM "{}" WHERE {}'.format(name, where), params)
        conn.commit()
        return cur.rowcount


def upsert_row(name, headers, row, key_column):
    bootstrap()
    with _lock:
        conn = _conn()
        _ensure_table(name, headers, conn)
        key_value = str(row.get(key_column, ""))
        existing = conn.execute(
            'SELECT "_rowid_" FROM "{}" WHERE "{}"=?'.format(name, key_column),
            (key_value,),
        ).fetchone()
        clean = {key: ("" if row.get(key) is None else str(row.get(key, ""))) for key in headers}
        if existing:
            sets = ", ".join('"{}"=?'.format(k) for k in headers)
            params = [clean[k] for k in headers]
            params.append(key_value)
            conn.execute(
                'UPDATE "{}" SET {} WHERE "{}"=?'.format(name, sets, key_column),
                params,
            )
        else:
            columns = ", ".join('"{}"'.format(h) for h in headers)
            placeholders = ", ".join("?" for _ in headers)
            conn.execute(
                'INSERT INTO "{}" ({}) VALUES ({})'.format(name, columns, placeholders),
                [clean[h] for h in headers],
            )
        conn.commit()
        return clean


def next_id(name, key_column):
    bootstrap()
    with _lock:
        conn = _conn()
        exists = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone()[0]
        if not exists:
            return 1
        row = conn.execute(
            'SELECT MAX(CAST("{}" AS INTEGER)) FROM "{}"'.format(key_column, name)
        ).fetchone()
        return (row[0] or 0) + 1


def exists_value(name, column, value):
    bootstrap()
    with _lock:
        conn = _conn()
        exists = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone()[0]
        if not exists:
            return False
        row = conn.execute(
            'SELECT COUNT(*) FROM "{}" WHERE "{}"=?'.format(name, column),
            (str(value),),
        ).fetchone()
        return row[0] > 0


def table_count(name):
    bootstrap()
    with _lock:
        conn = _conn()
        exists = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
            (name,),
        ).fetchone()[0]
        if not exists:
            return 0
        return conn.execute('SELECT COUNT(*) FROM "{}"'.format(name)).fetchone()[0]


def to_csv_bytes(name, rows=None, headers=None):
    import io

    if rows is None:
        rows = read_table(name, headers=headers)
    if headers is None:
        schema = _schemas.get(name)
        headers = schema["headers"] if schema else None
    if headers is None and rows:
        headers = list(rows[0].keys())
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer, fieldnames=headers or [], extrasaction="ignore", restval=""
    )
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key, "") for key in (headers or [])})
    return buffer.getvalue().encode("utf-8-sig")
