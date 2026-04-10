"""Install dependencies and run the server"""
import subprocess
import sys
import os
from pathlib import Path

def install_requirements():
    """Install requirements if needed"""
    print("=" * 60)
    print("Installing Dependencies")
    print("=" * 60)
    print()
    
    venv_python = Path(__file__).parent / "venv" / "Scripts" / "python.exe"
    if not venv_python.exists():
        print("❌ Virtual environment not found!")
        print("   Please create venv first: python -m venv venv")
        return False
    
    print("Installing/updating requirements...")
    try:
        result = subprocess.run(
            [str(venv_python), "-m", "pip", "install", "-r", "requirements.txt"],
            capture_output=True,
            text=True,
            check=True
        )
        print("✅ Dependencies installed successfully")
        print()
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error installing dependencies:")
        print(e.stderr)
        return False

def check_uvicorn():
    """Check if uvicorn is installed"""
    venv_python = Path(__file__).parent / "venv" / "Scripts" / "python.exe"
    try:
        result = subprocess.run(
            [str(venv_python), "-c", "import uvicorn; print(uvicorn.__version__)"],
            capture_output=True,
            text=True,
            check=True
        )
        print(f"✅ uvicorn is installed: {result.stdout.strip()}")
        return True
    except subprocess.CalledProcessError:
        print("❌ uvicorn is not installed")
        return False

if __name__ == "__main__":
    # Change to script directory
    os.chdir(Path(__file__).parent)
    
    # Check uvicorn
    if not check_uvicorn():
        print("\nInstalling dependencies...")
        if not install_requirements():
            sys.exit(1)
    
    # Run the server
    print("=" * 60)
    print("Starting Server")
    print("=" * 60)
    print()
    
    venv_python = Path(__file__).parent / "venv" / "Scripts" / "python.exe"
    try:
        subprocess.run([str(venv_python), "run.py"], check=True)
    except KeyboardInterrupt:
        print("\n\nServer stopped by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
