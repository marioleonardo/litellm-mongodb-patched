"""
Tests that .env configuration is valid and contains all required keys.
"""
import os
import sys
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


def load_dotenv(filepath):
    """Parse a .env file without loading it into environment."""
    result = {}
    if not os.path.exists(filepath):
        return result
    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, _, value = line.partition('=')
                result[key.strip()] = value.strip().strip('"').strip("'")
    return result


class TestDotEnvConfig:
    @pytest.fixture
    def env_vars(self):
        # Look for .env in the project root
        project_root = os.path.join(os.path.dirname(__file__), '..')
        env_path = os.path.join(project_root, '.env')
        if not os.path.exists(env_path):
            env_path = os.path.join(os.path.dirname(__file__), '..', 'AI-gateway', '.env')
        return load_dotenv(env_path)

    def test_database_url_present(self, env_vars):
        assert "DATABASE_URL" in env_vars, "DATABASE_URL must be set in .env"
        url = env_vars.get("DATABASE_URL", "")
        assert url.startswith("mongodb://") or url.startswith("mongodb+srv://")

    def test_litellm_master_key_present(self, env_vars):
        assert "LITELLM_MASTER_KEY" in env_vars, "LITELLM_MASTER_KEY must be set in .env"

    def test_google_client_id_present(self, env_vars):
        assert "GOOGLE_CLIENT_ID" in env_vars, "GOOGLE_CLIENT_ID must be set in .env"
        assert env_vars["GOOGLE_CLIENT_ID"] != "PLACEHOLDER_PLEASE_REPLACE", \
            "GOOGLE_CLIENT_ID must be a real value, not placeholder"

    def test_google_client_secret_present(self, env_vars):
        assert "GOOGLE_CLIENT_SECRET" in env_vars, "GOOGLE_CLIENT_SECRET must be set in .env"
        assert env_vars["GOOGLE_CLIENT_SECRET"] != "PLACEHOLDER_PLEASE_REPLACE", \
            "GOOGLE_CLIENT_SECRET must be a real value, not placeholder"

    def test_proxy_base_url_present(self, env_vars):
        assert "PROXY_BASE_URL" in env_vars, "PROXY_BASE_URL must be set in .env"
        assert env_vars["PROXY_BASE_URL"] == "https://ai-gateway-327109947279.us-central1.run.app"

    def test_google_redirect_uri(self, env_vars):
        assert "GOOGLE_REDIRECT_URI" in env_vars or "PROXY_BASE_URL" in env_vars
        # The redirect URI should be the proxy base URL
        redirect = env_vars.get("GOOGLE_REDIRECT_URI", env_vars.get("PROXY_BASE_URL", ""))
        assert "ai-gateway" in redirect
        assert redirect.startswith("https://")

    def test_allowed_email_domains(self, env_vars):
        assert "ALLOWED_EMAIL_DOMAINS" in env_vars, "ALLOWED_EMAIL_DOMAINS must be set"
        assert "dentsu.com" in env_vars.get("ALLOWED_EMAIL_DOMAINS", "")

    def test_no_placeholder_values(self, env_vars):
        """Ensure no placeholder values remain in .env"""
        for key, value in env_vars.items():
            assert "PLACEHOLDER" not in value, f"{key} contains placeholder value"
            assert "REPLACE_ME" not in value, f"{key} contains placeholder value"
