import os
import tempfile
import unittest

os.environ["MULHIM_DB"] = os.path.join(tempfile.gettempdir(), "mulhim_test.db")

import storage


def clear(name, headers):
    storage.register_schema(name, headers)
    with storage._lock:
        conn = storage._conn()
        storage._ensure_table(name, headers, conn)
        conn.execute('DELETE FROM "{}"'.format(name))
        conn.commit()


class StorageTests(unittest.TestCase):
    def setUp(self):
        clear("t_items", ["id", "name", "val"])

    def test_insert_and_read(self):
        storage.insert_rows("t_items", ["id", "name", "val"], [{"id": "1", "name": "a"}])
        rows = storage.read_table("t_items")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "a")
        self.assertEqual(rows[0].get("val", ""), "")

    def test_exists_and_next_id(self):
        storage.insert_rows("t_items", ["id", "name"], [{"id": "5", "name": "x"}])
        self.assertTrue(storage.exists_value("t_items", "id", "5"))
        self.assertFalse(storage.exists_value("t_items", "id", "99"))
        self.assertEqual(storage.next_id("t_items", "id"), 6)

    def test_update_delete(self):
        storage.insert_rows("t_items", ["id", "name"], [{"id": "1", "name": "old"}])
        changed = storage.update_rows("t_items", {"name": "new"}, "id", "1")
        self.assertEqual(changed, 1)
        self.assertEqual(storage.read_table("t_items")[0]["name"], "new")
        removed = storage.delete_rows("t_items", {"id": "1"})
        self.assertEqual(removed, 1)
        self.assertEqual(storage.read_table("t_items"), [])

    def test_upsert(self):
        storage.upsert_row("t_items", ["id", "name"], {"id": "9", "name": "first"}, "id")
        storage.upsert_row("t_items", ["id", "name"], {"id": "9", "name": "second"}, "id")
        rows = storage.read_table("t_items")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "second")

    def test_to_csv_bytes(self):
        storage.insert_rows("t_items", ["id", "name"], [{"id": "1", "name": "x"}])
        blob = storage.to_csv_bytes("t_items")
        text = blob.decode("utf-8")
        self.assertIn("name", text)
        self.assertIn("x", text)

    def test_missing_table_returns_empty(self):
        self.assertEqual(storage.read_table("no_such_table_xyz"), [])

    def test_app_status_schema(self):
        clear(
            "app_status",
            ["row_key", "user_id", "job_id", "status", "updated_at"],
        )
        storage.upsert_row(
            "app_status",
            ["row_key", "user_id", "job_id", "status", "updated_at"],
            {
                "row_key": "77-3",
                "user_id": "77",
                "job_id": "3",
                "status": "طلب مقابلة",
                "updated_at": "2026-10-28",
            },
            "row_key",
        )
        rows = storage.read_table("app_status")
        self.assertEqual(rows[0]["status"], "طلب مقابلة")


if __name__ == "__main__":
    unittest.main()
