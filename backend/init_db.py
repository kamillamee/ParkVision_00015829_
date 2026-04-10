import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.database import init_db
from backend.auth import get_password_hash
import aiosqlite
from backend.config import DATABASE_PATH

async def create_admin_user():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            "SELECT id FROM users WHERE phone = ?",
            ("+1234567890",)
        ) as cursor:
            if await cursor.fetchone():
                print("OK: Admin user already exists")
                return

        password_hash = get_password_hash("admin123")
        async with db.execute(
            """INSERT INTO users (phone, password_hash, name, email, is_admin)
               VALUES (?, ?, ?, ?, ?)""",
            ("+1234567890", password_hash, "Admin User", "admin@smartvision.com", 1)
        ):
            pass

        await db.commit()
        print("OK: Admin user created:")
        print("   Phone: +1234567890")
        print("   Password: admin123")

async def main():
    print("INFO: Initializing Smart Vision Database...")

    await init_db()
    print("OK: Database tables created")

    await create_admin_user()

    print("\nOK: Database initialization complete.")
    print(f"INFO: Database location: {DATABASE_PATH}")

if __name__ == "__main__":
    asyncio.run(main())
