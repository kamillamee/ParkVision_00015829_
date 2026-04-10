"""Authentication routes"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from typing import Optional
import aiosqlite
from backend.database import get_db
from backend.models import UserRegister, UserLogin, TokenResponse, UserResponse, PasswordChange
from backend.config import AUTH_RATE_LIMIT
from backend.limiter import limiter
from pydantic import BaseModel
from backend.auth import (
    get_password_hash, verify_password, create_access_token,
    get_current_user, security
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None

@router.post("/register", response_model=TokenResponse)
@limiter.limit(AUTH_RATE_LIMIT)
async def register(request: Request, user_data: UserRegister, db = Depends(get_db)):
    """Register a new user"""
    # Validate phone format (basic check)
    phone_clean = user_data.phone.strip().replace(" ", "").replace("-", "")
    if not phone_clean.replace("+", "").isdigit():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid phone number format"
        )
    
    # Check if user exists
    async with db.execute(
        "SELECT id FROM users WHERE phone = ?",
        (phone_clean,)
    ) as cursor:
        if await cursor.fetchone():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Phone number already registered"
            )
    
    # Create user
    password_hash = get_password_hash(user_data.password)
    await db.execute(
        """INSERT INTO users (phone, password_hash, name, email)
           VALUES (?, ?, ?, ?)""",
        (phone_clean, password_hash, user_data.name, user_data.email)
    )
    
    await db.commit()
    
    # Get created user
    async with db.execute(
        "SELECT id, phone, name, email, is_admin FROM users WHERE phone = ?",
        (phone_clean,)
    ) as cursor:
        user_row = await cursor.fetchone()
        if not user_row:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create user "
            )
        user = {
            "id": user_row["id"],
            "phone": user_row["phone"],
            "name": user_row["name"],
            "email": user_row["email"],
            "is_admin": bool(user_row["is_admin"])
        }
    
    # Create token
    access_token = create_access_token(data={"sub": user["id"]})
    
    return TokenResponse(
        access_token=access_token,
        user=UserResponse(**user)
    )

@router.post("/login", response_model=TokenResponse)
@limiter.limit(AUTH_RATE_LIMIT)
async def login(request: Request, credentials: UserLogin, db = Depends(get_db)):
    """Login user"""
    # Clean phone number (same as registration)
    phone_clean = credentials.phone.strip().replace(" ", "").replace("-", "")
    
    async with db.execute(
        "SELECT id, phone, password_hash, name, email, is_admin, COALESCE(is_active, 1) as is_active FROM users WHERE phone = ?",
        (phone_clean,)
    ) as cursor:
        user_row = await cursor.fetchone()
        if not user_row or not verify_password(credentials.password, user_row["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect phone or password"
            )
        if not user_row["is_active"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is disabled. Contact support."
            )
        user = {
            "id": user_row["id"],
            "phone": user_row["phone"],
            "name": user_row["name"],
            "email": user_row["email"],
            "is_admin": bool(user_row["is_admin"])
        }
    
    access_token = create_access_token(data={"sub": user["id"]})
    
    return TokenResponse(
        access_token=access_token,
        user=UserResponse(**user)
    )

@router.get("/me", response_model=UserResponse)
async def get_me(current_user = Depends(get_current_user)):
    """Get current user profile"""
    return UserResponse(**current_user)

@router.put("/me", response_model=UserResponse)
async def update_me(
    user_update: UserUpdate,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Update current user profile"""
    updates = []
    params = []
    
    if user_update.name is not None:
        updates.append("name = ?")
        params.append(user_update.name)
    if user_update.email is not None:
        updates.append("email = ?")
        params.append(user_update.email)
    
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update"
        )
    
    params.append(current_user["id"])
    query = f"UPDATE users SET {', '.join(updates)} WHERE id = ?"
    
    async with db.execute(query, params):
        pass
    await db.commit()
    
    # Get updated user (include is_active for UserResponse)
    async with db.execute(
        "SELECT id, phone, name, email, is_admin, COALESCE(is_active, 1) as is_active FROM users WHERE id = ?",
        (current_user["id"],)
    ) as cursor:
        user_row = await cursor.fetchone()
        if not user_row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return UserResponse(**dict(user_row))

@router.post("/change-password")
async def change_password(
    password_data: PasswordChange,
    current_user = Depends(get_current_user),
    db = Depends(get_db)
):
    """Change user password"""
    # Verify old password
    async with db.execute(
        "SELECT password_hash FROM users WHERE id = ?",
        (current_user["id"],)
    ) as cursor:
        user_row = await cursor.fetchone()
        if not user_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        if not verify_password(password_data.old_password, user_row["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Incorrect old password"
            )
    
    # Update password
    new_hash = get_password_hash(password_data.new_password)
    async with db.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (new_hash, current_user["id"])
    ):
        pass
    await db.commit()
    
    return {"message": "Password updated successfully"}
