"""
Tests that create_views.py properly skips view creation for MongoDB.
"""
import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from litellm.proxy.db.create_views import create_missing_views, should_create_missing_views


class TestCreateViewsMongoDB:
    
    @pytest.mark.asyncio
    async def test_create_missing_views_skips_mongodb(self):
        os.environ["DATABASE_URL"] = "mongodb://localhost:27017/db"
        mock_db = AsyncMock()
        result = await create_missing_views(mock_db)
        assert result is None
        mock_db.query_raw.assert_not_called()
        mock_db.execute_raw.assert_not_called()

    @pytest.mark.asyncio
    async def test_should_create_views_returns_false_for_mongodb(self):
        os.environ["DATABASE_URL"] = "mongodb+srv://user:pass@cluster.mongodb.net/db"
        mock_db = AsyncMock()
        result = await should_create_missing_views(mock_db)
        assert result is False
        mock_db.query_raw.assert_not_called()

    @pytest.mark.asyncio
    async def test_should_create_views_returns_false_for_mongodb_plain(self):
        os.environ["DATABASE_URL"] = "mongodb://localhost:27017/db"
        mock_db = AsyncMock()
        result = await should_create_missing_views(mock_db)
        assert result is False
