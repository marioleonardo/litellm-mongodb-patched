"""
Tests for DATABASE_URL cleaning functionality (removing connection_limit/pool_timeout params).
"""
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def clean_db_url(value):
    """Replicate the clean_db_url function from start_litellm.py for testing."""
    if not value or not isinstance(value, str):
        return value
    if "connection_limit" in value or "pool_timeout" in value:
        try:
            parsed = urllib.parse.urlparse(value)
            query_params = urllib.parse.parse_qs(parsed.query)
            query_params.pop("connection_limit", None)
            query_params.pop("pool_timeout", None)
            new_query = urllib.parse.urlencode(query_params, doseq=True)
            reconstructed = urllib.parse.ParseResult(
                parsed.scheme, parsed.netloc, parsed.path,
                parsed.params, new_query, parsed.fragment
            )
            return urllib.parse.urlunparse(reconstructed)
        except Exception:
            return value
    return value


class TestDBCleanURL:
    def test_strips_connection_limit(self):
        url = "mongodb://user:pass@host:27017/db?connection_limit=10&authMechanism=SCRAM-SHA-256"
        cleaned = clean_db_url(url)
        assert "connection_limit" not in cleaned
        assert "authMechanism=SCRAM-SHA-256" in cleaned

    def test_strips_pool_timeout(self):
        url = "mongodb://user:pass@host:27017/db?pool_timeout=30&retryWrites=false"
        cleaned = clean_db_url(url)
        assert "pool_timeout" not in cleaned
        assert "retryWrites=false" in cleaned

    def test_strips_both_params(self):
        url = "mongodb://user:pass@host:27017/db?connection_limit=10&pool_timeout=30&tls=true"
        cleaned = clean_db_url(url)
        assert "connection_limit" not in cleaned
        assert "pool_timeout" not in cleaned
        assert "tls=true" in cleaned

    def test_handles_no_params(self):
        url = "mongodb://user:pass@host:27017/db"
        cleaned = clean_db_url(url)
        assert cleaned == url

    def test_handles_none(self):
        assert clean_db_url(None) is None

    def test_handles_empty(self):
        assert clean_db_url("") == ""
