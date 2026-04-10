"""Admin routes"""
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
import aiosqlite
from backend.database import get_db
from backend.models import (
    AdminStats,
    UserResponse,
    ReservationResponse,
    ReservationsByDay,
    TopSlot,
    AuditLogEntry,
    UserUpdateAdmin,
)
from backend.auth import get_current_admin_user
from backend.services import (
    get_admin_stats,
    get_user_reservations,
    get_reservations_by_day,
    get_top_slots,
)
from backend.audit import log_action

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/stats", response_model=AdminStats)
async def get_admin_stats_endpoint(
    current_user=Depends(get_current_admin_user),
    db=Depends(get_db),
):
    """Get admin dashboard statistics"""
    stats = await get_admin_stats(db)
    return AdminStats(**stats)


@router.get("/users", response_model=List[UserResponse])
async def get_all_users(
    current_user=Depends(get_current_admin_user),
    db=Depends(get_db),
):
    """Get all users"""
    async with db.execute(
        "SELECT id, phone, name, email, is_admin, COALESCE(is_active, 1) as is_active FROM users ORDER BY created_at DESC"
    ) as cursor:
        rows = await cursor.fetchall()
        return [UserResponse(**dict(row)) for row in rows]


@router.patch("/users/{user_id}")
async def update_user(
    user_id: int,
    body: UserUpdateAdmin,
    current_user=Depends(get_current_admin_user),
    db=Depends(get_db),
):
    """Update user (e.g. disable/enable). Admin cannot disable self."""
    if current_user["id"] == user_id and body.is_active is False:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot disable your own account")
    if body.is_active is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update")
    async with db.execute("SELECT id FROM users WHERE id = ?", (user_id,)) as cursor:
        if not await cursor.fetchone():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    await db.execute(
        "UPDATE users SET is_active = ? WHERE id = ?",
        (1 if body.is_active else 0, user_id),
    )
    await log_action(db, "user_updated", current_user["id"], {"target_user_id": user_id, "is_active": body.is_active})
    await db.commit()
    return {"message": "User updated", "is_active": body.is_active}


@router.get("/analytics/reservations-by-day", response_model=List[ReservationsByDay])
async def analytics_reservations_by_day(
    days: int = 7,
    current_user=Depends(get_current_admin_user),
    db=Depends(get_db),
):

    """Reservation counts per day for the last N days."""
    if days < 1 or days > 90:
        days = 7
    data = await get_reservations_by_day(db, days)
    return [ReservationsByDay(**x) for x in data]


@router.get("/analytics/top-slots", response_model=List[TopSlot])
async def analytics_top_slots(
    limit: int = 10,
    current_user=Depends(get_current_admin_user),
    db=Depends(get_db),
):
    """Most used slots by reservation count."""
    if limit < 1 or limit > 50:
        limit = 10
    data = await get_top_slots(db, limit)
    return [TopSlot(**x) for x in data]


@router.get("/audit-log", response_model=List[AuditLogEntry])
async def get_audit_log(
    limit: int = 100,
    current_user=Depends(get_current_admin_user),
    db=Depends(get_db),
):
    """Get recent audit log entries."""
    if limit < 1 or limit > 500:
        limit = 100
    async with db.execute(
        "SELECT id, action, user_id, details, created_at FROM audit_log ORDER BY id DESC LIMIT ?",
        (limit,),
    ) as cursor:
        rows = await cursor.fetchall()
        return [AuditLogEntry(**dict(row)) for row in rows]

@router.get("/reservations", response_model=List[ReservationResponse])
async def get_all_reservations(
    current_user = Depends(get_current_admin_user),
    db = Depends(get_db)
):
    """Get all reservations"""
    async with db.execute("""
        SELECT 
            r.*,
            ps.slot_number,
            c.plate_number as car_plate
        FROM reservations r
        JOIN parking_slots ps ON r.slot_id = ps.id
        JOIN cars c ON r.car_id = c.id
        ORDER BY r.created_at DESC
    """) as cursor:
        rows = await cursor.fetchall()
        return [ReservationResponse(**dict(row)) for row in rows]
