import asyncio
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
import aiosqlite
from backend.database import get_db
from backend.models import ReservationCreate, ReservationResponse, PaymentConfirm
from backend.auth import get_current_user
from backend.services import check_slot_availability, get_user_reservations
from backend.audit import log_action
from backend.notifications import (
    notify_reservation_created,
    notify_payment_confirmed,
    notify_reservation_cancelled,
)
from datetime import datetime, timezone

router = APIRouter(prefix="/api/reservations", tags=["reservations"])

@router.get("/my-reservations", response_model=List[ReservationResponse])
async def get_my_reservations(
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    reservations = await get_user_reservations(db, current_user["id"])
    return [ReservationResponse(**r) for r in reservations]

@router.post("/create", response_model=ReservationResponse)
async def create_reservation(
    reservation_data: ReservationCreate,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    async with db.execute(
        "SELECT id FROM cars WHERE id = ? AND user_id = ?",
        (reservation_data.car_id, current_user["id"])
    ) as cursor:
        if not await cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Car not found"
            )

    async with db.execute(
        "SELECT id, slot_number FROM parking_slots WHERE id = ?",
        (reservation_data.slot_id,)
    ) as cursor:
        slot_row = await cursor.fetchone()
        if not slot_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Parking slot not found"
            )
        slot_number = slot_row["slot_number"]

    is_available = await check_slot_availability(
        db, reservation_data.slot_id,
        reservation_data.start_time, reservation_data.end_time
    )

    if not is_available:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Slot is not available for the selected time period"
        )

    try:
        start_str = reservation_data.start_time.strip()
        end_str = reservation_data.end_time.strip()

        if 'T' in start_str and start_str.count(':') == 1:
            start_str = start_str + ':00'
        if 'T' in end_str and end_str.count(':') == 1:
            end_str = end_str + ':00'

        if 'Z' in start_str:
            start_str = start_str.replace('Z', '')
        if '+' in start_str:
            start_str = start_str.split('+')[0]
        if 'Z' in end_str:
            end_str = end_str.replace('Z', '')
        if '+' in end_str:
            end_str = end_str.split('+')[0]

        start = datetime.fromisoformat(start_str)
        end = datetime.fromisoformat(end_str)
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)

    except (ValueError, IndexError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid date format. Use format: YYYY-MM-DDTHH:MM or YYYY-MM-DDTHH:MM:SS"
        )

    if end <= start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="End time must be after start time"
        )

    if start < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Start time must be in the future"
        )

    hours = (end - start).total_seconds() / 3600
    amount = max(round(hours * 5, 2), 2.0)

    async with db.execute("""
        INSERT INTO reservations
        (user_id, car_id, slot_id, start_time, end_time, status, amount)
        VALUES (?, ?, ?, ?, ?, 'pending', ?)
    """, (
        current_user["id"],
        reservation_data.car_id,
        reservation_data.slot_id,
        reservation_data.start_time,
        reservation_data.end_time,
        amount
    )) as cursor:
        reservation_id = getattr(cursor, "lastrowid", None)
    if reservation_id is None:
        async with db.execute(
            "SELECT id FROM reservations WHERE user_id = ? AND slot_id = ? ORDER BY id DESC LIMIT 1",
            (current_user["id"], reservation_data.slot_id),
        ) as cursor:
            row = await cursor.fetchone()
            reservation_id = row["id"] if row else 0

    await log_action(db, "reservation_created", current_user["id"], {
        "reservation_id": reservation_id,
        "slot_number": slot_number,
        "start_time": reservation_data.start_time,
        "end_time": reservation_data.end_time,
    })
    await db.commit()

    async with db.execute(
        "SELECT plate_number FROM cars WHERE id = ?",
        (reservation_data.car_id,)
    ) as cursor:
        car_plate = (await cursor.fetchone())["plate_number"]

    asyncio.create_task(asyncio.to_thread(
        notify_reservation_created,
        current_user.get("email"),
        current_user.get("phone"),
        slot_number,
        car_plate,
        reservation_data.start_time,
        reservation_data.end_time,
        amount,
    ))

    return ReservationResponse(
        id=reservation_id,
        user_id=current_user["id"],
        car_id=reservation_data.car_id,
        slot_id=reservation_data.slot_id,
        slot_number=slot_number,
        car_plate=car_plate,
        start_time=reservation_data.start_time,
        end_time=reservation_data.end_time,
        status="pending",
        payment_status="pending",
        amount=amount,
        created_at=datetime.now(timezone.utc).isoformat()
    )

@router.post("/confirm-payment")
async def confirm_payment(
    payment_data: PaymentConfirm,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    async with db.execute(
        "SELECT * FROM reservations WHERE id = ? AND user_id = ?",
        (payment_data.reservation_id, current_user["id"])
    ) as cursor:
        reservation = await cursor.fetchone()
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reservation not found"
            )

        if reservation["payment_status"] == "paid":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation already paid"
            )

    pm_id = payment_data.payment_method_id
    if pm_id is not None:
        async with db.execute(
            "SELECT id FROM payment_methods WHERE id = ? AND user_id = ?",
            (pm_id, current_user["id"]),
        ) as pm_cursor:
            if not await pm_cursor.fetchone():
                pm_id = None
    async with db.execute("""
        UPDATE reservations
        SET payment_status = 'paid', status = 'active', payment_method_id = ?
        WHERE id = ?
    """, (pm_id, payment_data.reservation_id)):
        pass

    await db.commit()

    async with db.execute(
        "SELECT ps.slot_number, r.start_time, r.end_time FROM reservations r "
        "JOIN parking_slots ps ON r.slot_id = ps.id WHERE r.id = ?",
        (payment_data.reservation_id,),
    ) as cursor:
        row = await cursor.fetchone()
        slot_number = row["slot_number"] if row else ""
        start_time = row["start_time"] if row else ""
        end_time = row["end_time"] if row else ""

    asyncio.create_task(asyncio.to_thread(
        notify_payment_confirmed,
        current_user.get("email"),
        current_user.get("phone"),
        slot_number,
        start_time,
        end_time,
    ))

    return {"message": "Payment confirmed. Reservation activated."}

@router.post("/{reservation_id}/cancel")
async def cancel_reservation(
    reservation_id: int,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    async with db.execute(
        "SELECT * FROM reservations WHERE id = ? AND user_id = ?",
        (reservation_id, current_user["id"])
    ) as cursor:
        reservation = await cursor.fetchone()
        if not reservation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reservation not found"
            )

        if reservation["status"] == "cancelled":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Reservation already cancelled"
            )

    async with db.execute("""
        UPDATE reservations
        SET status = 'cancelled'
        WHERE id = ?
    """, (reservation_id,)):
        pass

    await log_action(db, "reservation_cancelled", current_user["id"], {
        "reservation_id": reservation_id,
        "slot_id": reservation["slot_id"],
    })
    await db.commit()

    async with db.execute(
        "SELECT slot_number FROM parking_slots WHERE id = ?",
        (reservation["slot_id"],),
    ) as cursor:
        row = await cursor.fetchone()
        slot_number = row["slot_number"] if row else ""

    asyncio.create_task(asyncio.to_thread(
        notify_reservation_cancelled,
        current_user.get("email"),
        current_user.get("phone"),
        slot_number,
        reservation["start_time"],
    ))

    return {"message": "Reservation cancelled successfully"}
