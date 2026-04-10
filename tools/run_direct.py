"""Direct server run with error capture"""
import sys
import os
import traceback
from pathlib import Path

# Ensure we're in the right directory
os.chdir(Path(__file__).parent)

try:
    print("=" * 70)
    print("Smart Vision System - Starting Server")
    print("=" * 70)
    print()
    
    # Test imports first
    print("Step 1: Testing imports...")
    import uvicorn
    print("  ✓ uvicorn")
    
    from backend.config import HOST, PORT, DEBUG
    print(f"  ✓ config (HOST={HOST}, PORT={PORT}, DEBUG={DEBUG})")
    
    print("\nStep 2: Importing FastAPI app...")
    from backend.app import app
    print("  ✓ App imported")
    
    print("\nStep 3: Starting server...")
    print(f"  Server URL: http://localhost:{PORT}")
    print(f"  API Docs: http://localhost:{PORT}/docs")
    print("  Press Ctrl+C to stop")
    print("=" * 70)
    print()
    
    # Run server - pass app directly
    uvicorn.run(
        app,  # Pass app directly instead of string
        host=HOST,
        port=PORT,
        reload=False,  # Disable reload for stability
        log_level="info"
    )
    
except KeyboardInterrupt:
    print("\n\nServer stopped by user")
    sys.exit(0)
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    print("\nFull traceback:")
    traceback.print_exc()
    
    # Write error to file
    error_file = Path(__file__).parent / "server_error.log"
    with open(error_file, "w") as f:
        f.write(f"Error: {e}\n\n")
        traceback.print_exc(file=f)
    print(f"\nError details saved to: {error_file}")
    sys.exit(1)
