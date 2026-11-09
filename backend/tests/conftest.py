import os
import tempfile

# Settings are read at import time, so configure the test environment first.
BASE_DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+psycopg://docintel:docintel@localhost:5432/docintel")
TEST_DATABASE_NAME = "docintel_test"
os.environ["DATABASE_URL"] = BASE_DATABASE_URL.rsplit("/", 1)[0] + "/" + TEST_DATABASE_NAME
os.environ["RUN_JOBS_INLINE"] = "true"
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["API_KEY"] = ""
os.environ["UPLOAD_DIR"] = tempfile.mkdtemp(prefix="docintel-test-")

import pytest  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402


@pytest.fixture(scope="session")
def test_database():
    """Create the test database on first use. Only the API tests need it."""
    admin = create_engine(BASE_DATABASE_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": TEST_DATABASE_NAME})
        if not exists:
            conn.execute(text(f"CREATE DATABASE {TEST_DATABASE_NAME}"))
    admin.dispose()
