"""Run server with detailed error reporting"""
import sys
import traceback
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

print("=" * 60)
print("Starting Smart Vision System Server")
print("=" * 60)
print()

try:
    # Try to import and run
    import uvicorn
    from backend.config import HOST, PORT, DEBUG
    
    print(f"Configuration:")
    print(f"  Host: {HOST}")
    print(f"  Port: {PORT}")
    print(f"  Debug: {DEBUG}")
    print()
    
    print("Importing FastAPI app...")
    from backend.app import app
    print("✓ App imported successfully")
    print()
    
    print("Starting server...")
    print(f"Server will be available at: http://localhost:{PORT}")
    print("Press Ctrl+C to stop the server")
    print("=" * 60)
    print()
    
    uvicorn.run(
        "backend.app:app",
        host=HOST,
        port=PORT,
        reload=DEBUG,
        log_level="info"
    )
    
except ImportError as e:
    print(f"❌ Import Error: {e}")
    print("\nThis usually means dependencies are not installed.")
    print("Try running: pip install -r requirements.txt")
    traceback.print_exc()
    sys.exit(1)
    
except Exception as e:
    print(f"❌ Error starting server: {e}")
    print("\nFull error details:")
    traceback.print_exc()
    sys.exit(1)
