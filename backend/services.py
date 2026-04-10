import aiosqlite
from typing import List, Optional
from datetime import datetime

async def get_user_cars(db: aiosqlite.Connection, user_id: int) -> List[dict]:
    async with db.execute(
        "SELECT * FROM cars WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,)
    ) as cursor:
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def get_user_reservations(db: aiosqlite.Connection, user_id: int) -> List[dict]:
    async with db.execute("""
        SELECT
            r.*,
            ps.slot_number,
            c.plate_number as car_plate
        FROM reservations r
        JOIN parking_slots ps ON r.slot_id = ps.id
        JOIN cars c ON r.car_id = c.id
        WHERE r.user_id = ?
        ORDER BY r.created_at DESC
    """, (user_id,)) as cursor:
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def check_slot_availability(
    db: aiosqlite.Connection,
    slot_id: int,
    start_time: str,
    end_time: str,
    exclude_reservation_id: Optional[int] = None
) -> bool:
    query = """
        SELECT COUNT(*) as count FROM reservations
        WHERE slot_id = ?
        AND status IN ('active', 'pending')
        AND (
            (start_time <= ? AND end_time >= ?) OR
            (start_time <= ? AND end_time >= ?) OR
            (start_time >= ? AND end_time <= ?)
        )
    """
    params = (slot_id, start_time, start_time, end_time, end_time, start_time, end_time)

    if exclude_reservation_id:
        query += " AND id != ?"
        params = params + (exclude_reservation_id,)

    async with db.execute(query, params) as cursor:
        row = await cursor.fetchone()
        return row["count"] == 0

async def get_slot_stats(db: aiosqlite.Connection, lot_id: Optional[int] = None) -> dict:
    if lot_id is not None:
        try:
            async with db.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN is_occupied = 1 THEN 1 ELSE 0 END) as occupied
                FROM parking_slots WHERE lot_id = ?
            """, (lot_id,)) as cursor:
                row = await cursor.fetchone()
                total = row["total"] or 0
                occupied = row["occupied"] or 0
                available = total - occupied
                occupancy_rate = (occupied / total * 100) if total > 0 else 0.0
                return {
                    "total": total,
                    "occupied": occupied,
                    "available": available,
                    "occupancy_rate": round(occupancy_rate, 2)
                }
        except Exception:
            pass
    async with db.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN is_occupied = 1 THEN 1 ELSE 0 END) as occupied
        FROM parking_slots
    """) as cursor:
        row = await cursor.fetchone()
        total = row["total"] or 0
        occupied = row["occupied"] or 0
        available = total - occupied
        occupancy_rate = (occupied / total * 100) if total > 0 else 0.0
        return {
            "total": total,
            "occupied": occupied,
            "available": available,
            "occupancy_rate": round(occupancy_rate, 2)
        }

async def get_admin_stats(db: aiosqlite.Connection) -> dict:
    async with db.execute("SELECT COUNT(*) as count FROM users") as cursor:
        total_users = (await cursor.fetchone())["count"]

    async with db.execute("SELECT COUNT(*) as count FROM cars") as cursor:
        total_cars = (await cursor.fetchone())["count"]

    async with db.execute("SELECT COUNT(*) as count FROM parking_slots") as cursor:
        total_slots = (await cursor.fetchone())["count"]

    async with db.execute(
        "SELECT COUNT(*) as count FROM parking_slots WHERE is_occupied = 1"
    ) as cursor:
        occupied_slots = (await cursor.fetchone())["count"]

    async with db.execute("SELECT COUNT(*) as count FROM reservations") as cursor:
        total_reservations = (await cursor.fetchone())["count"]

    async with db.execute(
        "SELECT COUNT(*) as count FROM reservations WHERE status = 'active'"
    ) as cursor:
        active_reservations = (await cursor.fetchone())["count"]

    return {
        "total_users": total_users,
        "total_cars": total_cars,
        "total_slots": total_slots,
        "occupied_slots": occupied_slots,
        "total_reservations": total_reservations,
        "active_reservations": active_reservations
    }


async def get_reservations_by_day(db: aiosqlite.Connection, days: int = 7) -> list:
    async with db.execute("""
        SELECT DATE(created_at) as day, COUNT(*) as count
        FROM reservations
        WHERE created_at >= DATE('now', '-' || ? || ' days')
        GROUP BY DATE(created_at)
        ORDER BY day
    """, (days,)) as cursor:
        rows = await cursor.fetchall()
        return [{"day": row["day"], "count": row["count"]} for row in rows]


async def get_top_slots(db: aiosqlite.Connection, limit: int = 10) -> list:
    async with db.execute("""
        SELECT ps.slot_number, ps.zone, COUNT(r.id) as reservation_count
        FROM parking_slots ps
        LEFT JOIN reservations r ON r.slot_id = ps.id AND r.status != 'cancelled'
        GROUP BY ps.id
        ORDER BY reservation_count DESC
        LIMIT ?
    """, (limit,)) as cursor:
        rows = await cursor.fetchall()
        return [
            {"slot_number": row["slot_number"], "zone": row["zone"], "reservation_count": row["reservation_count"]}
            for row in rows
        ]
