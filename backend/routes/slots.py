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
from backend.config import SLOTS_CONFIG, SLOTS_CONFIG_WEST, AI_API_KEY

router = APIRouter(prefix="/api/slots", tags=["slots"])


def _row_to_slot_status(row) -> SlotStatus:
    d = dict(row)
    if d.get("occupation_source") is None:
        d["occupation_source"] = "vision"
    return SlotStatus(**d)


@router.get("/status", response_model=List[SlotStatus])
async def get_slots_status(    db=Depends(get_db), lot_id: Optional[int] = None):
    try:
        if lot_id is not None:
            try:
                async with db.execute(
                    "SELECT id, slot_number, zone, is_occupied, last_updated, "
                    "COALESCE(occupation_source, 'vision') as occupation_source, lot_id "
                    "FROM parking_slots "
                    "WHERE lot_id = ? ORDER BY slot_number",
                    (lot_id,),
                ) as cursor:
                    rows = await cursor.fetchall()
                    return [_row_to_slot_status(row) for row in rows]
            except Exception:
                pass
        async with db.execute(
            "SELECT id, slot_number, zone, is_occupied, last_updated, "
            "COALESCE(occupation_source, 'vision') as occupation_source, lot_id "
            "FROM parking_slots ORDER BY slot_number"
        ) as cursor:
            rows = await cursor.fetchall()
            return [_row_to_slot_status(row) for row in rows]
    except Exception:
        async with db.execute(
            "SELECT id, slot_number, zone, is_occupied, last_updated, lot_id FROM parking_slots ORDER BY slot_number"
        ) as cursor:
            rows = await cursor.fetchall()
            return [_row_to_slot_status(row) for row in rows]

@router.get("/stats", response_model=SlotStats)
async def get_stats(db=Depends(get_db), lot_id: Optional[int] = None):
    stats = await get_slot_stats(db, lot_id=lot_id)
    return SlotStats(**stats)

def _normalize_slot_keys(data: dict) -> dict:
    return {k.replace("\u0410", "A"): v for k, v in data.items()}


@router.get("/config")
async def get_slots_config(lot_id: Optional[int] = None):
    path = SLOTS_CONFIG
    if lot_id is not None:
        try:
            from backend.config import DATABASE_PATH

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
        data = _normalize_slot_keys(data)

        if lot_id is not None and data:
            try:
                from backend.database import get_db_connection

                async with get_db_connection() as db:
                    async with db.execute(
                        "SELECT slot_number FROM parking_slots WHERE lot_id = ? ORDER BY slot_number",
                        (lot_id,),
                    ) as c:
                        rows = await c.fetchall()
                db_slots = [str(r["slot_number"]) for r in rows if r and r["slot_number"]]
                cfg_keys = list(data.keys())
                overlap = set(db_slots).intersection(cfg_keys)
                if db_slots and not overlap and len(db_slots) == len(cfg_keys):
                    mapped = {}
                    for slot_name, old_key in zip(sorted(db_slots), sorted(cfg_keys)):
                        mapped[slot_name] = data[old_key]
                    return mapped
            except Exception:
                pass

        return data
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Invalid slots config: {str(e)}")

@router.get("/stream")
async def stream_slot_status():
    from backend.config import DATABASE_PATH

    async def generate():
        while True:
            try:
                async with aiosqlite.connect(DATABASE_PATH) as conn:
                    conn.row_factory = aiosqlite.Row
                    async with conn.execute(
                        "SELECT * FROM parking_slots ORDER BY slot_number"
                    ) as cursor:
                        rows = await cursor.fetchall()
                    data = []
                    for row in rows:
                        d = dict(row)
                        if d.get("occupation_source") is None:
                            d["occupation_source"] = "vision"
                        data.append(d)
                payload = json.dumps(data)
                yield f"data: {payload}\n\n"
            except Exception:
                yield "data: []\n\n"
            await asyncio.sleep(1)

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
            detail="No updates provided"
        )
    updated_count = 0
    current_time = datetime.now(timezone.utc).isoformat()
    for update in updates:
        if not update.slot_number:
            continue
        async with db.execute(
            """UPDATE parking_slots 
               SET is_occupied = ?, last_updated = ?, occupation_source = 'vision'
               WHERE slot_number = ?""",
            (1 if update.is_occupied else 0, current_time, update.slot_number)
        ) as cursor:
            if cursor.rowcount > 0:
                updated_count += 1
    await log_action(db, "slot_status_updated", None, {
        "updated_count": updated_count,
        "slots": [u.slot_number for u in updates],
    })
    await db.commit()
    return {"message": f"Updated {updated_count} slots", "updated": updated_count}
