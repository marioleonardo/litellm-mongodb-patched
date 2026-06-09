"""
Tests for the MongoDB query adapter (litellm/proxy/db/mongo_adapter.py).
"""
import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from litellm.proxy.db.mongo_adapter import (
    is_mongodb,
    MongoQueryAdapter,
    patch_prisma_for_mongodb,
)


class TestIsMongoDB:
    def test_detects_mongodb_url(self):
        os.environ["DATABASE_URL"] = "mongodb://localhost:27017/db"
        assert is_mongodb() is True

    def test_detects_mongodb_srv_url(self):
        os.environ["DATABASE_URL"] = "mongodb+srv://user:pass@cluster.mongodb.net/db"
        assert is_mongodb() is True

    def test_rejects_postgres_url(self):
        os.environ["DATABASE_URL"] = "postgresql://user:pass@localhost:5432/db"
        assert is_mongodb() is False

    def test_rejects_empty_url(self):
        os.environ["DATABASE_URL"] = ""
        assert is_mongodb() is False


class TestMongoQueryAdapterQueryRaw:
    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        db.litellm_verificationtoken = MagicMock()
        db.litellm_teamtable = MagicMock()
        db.litellm_budgettable = MagicMock()
        db.litellm_projecttable = MagicMock()
        db.litellm_teammembership = MagicMock()
        db.litellm_organizationtable = MagicMock()
        db.litellm_spendlogs = MagicMock()
        return db

    @pytest.fixture
    def adapter(self, mock_db):
        return MongoQueryAdapter(mock_db)

    @pytest.mark.asyncio
    async def test_reltuples_query_returns_zero(self, adapter):
        result = await adapter.query_raw(
            "SELECT reltuples::BIGINT FROM pg_class WHERE oid = '\"LiteLLM_SpendLogs\"'::regclass"
        )
        assert result == [{"reltuples": 0}]

    @pytest.mark.asyncio
    async def test_view_count_returns_8(self, adapter):
        result = await adapter.query_raw("SELECT COUNT(*) as view_count FROM something")
        assert result == [{"view_count": 8}]

    @pytest.mark.asyncio
    async def test_select_1_returns_one(self, adapter):
        result = await adapter.query_raw("SELECT 1")
        assert result == [{"1": 1}]

    @pytest.mark.asyncio
    async def test_spend_logs_query_returns_empty(self, adapter):
        result = await adapter.query_raw(
            'SELECT * FROM "LiteLLM_SpendLogs" WHERE startTime > $1', "2024-01-01"
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_error_logs_query_returns_empty(self, adapter):
        result = await adapter.query_raw(
            'SELECT * FROM "LiteLLM_ErrorLogs" WHERE startTime > $1', "2024-01-01"
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_user_listing_with_join_returns_empty(self, adapter):
        result = await adapter.query_raw(
            'SELECT u.*, k.* FROM "LiteLLM_UserTable" u LEFT JOIN "LiteLLM_VerificationToken" k ON u.user_id = k.user_id'
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_unknown_query_returns_empty(self, adapter):
        result = await adapter.query_raw("SELECT * FROM some_unknown_table")
        assert result == []


class TestMongoQueryAdapterQueryFirst:
    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        # Setup token lookup
        token_record = MagicMock()
        token_record.dict.return_value = {
            "token": "sk-test-hash",
            "user_id": "user123",
            "team_id": "team456",
            "project_id": None,
            "budget_id": None,
            "organization_id": None,
            "key_name": "test-key",
            "spend": 10.0,
            "models": ["gpt-4"],
            "metadata": {},
            "blocked": False,
            "max_budget": 100.0,
            "tpm_limit": 1000,
            "rpm_limit": 100,
            "expires": None,
            "aliases": {},
            "config": {},
            "permissions": {},
            "team_id_val": "team456",
            "project_id_val": None,
            "budget_id_val": None,
            "org_id_val": None,
        }
        token_record.token = "sk-test-hash"
        token_record.user_id = "user123"
        token_record.team_id = "team456"
        token_record.project_id = None
        token_record.budget_id = None
        token_record.organization_id = None
        token_record.key_name = "test-key"
        token_record.spend = 10.0
        token_record.models = ["gpt-4"]
        token_record.metadata = {}
        token_record.blocked = False
        token_record.max_budget = 100.0
        token_record.tpm_limit = 1000
        token_record.rpm_limit = 100
        token_record.expires = None

        db.litellm_verificationtoken.find_unique = AsyncMock(return_value=token_record)
        
        # Setup team lookup
        team_record = MagicMock()
        team_record.spend = 50.0
        team_record.max_budget = 500.0
        team_record.soft_budget = 450.0
        team_record.tpm_limit = 5000
        team_record.rpm_limit = 500
        team_record.models = ["gpt-4", "gpt-3.5"]
        team_record.metadata = {"department": "engineering"}
        team_record.blocked = False
        team_record.team_alias = "eng-team"
        team_record.members_with_roles = {"user123": "admin"}
        team_record.object_permission_id = "perm123"
        team_record.organization_id = "org789"
        team_record.litellm_model_table = MagicMock()
        team_record.litellm_model_table.aliases = {"custom-gpt": "gpt-4"}
        db.litellm_teamtable.find_unique = AsyncMock(return_value=team_record)

        # Setup org lookup
        org_record = MagicMock()
        org_record.metadata = {"tier": "enterprise"}
        org_record.organization_alias = "main-org"
        org_record.litellm_budget_table = MagicMock()
        org_record.litellm_budget_table.max_budget = 10000.0
        org_record.litellm_budget_table.tpm_limit = 50000
        org_record.litellm_budget_table.rpm_limit = 5000
        db.litellm_organizationtable.find_unique = AsyncMock(return_value=org_record)

        # Setup budget lookup
        budget_record = MagicMock()
        budget_record.max_budget = 200.0
        budget_record.tpm_limit = 2000
        budget_record.rpm_limit = 200
        budget_record.model_max_budget = {}
        budget_record.soft_budget = 180.0
        db.litellm_budgettable.find_unique = AsyncMock(return_value=budget_record)

        # Setup team membership lookup
        tm_record = MagicMock()
        tm_record.spend = 25.0
        tm_record.budget_id = "budget123"
        db.litellm_teammembership.find_unique = AsyncMock(return_value=tm_record)

        return db

    @pytest.fixture
    def adapter(self, mock_db):
        return MongoQueryAdapter(mock_db)

    @pytest.mark.asyncio
    async def test_verification_token_lookup_with_team_join(self, adapter, mock_db):
        # This is the most critical query - the verification token + team + budget JOIN
        query = """
            SELECT v.*, t.spend as team_spend, t.max_budget as team_max_budget
            FROM "LiteLLM_VerificationToken" v 
            LEFT JOIN "LiteLLM_TeamTable" t ON v.team_id = t.team_id
            WHERE v.token = $1
        """
        result = await adapter.query_first(query, "sk-test-hash")
        
        assert result is not None
        assert result["token"] == "sk-test-hash"
        assert result["team_spend"] == 50.0
        assert result["team_alias"] == "eng-team"
        assert result["team_models"] == ["gpt-4", "gpt-3.5"]
        assert result["team_model_aliases"] == {"custom-gpt": "gpt-4"}
        assert result["team_max_budget"] == 500.0
        assert result["team_members_with_roles"] == {"user123": "admin"}
        assert result["org_id"] == "org789"

    @pytest.mark.asyncio
    async def test_verification_token_extracts_hash_from_sql(self, adapter, mock_db):
        query = """
            SELECT v.* FROM "LiteLLM_VerificationToken" v 
            LEFT JOIN "LiteLLM_TeamTable" t ON v.team_id = t.team_id
            WHERE v.token = 'extracted-from-sql'
        """
        result = await adapter.query_first(query)
        assert result is not None

    @pytest.mark.asyncio
    async def test_verification_token_returns_none_when_no_token(self, adapter):
        result = await adapter.query_first(
            "SELECT v.* FROM LiteLLM_VerificationToken v LEFT JOIN LiteLLM_TeamTable t ON v.team_id = t.team_id"
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_simple_token_lookup(self, adapter, mock_db):
        result = await adapter.query_first(
            "SELECT * FROM LiteLLM_VerificationToken WHERE token = $1", "sk-test-hash"
        )
        assert result is not None
        assert result["token"] == "sk-test-hash"

    @pytest.mark.asyncio
    async def test_select_1_query_first(self, adapter):
        result = await adapter.query_first("SELECT 1")
        assert result == {"1": 1}

    @pytest.mark.asyncio
    async def test_token_not_found_returns_none(self, adapter, mock_db):
        mock_db.litellm_verificationtoken.find_unique = AsyncMock(return_value=None)
        result = await adapter.query_first(
            "SELECT * FROM LiteLLM_VerificationToken WHERE token = 'nonexistent'",
            "nonexistent"
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_default_fields_populated(self, adapter, mock_db):
        query = """
            SELECT v.*, t.spend as team_spend
            FROM "LiteLLM_VerificationToken" v 
            LEFT JOIN "LiteLLM_TeamTable" t ON v.team_id = t.team_id
            WHERE v.token = $1
        """
        result = await adapter.query_first(query, "sk-test-hash")
        
        assert result["team_member_spend"] is not None
        assert result["team_member_tpm_limit"] is not None
        assert result["organization_alias"] is None  # token has no org_id
        assert result["litellm_budget_table_max_budget"] is None
        assert result["litellm_budget_table_tpm_limit"] is None


class TestPatchPrismaForMongoDB:
    def test_patch_adds_query_raw_and_query_first(self, mongodb_env):
        mock_db = MagicMock()
        result = patch_prisma_for_mongodb(mock_db)
        assert hasattr(result, 'query_raw')
        assert hasattr(result, 'query_first')
        assert callable(result.query_raw)
        assert callable(result.query_first)

    def test_patch_does_nothing_for_non_mongodb(self):
        os.environ["DATABASE_URL"] = "postgresql://localhost:5432/db"
        mock_db = MagicMock()
        result = patch_prisma_for_mongodb(mock_db)
        # Should return unchanged
        assert result is mock_db
