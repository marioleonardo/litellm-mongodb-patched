"""
MongoDB query adapter for LiteLLM.
Converts PostgreSQL raw SQL queries to MongoDB-compatible Prisma ORM operations.
Since MongoDB / Firestore does not support raw SQL, we intercept query_raw 
and query_first calls and translate them to native Prisma operations.

ALL DB errors are logged at ERROR level for Cloud Run visibility.
"""
import os
import re
import traceback
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta

from litellm._logging import verbose_proxy_logger


def is_mongodb() -> bool:
    """Check if the database is MongoDB."""
    db_url = os.getenv("DATABASE_URL", "")
    return db_url.startswith("mongodb://") or db_url.startswith("mongodb+srv://")


class MongoQueryAdapter:
    """Adapter that intercepts raw SQL queries and translates them to MongoDB ORM calls."""
    
    def __init__(self, prisma_client_or_db):
        self.db = prisma_client_or_db
    
    async def query_raw(self, query: str, *args, **kwargs) -> List[Dict[str, Any]]:
        """Intercept query_raw calls and convert to ORM when possible."""
        
        verbose_proxy_logger.debug(f"MongoDB adapter: intercepted query_raw: {query[:200]}")
        query_lower = query.lower() if isinstance(query, str) else ""
        
        # Handle view existence checks - views don't exist in MongoDB
        if "reltuples" in query_lower or "pg_class" in query_lower:
            return [{"reltuples": 0}]
        
        # Handle view count checks  
        if "view_count" in query_lower or "existing_views" in query_lower:
            return [{"view_count": 8}]
        
        # Handle SELECT 1 style checks
        if "select 1" in query_lower:
            return [{"1": 1}]
        
        # Handle spend analytics queries (LiteLLM_SpendLogs)
        if '"LiteLLM_SpendLogs"' in query or '"litellm_spendlogs"' in query_lower:
            verbose_proxy_logger.warning(
                "MongoDB adapter: spend logs raw query intercepted, returning empty. "
                "Use ORM endpoints for spend data. Query: %s", query[:200]
            )
            return []
            
        # Handle user listing queries
        if '"LiteLLM_UserTable"' in query and 'LEFT JOIN' in query:
            verbose_proxy_logger.warning(
                "MongoDB adapter: user listing JOIN query intercepted, returning empty. "
                "Query: %s", query[:200]
            )
            return []
            
        # Handle verification token queries
        if '"LiteLLM_VerificationToken"' in query:
            verbose_proxy_logger.warning(
                "MongoDB adapter: verification token raw query intercepted. "
                "Query: %s", query[:200]
            )
            return []
            
        # Handle error logs queries
        if '"LiteLLM_ErrorLogs"' in query:
            return []
            
        # For unknown queries, log and return empty
        verbose_proxy_logger.error(
            "MongoDB adapter: UNHANDLED query_raw pattern! "
            "This may cause missing data. Query: %s", query[:300]
        )
        return []
    
    async def query_first(self, query: str, *args, **kwargs) -> Optional[Dict[str, Any]]:
        """Intercept query_first calls - primarily used for token verification."""
        
        verbose_proxy_logger.debug(f"MongoDB adapter: intercepted query_first: {query[:200]}")
        query_lower = query.lower() if isinstance(query, str) else ""
        
        # Handle verification token lookup with team/budget joins (combined_view)
        if "litellm_verificationtoken" in query_lower and "litellm_teamtable" in query_lower:
            return await self._handle_verification_token_first(query, *args, **kwargs)
        
        # Handle simple token lookup
        if "litellm_verificationtoken" in query_lower:
            return await self._handle_simple_token_lookup(query, *args, **kwargs)
        
        # Handle SELECT 1 checks
        if "select 1" in query_lower:
            return {"1": 1}
        
        verbose_proxy_logger.error(
            "MongoDB adapter: UNHANDLED query_first pattern! "
            "This may cause auth failures. Query: %s", query[:300]
        )
        return None
    
    async def _handle_verification_token_first(self, query: str, *args, **kwargs) -> Optional[Dict]:
        """Handle the complex verification token + team + budget JOIN query."""
        
        token_hash = None
        
        # Extract token from args
        if len(args) > 0:
            token_hash = args[0]
        
        # Extract from kwargs
        if not token_hash and "where" in kwargs:
            token_hash = kwargs["where"].get("token")
        
        # Extract from SQL query
        if not token_hash:
            m = re.search(r"v\.token\s*=\s*'([^']+)'", query)
            if m:
                token_hash = m.group(1)
        
        if not token_hash:
            verbose_proxy_logger.error(
                "MongoDB adapter: could not extract token hash from query_first. "
                "Query: %s, args: %s", query[:200], str(args)[:200]
            )
            return None
        
        verbose_proxy_logger.debug(
            "MongoDB adapter: looking up token hash %s", token_hash
        )
        
        # Fetch token record
        try:
            token_record = await self.db.litellm_verificationtoken.find_unique(
                where={"token": token_hash}
            )
        except Exception as e:
            verbose_proxy_logger.error(
                "MongoDB adapter: ERROR fetching token %s: %s\n%s",
                token_hash, str(e), traceback.format_exc()
            )
            return None
            
        if not token_record:
            verbose_proxy_logger.warning(
                "MongoDB adapter: token NOT FOUND in DB: %s", token_hash
            )
            return None
        
        verbose_proxy_logger.debug(
            "MongoDB adapter: token found. user_id=%s, team_id=%s",
            getattr(token_record, "user_id", None),
            getattr(token_record, "team_id", None)
        )
        
        res = token_record.dict()
        
        # Default fields expected by LiteLLM auth
        defaults = {
            "team_spend": None, "team_max_budget": None, "team_soft_budget": None,
            "team_tpm_limit": None, "team_rpm_limit": None, "team_models": [],
            "team_metadata": {}, "team_blocked": None, "team_alias": None,
            "team_members_with_roles": {}, "team_object_permission_id": None,
            "org_id": None, "project_alias": None, "team_member_spend": None,
            "team_member_tpm_limit": None, "team_member_rpm_limit": None,
            "team_model_aliases": {}, "litellm_budget_table_max_budget": None,
            "litellm_budget_table_tpm_limit": None, "litellm_budget_table_rpm_limit": None,
            "litellm_budget_table_model_max_budget": None,
            "litellm_budget_table_soft_budget": None,
            "organization_metadata": {}, "organization_alias": None,
            "organization_max_budget": None, "organization_tpm_limit": None,
            "organization_rpm_limit": None
        }
        for k, v in defaults.items():
            if k not in res:
                res[k] = v
        
        # Fetch team data
        if token_record.team_id:
            try:
                t = await self.db.litellm_teamtable.find_unique(
                    where={"team_id": token_record.team_id},
                    include={"litellm_model_table": True}
                )
                if t:
                    res["team_spend"] = t.spend
                    res["team_max_budget"] = t.max_budget
                    res["team_soft_budget"] = t.soft_budget
                    res["team_tpm_limit"] = t.tpm_limit
                    res["team_rpm_limit"] = t.rpm_limit
                    res["team_models"] = t.models if t.models else []
                    res["team_metadata"] = t.metadata
                    res["team_blocked"] = t.blocked
                    res["team_alias"] = t.team_alias
                    res["team_members_with_roles"] = t.members_with_roles
                    res["team_object_permission_id"] = t.object_permission_id
                    res["org_id"] = t.organization_id
                    if t.litellm_model_table:
                        res["team_model_aliases"] = t.litellm_model_table.aliases
            except Exception as e:
                verbose_proxy_logger.error(
                    "MongoDB adapter: error fetching team %s: %s\n%s",
                    token_record.team_id, str(e), traceback.format_exc()
                )
        
        # Fetch project data
        if token_record.project_id:
            try:
                p = await self.db.litellm_projecttable.find_unique(
                    where={"project_id": token_record.project_id}
                )
                if p:
                    res["project_alias"] = p.project_alias
            except Exception as e:
                verbose_proxy_logger.error(
                    "MongoDB adapter: error fetching project %s: %s",
                    token_record.project_id, str(e)
                )
        
        # Fetch team membership
        if token_record.team_id and token_record.user_id:
            try:
                tm = await self.db.litellm_teammembership.find_unique(
                    where={"user_id_team_id": {
                        "user_id": token_record.user_id,
                        "team_id": token_record.team_id
                    }}
                )
                if tm:
                    res["team_member_spend"] = tm.spend
                    if tm.budget_id:
                        b = await self.db.litellm_budgettable.find_unique(
                            where={"budget_id": tm.budget_id}
                        )
                        if b:
                            res["team_member_tpm_limit"] = b.tpm_limit
                            res["team_member_rpm_limit"] = b.rpm_limit
            except Exception as e:
                verbose_proxy_logger.error(
                    "MongoDB adapter: error fetching team membership: %s", str(e)
                )
        
        # Fetch budget data
        if token_record.budget_id:
            try:
                b = await self.db.litellm_budgettable.find_unique(
                    where={"budget_id": token_record.budget_id}
                )
                if b:
                    res["litellm_budget_table_max_budget"] = b.max_budget
                    res["litellm_budget_table_tpm_limit"] = b.tpm_limit
                    res["litellm_budget_table_rpm_limit"] = b.rpm_limit
                    res["litellm_budget_table_model_max_budget"] = b.model_max_budget
                    res["litellm_budget_table_soft_budget"] = b.soft_budget
            except Exception as e:
                verbose_proxy_logger.error(
                    "MongoDB adapter: error fetching budget %s: %s",
                    token_record.budget_id, str(e)
                )
        
        # Fetch organization data
        if token_record.organization_id:
            try:
                o = await self.db.litellm_organizationtable.find_unique(
                    where={"organization_id": token_record.organization_id},
                    include={"litellm_budget_table": True}
                )
                if o:
                    res["organization_metadata"] = o.metadata
                    res["organization_alias"] = o.organization_alias
                    if o.litellm_budget_table:
                        res["organization_max_budget"] = o.litellm_budget_table.max_budget
                        res["organization_tpm_limit"] = o.litellm_budget_table.tpm_limit
                        res["organization_rpm_limit"] = o.litellm_budget_table.rpm_limit
            except Exception as e:
                verbose_proxy_logger.error(
                    "MongoDB adapter: error fetching org %s: %s",
                    token_record.organization_id, str(e)
                )
        
        res["token"] = token_hash
        return res
    
    async def _handle_simple_token_lookup(self, query: str, *args, **kwargs) -> Optional[Dict]:
        """Handle simple token lookup queries."""
        token_hash = args[0] if args else None
        if not token_hash:
            verbose_proxy_logger.error("MongoDB adapter: no token hash for simple lookup")
            return None
        try:
            record = await self.db.litellm_verificationtoken.find_unique(
                where={"token": token_hash}
            )
            if record:
                return record.dict()
            verbose_proxy_logger.warning("MongoDB adapter: simple token lookup not found: %s", token_hash)
            return None
        except Exception as e:
            verbose_proxy_logger.error(
                "MongoDB adapter: error in simple token lookup %s: %s\n%s",
                token_hash, str(e), traceback.format_exc()
            )
            return None
    
    async def _handle_spend_logs_query(self, query: str, *args) -> List[Dict]:
        """Handle spend analytics queries by returning empty results."""
        return []
    
    async def _handle_user_listing_query(self, query: str, *args) -> List[Dict]:
        """Handle user listing queries with JOINs."""
        return []
    
    async def _handle_verification_token_query(self, query: str, *args) -> List[Dict]:
        """Handle verification token queries."""
        return []


def patch_prisma_for_mongodb(prisma_client_or_db):
    """Apply MongoDB compatibility patches to a Prisma client instance."""
    if not is_mongodb():
        return prisma_client_or_db
    
    adapter = MongoQueryAdapter(prisma_client_or_db)
    
    original_query_raw = getattr(prisma_client_or_db, "query_raw", None)
    original_query_first = getattr(prisma_client_or_db, "query_first", None)
    
    async def mongo_query_raw(query: str, *args, **kwargs):
        return await adapter.query_raw(query, *args, **kwargs)
    
    async def mongo_query_first(query: str, *args, **kwargs):
        return await adapter.query_first(query, *args, **kwargs)
    
    prisma_client_or_db.query_raw = mongo_query_raw
    prisma_client_or_db.query_first = mongo_query_first
    prisma_client_or_db._original_query_raw = original_query_raw
    prisma_client_or_db._original_query_first = original_query_first
    
    return prisma_client_or_db
