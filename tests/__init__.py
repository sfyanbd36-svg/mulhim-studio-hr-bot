import os
import tempfile

_test_db = os.path.join(tempfile.gettempdir(), "mulhim_test.db")
if os.path.exists(_test_db):
    os.remove(_test_db)
os.environ["MULHIM_DB"] = _test_db
