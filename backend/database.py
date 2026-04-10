import aiosqlite
from pathlib import Path
from backend.config import DATABASE_PATH

DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)

async def get_db():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db

async def init_db():
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                name TEXT,
                email TEXT,
                is_admin INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS cars (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                plate_number TEXT NOT NULL,
                brand TEXT,
                model TEXT,
                color TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS parking_lots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                address TEXT,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute(
            """INSERT INTO parking_lots (name, address, latitude, longitude)
               SELECT 'Main Parking Tashkent', 'Toshkent sh., Amir Temur ko''chasi', 41.2995, 69.2401
               WHERE NOT EXISTS (SELECT 1 FROM parking_lots LIMIT 1)"""
        )

        await db.execute("""
            CREATE TABLE IF NOT EXISTS parking_slots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slot_number TEXT UNIQUE NOT NULL,
                zone TEXT,
                is_occupied INTEGER DEFAULT 0,
                last_updated TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                car_id INTEGER NOT NULL,
                slot_id INTEGER NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                payment_status TEXT DEFAULT 'pending',
                amount REAL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (car_id) REFERENCES cars(id) ON DELETE CASCADE,
                FOREIGN KEY (slot_id) REFERENCES parking_slots(id) ON DELETE CASCADE
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS payment_methods (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                type TEXT NOT NULL DEFAULT 'credit_card',
                brand TEXT,
                last4 TEXT,
                expiry_month INTEGER,
                expiry_year INTEGER,
                cardholder_name TEXT,
                is_default INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action TEXT NOT NULL,
                user_id INTEGER,
                details TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        await db.execute("""
            CREATE TABLE IF NOT EXISTS sensor_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slot_number TEXT NOT NULL,
                source TEXT NOT NULL,
                is_occupied INTEGER NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        await db.commit()

        try:
            async with db.execute("PRAGMA table_info(users)") as cursor:
                rows = await cursor.fetchall()
            cols = [r[1] for r in rows]
            if "is_active" not in cols:
                await db.execute("ALTER TABLE users ADD COLUMN is_active INTEGER DEFAULT 1")
                await db.commit()
        except Exception:
            pass

        try:
            async with db.execute("PRAGMA table_info(parking_slots)") as cursor:
                rows = await cursor.fetchall()
            cols = [r[1] for r in rows]
            if "occupation_source" not in cols:
                await db.execute(
                    "ALTER TABLE parking_slots ADD COLUMN occupation_source TEXT DEFAULT 'vision'"
                )
                await db.commit()
        except Exception:
            pass

        try:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS parking_lots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    address TEXT,
                    latitude REAL NOT NULL,
                    longitude REAL NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await db.execute(
                """INSERT INTO parking_lots (name, address, latitude, longitude)
                   SELECT 'Main Parking Tashkent', 'Toshkent sh., Amir Temur ko''chasi', 41.2995, 69.2401
                   WHERE NOT EXISTS (SELECT 1 FROM parking_lots LIMIT 1)"""
            )
            await db.commit()
        except Exception:
            pass
        try:
            async with db.execute("PRAGMA table_info(parking_slots)") as cursor:
                rows = await cursor.fetchall()
            cols = [r[1] for r in rows]
            if "lot_id" not in cols:
                await db.execute(
                    "ALTER TABLE parking_slots ADD COLUMN lot_id INTEGER REFERENCES parking_lots(id) ON DELETE SET NULL"
                )
                await db.commit()
                async with db.execute("SELECT id FROM parking_lots LIMIT 1") as cursor:
                    row = await cursor.fetchone()
                if row is not None:
                    await db.execute("UPDATE parking_slots SET lot_id = ? WHERE lot_id IS NULL", (row["id"],))
                    await db.commit()
        except Exception:
            pass

        try:
            await db.execute(
                "UPDATE parking_lots SET name='Main Parking Tashkent', address='Toshkent sh., Amir Temur ko''chasi', latitude=41.2995, longitude=69.2401 WHERE latitude > 50 AND longitude < 80"
            )
            await db.commit()
        except Exception:
            pass

        try:
            async with db.execute("PRAGMA table_info(parking_lots)") as cursor:
                rows = await cursor.fetchall()
            cols = [r[1] for r in rows]
            if "is_live" not in cols:
                await db.execute("ALTER TABLE parking_lots ADD COLUMN is_live INTEGER DEFAULT 0")
                await db.commit()
                await db.execute(
                    "UPDATE parking_lots SET is_live = 1 WHERE name LIKE '%Tashkent%' OR id = (SELECT id FROM parking_lots LIMIT 1)"
                )
                await db.commit()
        except Exception:
            pass

        try:
            await db.execute(
                """UPDATE parking_lots SET
                   name = 'British School of Tashkent — parking',
                   address = 'British School of Tashkent, Yunusobod, Tashkent',
                   latitude = 41.3670,
                   longitude = 69.2720,
                   is_live = 1
                   WHERE id = 1"""
            )
            await db.commit()
        except Exception:
            pass
        try:
            async with db.execute(
                "SELECT id FROM parking_lots WHERE name = 'Westminster University Parking' LIMIT 1"
            ) as c:
                exists_w = await c.fetchone()
            if not exists_w:
                await db.execute(
                    """INSERT INTO parking_lots (name, address, latitude, longitude, is_live)
                       VALUES ('Westminster University Parking',
                               'Westminster International University in Tashkent',
                               41.3280, 69.2885, 1)"""
                )
                await db.commit()
        except Exception:
            pass

        try:
            async with db.execute("PRAGMA table_info(reservations)") as cursor:
                rows = await cursor.fetchall()
            cols = [r[1] for r in rows]
            if "payment_method_id" not in cols:
                await db.execute(
                    "ALTER TABLE reservations ADD COLUMN payment_method_id INTEGER REFERENCES payment_methods(id) ON DELETE SET NULL"
                )
                await db.commit()
        except Exception:
            pass
