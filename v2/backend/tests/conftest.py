import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

_test_data = tempfile.mkdtemp(prefix="versepro-tests-")
os.environ.setdefault("VERSEPRO_TESTING", "1")
os.environ.setdefault("VERSEPRO_DATA_DIR", _test_data)
os.environ.setdefault("VERSEPRO_DB_PATH", str(Path(_test_data) / "versepro-test.db"))
atexit.register(shutil.rmtree, _test_data, ignore_errors=True)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
