"""Payment methods routes"""
import re
import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from backend.auth import get_current_user
from backend.config import DATABASE_PATH
from backend.models import PaymentMethodCreate, PaymentMethodResponse
from backend.audit import log_action

router = APIRouter(prefix="/api/payments", tags=["payments"])


def detect_card_brand(number: str) -> str:
    """Detect card brand from first digits"""
    n = re.sub(r"\D", "", number)
    if n.startswith("4"):
        return "visa"
    if n.startswith(("51", "52", "53", "54", "55")) or (len(n) >= 2 and n[:2] in ("22", "23", "24", "25", "26", "27")):
        return "mastercard"
    if n.startswith(("34", "37")):
        return "amex"
    return "card"


@router.get("/methods", response_model=List[PaymentMethodResponse])
async def get_payment_methods(current_user=Depends(get_current_user)):
    """Get current user's payment methods"""
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT id, user_id, type, brand, last4, expiry_month, expiry_year, cardholder_name, is_default, created_at
                   FROM payment_methods WHERE user_id = ? ORDER BY is_default DESC, created_at DESC""",
                (current_user["id"],),
            ) as cursor:
                rows = await cursor.fetchall()
        return [
            PaymentMethodResponse(
                id=r["id"],
                user_id=r["user_id"],
                type=r["type"] or "credit_card",
                brand=r["brand"] or "",
                last4=r["last4"] or "",
                expiry_month=r["expiry_month"],
                expiry_year=r["expiry_year"],
                cardholder_name=r["cardholder_name"] or "",
                is_default=bool(r["is_default"]),
                created_at=str(r["created_at"]) if r["created_at"] else "",
            )
            for r in rows
        ]
    except Exception as e:
        import logging
        logging.exception("get_payment_methods error")
        raise HTTPException(status_code=500, detail="Failed to load payment methods")


@router.post("/methods", response_model=PaymentMethodResponse)
async def add_payment_method(
    data: PaymentMethodCreate,
    current_user=Depends(get_current_user),
):
    """Add a new payment method (card). Only safe data is stored."""
    import aiosqlite
    from backend.config import DATABASE_PATH

    # Extract last4 and brand from card number (simulated - in production use Stripe/etc.)
    card_num = re.sub(r"\D", "", data.card_number)
    if len(card_num) < 4:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid card number",
        )
    last4 = card_num[-4:]
    brand = detect_card_brand(card_num)

    # Validate expiry
    exp = re.sub(r"\D", "", data.expiry or "")
    if len(exp) >= 4:
        month = int(exp[:2])
        year = int(exp[2:4])  # YY
        if month < 1 or month > 12:
            raise HTTPException(status_code=400, detail="Invalid expiry month")
        expiry_month = month
        expiry_year = 2000 + year
    else:
        raise HTTPException(status_code=400, detail="Invalid expiry format (MM/YY)")

    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        # If this is first card or user chose default, set as default
        async with db.execute(
            "SELECT COUNT(*) as c FROM payment_methods WHERE user_id = ?",
            (current_user["id"],),
        ) as cursor:
            count = (await cursor.fetchone())["c"]
        is_default = 1 if count == 0 or data.is_default else 0

        if is_default:
            await db.execute(
                "UPDATE payment_methods SET is_default = 0 WHERE user_id = ?",
                (current_user["id"],),
            )

        cursor = await db.execute(
            """INSERT INTO payment_methods (user_id, type, brand, last4, expiry_month, expiry_year, cardholder_name, is_default)
               VALUES (?, 'credit_card', ?, ?, ?, ?, ?, ?)""",
            (current_user["id"], brand, last4, expiry_month, expiry_year, data.cardholder_name or "", is_default),
        )
        rowid = cursor.lastrowid
        await log_action(db, "payment_method_added", current_user["id"], {"method_id": rowid, "brand": brand})
        await db.commit()

    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, user_id, type, brand, last4, expiry_month, expiry_year, cardholder_name, is_default, created_at FROM payment_methods WHERE id = ?",
            (rowid,),
        ) as cursor:
            row = await cursor.fetchone()

    return PaymentMethodResponse(
        id=row["id"],
        user_id=row["user_id"],
        type=row["type"],
        brand=row["brand"] or "",
        last4=row["last4"] or "",
        expiry_month=row["expiry_month"],
        expiry_year=row["expiry_year"],
        cardholder_name=row["cardholder_name"] or "",
        is_default=bool(row["is_default"]),
        created_at=row["created_at"],
    )


@router.delete("/methods/{method_id}")
async def delete_payment_method(
    method_id: int,
    current_user=Depends(get_current_user),
):
    """Remove a payment method"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, is_default FROM payment_methods WHERE id = ? AND user_id = ?",
            (method_id, current_user["id"]),
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Payment method not found")

        await db.execute("DELETE FROM payment_methods WHERE id = ?", (method_id,))
        if row["is_default"]:
            async with db.execute(
                "SELECT id FROM payment_methods WHERE user_id = ? LIMIT 1",
                (current_user["id"],),
            ) as c2:
                first = await c2.fetchone()
            if first:
                await db.execute(
                    "UPDATE payment_methods SET is_default = 1 WHERE id = ?",
                    (first["id"],),
                )
        await db.commit()

    return {"message": "Payment method deleted"}


@router.patch("/methods/{method_id}/default")
async def set_default_payment_method(
    method_id: int,
    current_user=Depends(get_current_user),
):
    """Set payment method as default"""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT id FROM payment_methods WHERE id = ? AND user_id = ?",
            (method_id, current_user["id"]),
        ) as cursor:
            if not await cursor.fetchone():
                raise HTTPException(status_code=404, detail="Payment method not found")

        await db.execute(
            "UPDATE payment_methods SET is_default = 0 WHERE user_id = ?",
            (current_user["id"],),
        )
        await db.execute(
            "UPDATE payment_methods SET is_default = 1 WHERE id = ?",
            (method_id,),
        )
        await db.commit()

    return {"message": "Default payment method updated"}
