"""Simple server run - minimal configuration"""
import uvicorn

if __name__ == "__main__":
    print("Starting server on http://127.0.0.1:8000")
    print("Press Ctrl+C to stop")
    print()
    
    uvicorn.run(
        "backend.app:app",
        host="127.0.0.1",  # Use localhost explicitly
        port=8000,
        reload=False,
        log_level="info"
    )
