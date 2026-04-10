import sys

if __name__ == "__main__":
    try:
        from backend.config import HOST, PORT, DEBUG
        import uvicorn
    except Exception as e:
        print("Error loading backend:", e)
        print("Run from project root with venv activated: python run.py")
        sys.exit(1)

    print(f"Starting server on http://{HOST}:{PORT}")
    print(f"API docs: http://{HOST}:{PORT}/docs")
    print("Press Ctrl+C to stop")
    print()

    try:
        uvicorn.run(
            "backend.app:app",
            host=HOST,
            port=PORT,
            reload=DEBUG,
            reload_excludes=[".venv", "venv", "*.pyc", "video", "models", "database"],
            log_level="info"
        )
    except Exception as e:
        print("Server error:", e)
        sys.exit(1)
