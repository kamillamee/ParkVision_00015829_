"""Audit logging for admin and compliance."""
import json
import aiosqlite
from typing import Optional


async def log_action(
    db: aiosqlite.Connection,
    action: str,
    user_id: Optional[int] = None,
    details: Optional[dict] = None,
) -> None:
    """Append an entry to the audit log. Caller must commit."""
    details_str = json.dumps(details) if details is not None else None
    await db.execute(
        "INSERT INTO audit_log (action, user_id, details) VALUES (?, ?, ?)",
        (action, user_id, details_str),
    )
