"""Quick setup check script"""
import sys
from pathlib import Path

print("🔍 Checking Smart Vision System Setup...\n")

# Check Python version
print(f"✓ Python version: {sys.version}")

# Check if we can import required modules
required_modules = [
    "fastapi",
    "uvicorn",
    "pydantic",
    "aiosqlite",
    "passlib",
    "jose",
]

missing_modules = []
for module in required_modules:
    try:
        if module == "jose":
            __import__("jose")
        elif module == "passlib":
            __import__("passlib")
        else:
            __import__(module)
        print(f"✓ {module} installed")
    except ImportError:
        print(f"✗ {module} NOT installed")
        missing_modules.append(module)

if missing_modules:
    print(f"\n⚠️  Missing modules: {', '.join(missing_modules)}")
    print("   Run: pip install -r requirements.txt")
else:
    print("\n✓ All required modules installed")

# Check project structure (run from project root: python tools/check_setup.py)
print("\n📁 Checking project structure...")
base_dir = Path(__file__).resolve().parent.parent
required_dirs = ["backend", "frontend", "config", "video"]
for dir_name in required_dirs:
    dir_path = base_dir / dir_name
    if dir_path.exists():
        print(f"✓ {dir_name}/ exists")
    else:
        print(f"✗ {dir_name}/ missing")

# Check database
print("\n💾 Checking database...")
db_path = base_dir / "database" / "parking.db"
if db_path.exists():
    print(f"✓ Database exists: {db_path}")
else:
    print(f"⚠️  Database not found: {db_path}")
    print("   Run: python backend/init_db.py")

# Check config files
print("\n⚙️  Checking configuration...")
slots_config = base_dir / "config" / "slots.json"
if slots_config.exists():
    print(f"✓ slots.json exists")
else:
    print(f"⚠️  slots.json not found")

video_path = base_dir / "video" / "Parking.mp4"
if video_path.exists():
    print(f"✓ Video file exists")
else:
    print(f"⚠️  Video file not found (optional for AI module)")

# Try importing backend modules (ensure project root is on path)
print("\n🔧 Checking backend imports...")
sys.path.insert(0, str(base_dir))
try:
    from backend.config import HOST, PORT, DEBUG
    print(f"✓ Backend config loaded (HOST={HOST}, PORT={PORT}, DEBUG={DEBUG})")
except Exception as e:
    print(f"✗ Error loading backend config: {e}")

try:
    from backend.app import app
    print("✓ FastAPI app can be imported")
except Exception as e:
    print(f"✗ Error importing FastAPI app: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*50)
if not missing_modules:
    print("✅ Setup looks good! You can run: python run.py")
else:
    print("❌ Please install missing dependencies first")
print("="*50)
