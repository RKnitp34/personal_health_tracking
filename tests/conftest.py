"""Point the app at a throwaway SQLite file before any app module is
imported by a test, so tests never touch the real dev database."""
import os
import tempfile

_tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp_db.name}"
