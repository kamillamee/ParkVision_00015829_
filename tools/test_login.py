"""Test login functionality"""
import asyncio
import sys
from pathlib import Path
from backend.config import DATABASE_PATH
from backend.auth import verify_password, get_password_hash
import aiosqlite

async def test_login():
    """Test login with a phone number"""
    print("=" * 60)
    print("Login Test")
    print("=" * 60)
    print()
    
    # Get phone number from user
    if len(sys.argv) > 1:
        test_phone = sys.argv[1]
    else:
        test_phone = input("Enter phone number to test: ").strip()
    
    print(f"Testing login for: {test_phone}")
    print()
    
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            db.row_factory = aiosqlite.Row
            
            # Clean phone number (same as in register route)
            phone_clean = test_phone.strip().replace(" ", "").replace("-", "")
            
            print(f"1. Looking for user with phone: '{phone_clean}'")
            print(f"   (Original input: '{test_phone}')")
            print()
            
            # Check all users first
            print("2. All users in database:")
            async with db.execute("""
                SELECT id, phone, name, email, is_admin 
                FROM users 
                ORDER BY id
            """) as cursor:
                users = await cursor.fetchall()
                if users:
                    for user in users:
                        match = "✓ MATCH" if user['phone'] == phone_clean else ""
                        print(f"   ID: {user['id']}, Phone: '{user['phone']}' {match}")
                else:
                    print("   No users found!")
            print()
            
            # Try to find the user
            async with db.execute("""
                SELECT id, phone, password_hash, name, email, is_admin 
                FROM users 
                WHERE phone = ?
            """, (phone_clean,)) as cursor:
                user_row = await cursor.fetchone()
                
                if user_row:
                    print(f"3. User found:")
                    print(f"   ID: {user_row['id']}")
                    print(f"   Phone: {user_row['phone']}")
                    print(f"   Name: {user_row['name']}")
                    print(f"   Email: {user_row['email']}")
                    print(f"   Admin: {bool(user_row['is_admin'])}")
                    print(f"   Password hash: {user_row['password_hash'][:20]}...")
                    print()
                    
                    # Test password
                    if len(sys.argv) > 2:
                        test_password = sys.argv[2]
                    else:
                        test_password = input("Enter password to test (or press Enter to skip): ").strip()
                    
                    if test_password:
                        print("4. Testing password:")
                        is_valid = verify_password(test_password, user_row['password_hash'])
                        if is_valid:
                            print("   ✓ Password is CORRECT")
                        else:
                            print("   ✗ Password is INCORRECT")
                            print()
                            print("   Note: If you're sure the password is correct,")
                            print("   the password hash might have been created with")
                            print("   a different algorithm or secret key.")
                else:
                    print(f"3. User NOT found with phone: '{phone_clean}'")
                    print()
                    print("   Possible issues:")
                    print("   - Phone number format mismatch")
                    print("   - User was created in a different database")
                    print("   - Phone number has extra spaces or characters")
                    print()
                    print("   Try checking all users above to see the exact format.")
                    
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_login())
