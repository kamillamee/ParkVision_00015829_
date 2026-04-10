"""Test server startup and diagnose issues"""
import sys
import traceback
from pathlib import Path

print("=" * 60)
print("Testing Smart Vision System Server Startup")
print("=" * 60)
print()

# Test 1: Check Python version
print("1. Python Version:")
print(f"   {sys.version}")
print()

# Test 2: Check imports
print("2. Testing Imports...")
try:
    import fastapi
    print("   ✓ fastapi")
except ImportError as e:
    print(f"   ✗ fastapi - {e}")
    sys.exit(1)

try:
    import uvicorn
    print("   ✓ uvicorn")
except ImportError as e:
    print(f"   ✗ uvicorn - {e}")
    sys.exit(1)

try:
    import aiosqlite
    print("   ✓ aiosqlite")
except ImportError as e:
    print(f"   ✗ aiosqlite - {e}")
    sys.exit(1)

try:
    from backend.config import HOST, PORT, DEBUG
    print(f"   ✓ backend.config (HOST={HOST}, PORT={PORT}, DEBUG={DEBUG})")
except Exception as e:
    print(f"   ✗ backend.config - {e}")
    traceback.print_exc()
    sys.exit(1)

# Test 3: Check database
print("\n3. Checking Database...")
try:
    from backend.config import DATABASE_PATH
    db_dir = DATABASE_PATH.parent
    if not db_dir.exists():
        db_dir.mkdir(parents=True, exist_ok=True)
        print(f"   ✓ Created database directory: {db_dir}")
    else:
        print(f"   ✓ Database directory exists: {db_dir}")
    
    if DATABASE_PATH.exists():
        print(f"   ✓ Database file exists: {DATABASE_PATH}")
    else:
        print(f"   ⚠ Database file not found (will be created on first run)")
except Exception as e:
    print(f"   ✗ Database check failed - {e}")
    traceback.print_exc()

# Test 4: Try importing app
print("\n4. Testing FastAPI App Import...")
try:
    from backend.app import app
    print("   ✓ FastAPI app imported successfully")
    print(f"   ✓ App title: {app.title}")
except Exception as e:
    print(f"   ✗ Failed to import app - {e}")
    traceback.print_exc()
    sys.exit(1)

# Test 5: Check routes
print("\n5. Checking Routes...")
try:
    routes = [route.path for route in app.routes]
    print(f"   ✓ Found {len(routes)} routes")
    print(f"   ✓ Sample routes: {routes[:5]}")
except Exception as e:
    print(f"   ✗ Route check failed - {e}")

# Test 6: Try to start server (non-blocking test)
print("\n6. Testing Server Configuration...")
try:
    import uvicorn
    config = uvicorn.Config(
        app=app,
        host=HOST,
        port=PORT,
        log_level="info"
    )
    print(f"   ✓ Server config created successfully")
    print(f"   ✓ Will run on: http://{HOST}:{PORT}")
except Exception as e:
    print(f"   ✗ Server config failed - {e}")
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
print("✅ All checks passed! Server should start successfully.")
print("=" * 60)
print("\nTo start the server, run:")
print("  python run.py")
print("\nOr use:")
print("  .\\start_server.bat")
print("  .\\start_server.ps1")
