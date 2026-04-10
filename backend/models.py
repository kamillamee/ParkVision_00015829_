from pydantic import BaseModel, Field, EmailStr, ConfigDict
from typing import Optional, List
from datetime import datetime

# Authentication Models
class UserRegister(BaseModel):
    phone: str = Field(..., min_length=10, max_length=15, description="Phone number (e.g., +1234567890)")
    password: str = Field(..., min_length=6, max_length=100, description="Password (min 6 characters)")
    name: Optional[str] = Field(None, max_length=100)
    email: Optional[EmailStr] = None

class UserLogin(BaseModel):
    phone: str
    password: str

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    phone: str
    name: Optional[str]
    email: Optional[str]
    is_admin: bool
    is_active: bool = True

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

class PasswordChange(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=6)

class CarCreate(BaseModel):
    plate_number: str = Field(..., min_length=2, max_length=20, description="License plate number")
    brand: Optional[str] = Field(None, max_length=50)
    model: Optional[str] = Field(None, max_length=50)
    color: Optional[str] = Field(None, max_length=30)

class CarResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    plate_number: str
    brand: Optional[str]
    model: Optional[str]
    color: Optional[str]
    created_at: str

# Slot Models
class SlotStatus(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slot_number: str
    zone: Optional[str]
    is_occupied: bool
    last_updated: str
    occupation_source: Optional[str] = None
    lot_id: Optional[int] = None

class SlotUpdate(BaseModel):
    slot_number: str
    is_occupied: bool

class ParkingLotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    address: Optional[str] = None
    latitude: float
    longitude: float
    slots_total: int = 0
    slots_available: int = 0
    is_live: bool = False

class SensorReadingItem(BaseModel):
    slot_number: str = Field(..., min_length=1, max_length=20)
    source: str = Field(..., description="e.g. ultrasonic, ir, magnetic")
    is_occupied: bool

class SensorReadingsBatch(BaseModel):
    readings: List[SensorReadingItem] = Field(..., min_length=1, max_length=500)

class SlotStats(BaseModel):
    total: int
    occupied: int
    available: int
    occupancy_rate: float

class ReservationCreate(BaseModel):
    car_id: int = Field(..., gt=0, description="Car ID must be positive")
    slot_id: int = Field(..., gt=0, description="Slot ID must be positive")
    start_time: str = Field(..., description="Start time in ISO format (YYYY-MM-DDTHH:MM:SS)")
    end_time: str = Field(..., description="End time in ISO format (YYYY-MM-DDTHH:MM:SS)")

class ReservationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    car_id: int
    slot_id: int
    slot_number: str
    car_plate: str
    start_time: str
    end_time: str
    status: str
    payment_status: str
    amount: Optional[float]
    created_at: str

class PaymentConfirm(BaseModel):
    reservation_id: int
    payment_method_id: Optional[int] = None


class PaymentMethodCreate(BaseModel):
    card_number: str = Field(..., min_length=13, max_length=19)
    expiry: str = Field(..., description="MM/YY")
    cardholder_name: str = Field("", max_length=100)
    is_default: bool = False


class PaymentMethodResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    user_id: int
    type: str
    brand: str
    last4: str
    expiry_month: Optional[int]
    expiry_year: Optional[int]
    cardholder_name: str
    is_default: bool
    created_at: str

class AdminStats(BaseModel):
    total_users: int
    total_cars: int
    total_slots: int
    occupied_slots: int
    total_reservations: int
    active_reservations: int


class ReservationsByDay(BaseModel):
    day: str
    count: int


class TopSlot(BaseModel):
    slot_number: str
    zone: Optional[str]
    reservation_count: int


class AuditLogEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    action: str
    user_id: Optional[int]
    details: Optional[str]
    created_at: str


class UserUpdateAdmin(BaseModel):
    is_active: Optional[bool] = None
