"""
Monkeypatches for Prisma Client Python to make upsert/update/create_many
MongoDB-compatible. In MongoDB/Firestore, primary keys (@id mapped to _id)
are immutable and cannot appear in the update section.
"""
import functools
from typing import Any, Callable, Coroutine

from litellm._logging import verbose_proxy_logger


_PRIMARY_KEYS = frozenset({
    "user_id", "budget_id", "credential_id", "model_id", "agent_id",
    "organization_id", "team_id", "project_id", "id", "token", "request_id",
    "tag_name", "param_name", "server_id", "toolset_id", "config_type",
    "skill_id", "policy_id", "attachment_id", "tool_id", "access_group_id",
    "memory_id", "run_id", "event_id", "message_id", "guardrail_id",
    "health_check_id", "search_tool_id", "cronjob_id", "index_name",
    "unified_file_id", "unified_object_id", "unified_resource_id",
    "vector_store_id",
})


def _strip_pk_from_dict(data: dict, where: Any, model_name: str) -> None:
    """Strip primary keys from a data dict that are in the where clause or are known PKs."""
    where_keys = []
    try:
        if hasattr(where, "keys"):
            where_keys = list(where.keys())
        elif isinstance(where, dict):
            where_keys = list(where.keys())
    except Exception:
        pass

    for k in where_keys:
        if k in data:
            verbose_proxy_logger.debug(
                "Popping lookup/where key '%s' from %s update payload", k, model_name
            )
            data.pop(k, None)

    for pk in _PRIMARY_KEYS:
        if pk in data:
            verbose_proxy_logger.debug(
                "Popping immutable primary key '%s' from %s update payload", pk, model_name
            )
            data.pop(pk, None)


def _make_mongo_upsert(original_upsert: Callable, model_name: str) -> Callable:
    """Wrap upsert to strip primary keys from the update section."""

    @functools.wraps(original_upsert)
    async def patched_upsert(*args: Any, **kwargs: Any) -> Any:
        where = kwargs.get("where")
        data = kwargs.get("data")
        if len(args) > 1:
            where = args[1]
        if len(args) > 2:
            data = args[2]

        if isinstance(data, dict):
            update_dict = data.get("update")
            if isinstance(update_dict, dict):
                _strip_pk_from_dict(update_dict, where, model_name)

        return await original_upsert(*args, **kwargs)

    return patched_upsert


def _make_mongo_update(original_update: Callable, model_name: str) -> Callable:
    """Wrap update to strip primary keys from the data section."""

    @functools.wraps(original_update)
    async def patched_update(*args: Any, **kwargs: Any) -> Any:
        where = kwargs.get("where")
        data = kwargs.get("data")
        if len(args) > 1:
            data = args[1]
        if len(args) > 2:
            where = args[2]

        if isinstance(data, dict):
            _strip_pk_from_dict(data, where, model_name)

        return await original_update(*args, **kwargs)

    return patched_update


def _make_mongo_create_many(original_create_many: Callable, model_name: str) -> Callable:
    """Wrap create_many to strip skip_duplicates (unsupported by MongoDB Prisma)."""

    @functools.wraps(original_create_many)
    async def patched_create_many(*args: Any, **kwargs: Any) -> Any:
        if "skip_duplicates" in kwargs:
            verbose_proxy_logger.debug(
                "Stripping skip_duplicates from %s.create_many (kwargs)", model_name
            )
            kwargs.pop("skip_duplicates", None)

        # Clean positional args
        new_args = list(args)
        if len(new_args) > 2:
            new_args = new_args[:2]
        elif len(new_args) == 2 and isinstance(new_args[1], bool):
            new_args = [new_args[0]]

        return await original_create_many(*new_args, **kwargs)

    return patched_create_many


def apply_mongo_prisma_action_patches() -> bool:
    """
    Apply MongoDB-compatible patches to Prisma action classes.
    Strips immutable PKs from upsert/update and removes skip_duplicates from create_many.

    Returns True if patches were applied, False otherwise.
    """
    import os
    db_url = os.getenv("DATABASE_URL", "")
    if not (db_url.startswith("mongodb://") or db_url.startswith("mongodb+srv://")):
        return False

    try:
        import prisma.actions

        for attr_name in dir(prisma.actions):
            attr = getattr(prisma.actions, attr_name)
            if not isinstance(attr, type):
                continue

            if hasattr(attr, "upsert") and callable(getattr(attr, "upsert")):
                setattr(
                    attr,
                    "upsert",
                    _make_mongo_upsert(getattr(attr, "upsert"), attr_name),
                )

            if hasattr(attr, "update") and callable(getattr(attr, "update")):
                setattr(
                    attr,
                    "update",
                    _make_mongo_update(getattr(attr, "update"), attr_name),
                )

            if hasattr(attr, "create_many") and callable(getattr(attr, "create_many")):
                setattr(
                    attr,
                    "create_many",
                    _make_mongo_create_many(getattr(attr, "create_many"), attr_name),
                )

        verbose_proxy_logger.info("Applied MongoDB-compatible Prisma action patches (upsert/update/create_many).")
        return True
    except Exception as e:
        verbose_proxy_logger.error("Failed to apply MongoDB Prisma action patches: %s", e)
        return False
