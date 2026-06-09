import os
import sys
import pytest

# Ensure the litellm source is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

@pytest.fixture
def mongodb_env():
    """Set up MongoDB environment variables for testing."""
    original_url = os.environ.get("DATABASE_URL", "")
    os.environ["DATABASE_URL"] = "mongodb://testuser:testpass@localhost:27017/testdb?authMechanism=SCRAM-SHA-256"
    yield
    if original_url:
        os.environ["DATABASE_URL"] = original_url
    else:
        del os.environ["DATABASE_URL"]
