"""Test all imports to find the issue"""
import sys
import traceback

print("Testing imports step by step...")
print("=" * 60)

try:
    print("1. Testing basic imports...")
    import uvicorn
    print("   ✓ uvicorn")
    
    import fastapi
    print("   ✓ fastapi")
    
    import aiosqlite
    print("   ✓ aiosqlite")
    
    print("\n2. Testing backend.config...")
    from backend.config import HOST, PORT, DEBUG, DATABASE_PATH
    print(f"   ✓ HOST={HOST}, PORT={PORT}, DEBUG={DEBUG}")
    print(f"   ✓ DATABASE_PATH={DATABASE_PATH}")
    
    print("\n3. Testing backend.database...")
    from backend.database import init_db, get_db
    print("   ✓ database module")
    
    print("\n4. Testing backend.auth...")
    from backend.auth import get_password_hash
    print("   ✓ auth module")
    
    print("\n5. Testing backend.models...")
    from backend.models import UserRegister
    print("   ✓ models module")
    
    print("\n6. Testing backend.routes...")
    from backend.routes import auth, slots, reservations, cars, admin
    print("   ✓ all route modules")
    
    print("\n7. Testing backend.app...")
    from backend.app import app
    print("   ✓ FastAPI app imported!")
    print(f"   ✓ App title: {app.title}")
    print(f"   ✓ Routes count: {len(app.routes)}")
    
    print("\n" + "=" * 60)
    print("✅ All imports successful!")
    print("=" * 60)
    
except Exception as e:
    print(f"\n❌ ERROR at step: {e}")
    print("\nFull traceback:")
    traceback.print_exc()
    sys.exit(1)
