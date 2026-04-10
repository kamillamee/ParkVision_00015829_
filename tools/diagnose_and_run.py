"""Comprehensive diagnostic and server runner. Run from project root: python tools/diagnose_and_run.py"""
import sys
import os
import traceback
from pathlib import Path

# Ensure project root is on path and cwd
_project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_project_root))
os.chdir(_project_root)

print("=" * 70)
print("Smart Vision System - Diagnostic & Server Start")
print("=" * 70)
print()

# Step 1: Test Python
print("Step 1: Python Environment")
print(f"  Python: {sys.executable}")
print(f"  Version: {sys.version}")
print(f"  Working Directory: {os.getcwd()}")
print()

# Step 2: Test basic imports
print("Step 2: Testing Basic Imports")
try:
    import uvicorn
    print(f"  ✓ uvicorn {uvicorn.__version__}")
except Exception as e:
    print(f"  ✗ uvicorn: {e}")
    sys.exit(1)

try:
    import fastapi
    print(f"  ✓ fastapi {fastapi.__version__}")
except Exception as e:
    print(f"  ✗ fastapi: {e}")
    sys.exit(1)

try:
    import aiosqlite
    print(f"  ✓ aiosqlite")
except Exception as e:
    print(f"  ✗ aiosqlite: {e}")
    sys.exit(1)
print()

# Step 3: Test backend imports
print("Step 3: Testing Backend Imports")
try:
    from backend.config import HOST, PORT, DEBUG, DATABASE_PATH
    print(f"  ✓ config: HOST={HOST}, PORT={PORT}, DEBUG={DEBUG}")
    print(f"  ✓ DATABASE_PATH={DATABASE_PATH}")
except Exception as e:
    print(f"  ✗ config: {e}")
    traceback.print_exc()
    sys.exit(1)

try:
    from backend.database import init_db
    print("  ✓ database module")
except Exception as e:
    print(f"  ✗ database: {e}")
    traceback.print_exc()
    sys.exit(1)

try:
    from backend.routes import auth, slots, reservations, cars, admin
    print("  ✓ all route modules")
except Exception as e:
    print(f"  ✗ routes: {e}")
    traceback.print_exc()
    sys.exit(1)
print()

# Step 4: Test app import
print("Step 4: Testing FastAPI App Import")
try:
    from backend.app import app
    print(f"  ✓ App imported: {app.title}")
    print(f"  ✓ Routes: {len(app.routes)}")
except Exception as e:
    print(f"  ✗ App import failed: {e}")
    traceback.print_exc()
    sys.exit(1)
print()

# Step 5: Check database
print("Step 5: Checking Database")
db_dir = DATABASE_PATH.parent
if not db_dir.exists():
    print(f"  Creating database directory: {db_dir}")
    db_dir.mkdir(parents=True, exist_ok=True)

if DATABASE_PATH.exists():
    print(f"  ✓ Database exists: {DATABASE_PATH}")
else:
    print(f"  ⚠ Database will be created on first run")
print()

# Step 6: Start server
print("=" * 70)
print("Starting Server...")
print(f"  URL: http://127.0.0.1:{PORT}")
print(f"  Docs: http://127.0.0.1:{PORT}/docs")
print("  Press Ctrl+C to stop")
print("=" * 70)
print()

try:
    # Use explicit host and port
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=PORT,
        reload=False,
        log_level="info",
        access_log=True
    )
except KeyboardInterrupt:
    print("\n\nServer stopped by user")
except Exception as e:
    print(f"\n\n❌ SERVER ERROR: {e}")
    print("\nFull traceback:")
    traceback.print_exc()
    
    # Save error
    error_file = Path("server_error.log")
    with open(error_file, "w") as f:
        f.write(f"Error: {e}\n\n")
        traceback.print_exc(file=f)
    print(f"\nError saved to: {error_file}")
    sys.exit(1)
