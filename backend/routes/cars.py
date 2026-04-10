"""Cars routes"""
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
import aiosqlite
from backend.database import get_db
from backend.models import CarCreate, CarResponse
from backend.auth import get_current_user
from backend.services import get_user_cars

router = APIRouter(prefix="/api/cars", tags=["cars"])

@router.get("/", response_model=List[CarResponse])
async def get_my_cars(
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Get current user's cars"""
    cars = await get_user_cars(db, current_user["id"])
    return [CarResponse(**car) for car in cars]

@router.post("/", response_model=CarResponse)
async def add_car(
    car_data: CarCreate,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Add a new car"""
    async with db.execute("""
        INSERT INTO cars (user_id, plate_number, brand, model, color)
        VALUES (?, ?, ?, ?, ?)
    """, (
        current_user["id"],
        car_data.plate_number,
        car_data.brand,
        car_data.model,
        car_data.color
    )) as cursor:
        car_id = getattr(cursor, "lastrowid", None)
    if car_id is None:
        async with db.execute(
            "SELECT id FROM cars WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (current_user["id"],),
        ) as cursor:
            row = await cursor.fetchone()
            car_id = row["id"] if row else None
    if car_id is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create car"
        )
    await db.commit()

    # Get created car
    async with db.execute(
        "SELECT * FROM cars WHERE id = ?",
        (car_id,)
    ) as cursor:
        car_row = await cursor.fetchone()
        return CarResponse(**dict(car_row))

@router.put("/{car_id}", response_model=CarResponse)
async def update_car(
    car_id: int,
    car_data: CarCreate,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Update a car"""
    # Verify car belongs to user
    async with db.execute(
        "SELECT id FROM cars WHERE id = ? AND user_id = ?",
        (car_id, current_user["id"])
    ) as cursor:
        if not await cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Car not found"
            )
    
    # Update car
    async with db.execute("""
        UPDATE cars 
        SET plate_number = ?, brand = ?, model = ?, color = ?
        WHERE id = ?
    """, (
        car_data.plate_number,
        car_data.brand,
        car_data.model,
        car_data.color,
        car_id
    )):
        pass
    
    await db.commit()
    
    # Get updated car
    async with db.execute(
        "SELECT * FROM cars WHERE id = ?",
        (car_id,)
    ) as cursor:
        car_row = await cursor.fetchone()
        return CarResponse(**dict(car_row))

@router.delete("/{car_id}")
async def delete_car(
    car_id: int,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Delete a car"""
    # Verify car belongs to user
    async with db.execute(
        "SELECT id FROM cars WHERE id = ? AND user_id = ?",
        (car_id, current_user["id"])
    ) as cursor:
        if not await cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Car not found"
            )
    
    # Delete car
    async with db.execute("DELETE FROM cars WHERE id = ?", (car_id,)):
        pass
    
    await db.commit()
    
    return {"message": "Car deleted successfully"}
