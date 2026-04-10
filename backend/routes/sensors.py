"""Sensor data routes - receive readings from ultrasonic, IR, etc. and update slot status"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from backend.database import get_db
from backend.models import SensorReadingsBatch
from backend.audit import log_action

router = APIRouter(prefix="/api/sensors", tags=["sensors"])


@router.post("/readings")
async def submit_sensor_readings(
    batch: SensorReadingsBatch,
    db=Depends(get_db),
):
    """
    Submit sensor readings (e.g. ultrasonic, IR). Updates parking_slots with occupation_source='sensor'.
    Used by sensor hardware or the sensor emulator.
    """
    if not batch.readings:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No readings provided",
        )
    current_time = datetime.now(timezone.utc).isoformat()
    updated_count = 0
    use_occupation_source = True
    for item in batch.readings:
        try:
            async with db.execute(
                """INSERT INTO sensor_readings (slot_number, source, is_occupied, created_at)
                   VALUES (?, ?, ?, ?)""",
                (item.slot_number, item.source, 1 if item.is_occupied else 0, current_time),
            ):
                pass
            if use_occupation_source:
                try:
                    async with db.execute(
                        """UPDATE parking_slots
                           SET is_occupied = ?, last_updated = ?, occupation_source = 'sensor'
                           WHERE slot_number = ?""",
                        (1 if item.is_occupied else 0, current_time, item.slot_number),
                    ) as cursor:
                        if cursor.rowcount > 0:
                            updated_count += 1
                except Exception:
                    use_occupation_source = False
                    async with db.execute(
                        """UPDATE parking_slots SET is_occupied = ?, last_updated = ? WHERE slot_number = ?""",
                        (1 if item.is_occupied else 0, current_time, item.slot_number),
                    ) as cursor:
                        if cursor.rowcount > 0:
                            updated_count += 1
            else:
                async with db.execute(
                    """UPDATE parking_slots SET is_occupied = ?, last_updated = ? WHERE slot_number = ?""",
                    (1 if item.is_occupied else 0, current_time, item.slot_number),
                ) as cursor:
                    if cursor.rowcount > 0:
                        updated_count += 1
        except Exception:
            continue
    await log_action(
        db,
        "sensor_readings_submitted",
        None,
        {"count": len(batch.readings), "updated_slots": updated_count},
    )
    await db.commit()
    return {
        "message": f"Accepted {len(batch.readings)} readings, updated {updated_count} slots",
        "readings_count": len(batch.readings),
        "updated_count": updated_count,
    }
