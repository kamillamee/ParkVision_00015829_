"""Parking lots (map locations) routes"""
from fastapi import APIRouter, Depends
from typing import List
import aiosqlite
from backend.database import get_db
from backend.models import ParkingLotResponse

router = APIRouter(prefix="/api/lots", tags=["lots"])


@router.get("", response_model=List[ParkingLotResponse])
async def list_lots(db=Depends(get_db)):
    """List all parking lots with coordinates and slot counts (for map)."""
    result = []
    try:
        async with db.execute(
            """SELECT pl.id, pl.name, pl.address, pl.latitude, pl.longitude,
                      COALESCE(pl.is_live, 0) as is_live,
                      COUNT(ps.id) as slots_total,
                      SUM(CASE WHEN ps.is_occupied = 0 THEN 1 ELSE 0 END) as slots_available
               FROM parking_lots pl
               LEFT JOIN parking_slots ps ON ps.lot_id = pl.id
               GROUP BY pl.id
               ORDER BY pl.name"""
        ) as cursor:
            rows = await cursor.fetchall()
        for row in rows:
            d = dict(row)
            d["slots_total"] = d.get("slots_total") or 0
            d["slots_available"] = d.get("slots_available") or 0
            d["is_live"] = bool(d.get("is_live", 0))
            result.append(ParkingLotResponse(**d))
        return result
    except Exception:
        pass
    try:
        async with db.execute(
            "SELECT id, name, address, latitude, longitude, COALESCE(is_live, 0) as is_live FROM parking_lots ORDER BY name"
        ) as cursor:
            rows = await cursor.fetchall()
        for row in rows:
            d = dict(row)
            d["slots_total"] = 0
            d["slots_available"] = 0
            d["is_live"] = bool(d.get("is_live", 0))
            result.append(ParkingLotResponse(**d))
    except Exception:
        pass
    return result
