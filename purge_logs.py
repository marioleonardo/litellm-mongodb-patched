#!/usr/bin/env python3
"""One-shot script to delete all spend logs and audit logs older than retention_days.

Usage:
    python purge_logs.py [retention_days]

Default retention_days = 7.
"""
import os
import sys
import asyncio
from datetime import datetime, timedelta, timezone

RETENTION_DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 7


async def main():
    # Strip Prisma-unsupported connection params from DATABASE_URL (Firestore MongoDB compat)
    db_url = os.environ.get("DATABASE_URL", "")
    if "connection_limit" in db_url or "pool_timeout" in db_url:
        from urllib.parse import urlparse, parse_qs, urlencode, ParseResult
        p = urlparse(db_url)
        q = parse_qs(p.query)
        q.pop("connection_limit", None)
        q.pop("pool_timeout", None)
        new_q = urlencode(q, doseq=True)
        db_url = ParseResult(p.scheme, p.netloc, p.path, p.params, new_q, p.fragment).geturl()
        os.environ["DATABASE_URL"] = db_url
        print(f"Cleaned DATABASE_URL for Prisma/Firestore compat")

    from prisma import Prisma
    db = Prisma()
    await db.connect()
    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    print(f"Cutoff: {cutoff.isoformat()} (deleting spend logs older than {RETENTION_DAYS}d)")

    try:
        deleted = await db.litellm_spendlogs.delete_many(
            where={"startTime": {"lt": cutoff}}
        )
        print(f"Deleted spend logs: {deleted}")
    except Exception as e:
        print(f"Spend logs delete error: {e}")

    try:
        # LiteLLM_AuditLog table may be named differently; skip if missing
        if hasattr(db, "litellm_auditlog"):
            deleted = await db.litellm_auditlog.delete_many(
                where={"updated_at": {"lt": cutoff}}
            )
            print(f"Deleted audit logs: {deleted}")
    except Exception as e:
        print(f"Audit log delete error (non-fatal): {e}")

    await db.disconnect()
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
