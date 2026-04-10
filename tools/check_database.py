"""Check database connection and user accounts"""
import asyncio
import sys
from pathlib import Path
from backend.config import DATABASE_PATH
import aiosqlite

async def check_database():
    """Check database and list users"""
    print("=" * 60)
    print("Database Connection Check")
    print("=" * 60)
    print()
    
    # Check if database exists
    print(f"1. Database File:")
    print(f"   Path: {DATABASE_PATH}")
    if DATABASE_PATH.exists():
        size = DATABASE_PATH.stat().st_size
        print(f"   ✓ Exists ({size} bytes)")
    else:
        print(f"   ✗ Not found!")
        print("   Run: python backend/init_db.py")
        return
    print()
    
    # Try to connect
    print("2. Database Connection:")
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            print("   ✓ Connected successfully")
            
            # Check tables
            print()
            print("3. Checking Tables:")
            async with db.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' 
                ORDER BY name
            """) as cursor:
                tables = await cursor.fetchall()
                table_names = [row['name'] for row in tables]
                print(f"   Found {len(table_names)} tables:")
                for table in table_names:
                    print(f"     - {table}")
            print()
            
            # Check users
            print("4. User Accounts:")
            async with db.execute("""
                SELECT id, phone, name, email, is_admin, created_at 
                FROM users 
                ORDER BY created_at DESC
            """) as cursor:
                users = await cursor.fetchall()
                if users:
                    print(f"   Found {len(users)} user(s):")
                    print()
                    for user in users:
                        admin_status = "ADMIN" if user['is_admin'] else "User"
                        print(f"   ID: {user['id']}")
                        print(f"   Phone: {user['phone']}")
                        print(f"   Name: {user['name'] or 'N/A'}")
                        print(f"   Email: {user['email'] or 'N/A'}")
                        print(f"   Type: {admin_status}")
                        print(f"   Created: {user['created_at']}")
                        print()
                else:
                    print("   ⚠ No users found in database")
                    print("   Run: python backend/init_db.py")
            print()
            
            # Check cars
            print("5. Cars:")
            async with db.execute("SELECT COUNT(*) as count FROM cars") as cursor:
                car_count = (await cursor.fetchone())['count']
                print(f"   Total cars: {car_count}")
            print()
            
            # Check reservations
            print("6. Reservations:")
            async with db.execute("SELECT COUNT(*) as count FROM reservations") as cursor:
                res_count = (await cursor.fetchone())['count']
                print(f"   Total reservations: {res_count}")
            print()
            
            # Check parking slots
            print("7. Parking Slots:")
            async with db.execute("SELECT COUNT(*) as count FROM parking_slots") as cursor:
                slot_count = (await cursor.fetchone())['count']
                print(f"   Total slots: {slot_count}")
            
    except Exception as e:
        print(f"   ✗ Connection failed: {e}")
        import traceback
        traceback.print_exc()
        return
    
    print()
    print("=" * 60)
    print("Database check complete!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(check_database())
