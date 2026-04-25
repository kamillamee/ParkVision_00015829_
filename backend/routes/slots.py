import asyncio
import json
from fastapi import APIRouter, Depends, HTTPException, status, Header
from fastapi.responses import StreamingResponse
from typing import List, Optional
import aiosqlite
from backend.database import get_db
from backend.models import SlotStatus, SlotUpdate, SlotStats
from backend.auth import get_current_user, get_current_admin_user
from backend.services import get_slot_stats
from backend.config import SLOTS_CONFIG, SLOTS_CONFIG_WEST, AI_API_KEY, DATABASE_PATH
from backend.slot_notify import subscribe, unsubscribe, notify_slot_changed

router = APIRouter(prefix="/api/slots", tags=["slots"])


def _row_to_slot_status(row) -> SlotStatus:
    return SlotStatus(**dict(row))


@router.get("/status", response_model=List[SlotStatus])
async def get_slots_status(db=Depends(get_db), lot_id: Optional[int] = None):
    if lot_id is not None:
        async with db.execute(
            "SELECT id, slot_number, zone, is_occupied, last_updated, lot_id "
            "FROM parking_slots WHERE lot_id = ? ORDER BY slot_number",
            (lot_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [_row_to_slot_status(row) for row in rows]
    async with db.execute(
        "SELECT id, slot_number, zone, is_occupied, last_updated, lot_id "
        "FROM parking_slots ORDER BY slot_number"
    ) as cursor:
        rows = await cursor.fetchall()
        return [_row_to_slot_status(row) for row in rows]


@router.get("/stats", response_model=SlotStats)
async def get_stats(db=Depends(get_db), lot_id: Optional[int] = None):
    stats = await get_slot_stats(db, lot_id=lot_id)
    return SlotStats(**stats)


def _normalize_slot_keys(data: dict) -> dict:
    # Cyrillic "А" → Latin "A" so hand-edited JSON still matches DB slot names.
    return {k.replace("\u0410", "A"): v for k, v in data.items()}


@router.get("/config")
async def get_slots_config(lot_id: Optional[int] = None):
    path = SLOTS_CONFIG
    if lot_id is not None:
        try:
            async with aiosqlite.connect(DATABASE_PATH) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT name FROM parking_lots WHERE id = ? LIMIT 1", (lot_id,)
                ) as c:
                    row = await c.fetchone()
            if row and row["name"] and "westminster" in row["name"].lower():
                path = SLOTS_CONFIG_WEST
        except Exception:
            path = SLOTS_CONFIG
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return _normalize_slot_keys(data)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Invalid slots config: {str(e)}")


@router.get("/stream")
async def stream_slot_status():
    async def generate():
        ev = subscribe()
        last_payload: Optional[str] = None
        # Fallback tick so long-idle connections still revalidate and any
        # missed notifications (e.g. writes from a process without the
        # notifier wired) still land within this window.
        idle_timeout = 10.0
        # After being woken, coalesce rapid-fire updates into one SSE frame.
        coalesce_delay = 0.15
        try:
            while True:
                try:
                    async with aiosqlite.connect(DATABASE_PATH) as conn:
                        conn.row_factory = aiosqlite.Row
                        async with conn.execute(
                            "SELECT id, slot_number, zone, is_occupied, last_updated, lot_id "
                            "FROM parking_slots ORDER BY slot_number"
                        ) as cursor:
                            rows = await cursor.fetchall()
                        data = [dict(row) for row in rows]
                    payload = json.dumps(data)
                    if payload != last_payload:
                        last_payload = payload
                        yield f"data: {payload}\n\n"
                except Exception:
                    if last_payload != "[]":
                        last_payload = "[]"
                        yield "data: []\n\n"

                ev.clear()
                try:
                    await asyncio.wait_for(ev.wait(), timeout=idle_timeout)
                    # Woken by a change — wait a beat so bursts coalesce.
                    await asyncio.sleep(coalesce_delay)
                except asyncio.TimeoutError:
                    pass
        finally:
            unsubscribe(ev)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/update-status")
async def update_slot_status(
    updates: List[SlotUpdate],
    db=Depends(get_db),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
):
    from datetime import datetime, timezone
    from backend.audit import log_action

    if AI_API_KEY and x_api_key != AI_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key",
        )
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No updates provided",
        )
    updated_count = 0
    current_time = datetime.now(timezone.utc).isoformat()
    for update in updates:
        if not update.slot_number:
            continue
        if update.lot_id is not None:
            async with db.execute(
                """UPDATE parking_slots
                   SET is_occupied = ?, last_updated = ?
                   WHERE slot_number = ? AND lot_id = ?""",
                (1 if update.is_occupied else 0, current_time, update.slot_number, update.lot_id),
            ) as cursor:
                if cursor.rowcount > 0:
                    updated_count += 1
        else:
            async with db.execute(
                """UPDATE parking_slots
                   SET is_occupied = ?, last_updated = ?
                   WHERE slot_number = ?""",
                (1 if update.is_occupied else 0, current_time, update.slot_number),
            ) as cursor:
                if cursor.rowcount > 0:
                    updated_count += 1
    await log_action(db, "slot_status_updated", None, {
        "updated_count": updated_count,
        "slots": [u.slot_number for u in updates],
    })
    await db.commit()
    if updated_count:
        notify_slot_changed()
    return {"message": f"Updated {updated_count} slots", "updated": updated_count}
