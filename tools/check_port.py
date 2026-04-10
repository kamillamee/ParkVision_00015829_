"""Check if port 8000 is available and test server binding"""
import socket
import sys
from backend.config import HOST, PORT

def check_port(host, port):
    """Check if a port is available"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    try:
        result = sock.connect_ex((host, port))
        sock.close()
        return result != 0  # True if port is free
    except Exception as e:
        print(f"Error checking port: {e}")
        return False

def test_bind(host, port):
    """Test if we can bind to the port"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
        sock.close()
        return True
    except OSError as e:
        print(f"Cannot bind to {host}:{port} - {e}")
        return False
    except Exception as e:
        print(f"Error: {e}")
        return False

print("=" * 60)
print("Port Availability Check")
print("=" * 60)
print()

print(f"Configuration:")
print(f"  HOST: {HOST}")
print(f"  PORT: {PORT}")
print()

# Check localhost
print("Checking localhost (127.0.0.1):")
if check_port("127.0.0.1", PORT):
    print(f"  ✓ Port {PORT} is FREE on 127.0.0.1")
else:
    print(f"  ✗ Port {PORT} is IN USE on 127.0.0.1")
    print(f"    Something is already listening on this port!")

print()

# Check 0.0.0.0
if HOST == "0.0.0.0":
    print("Checking 0.0.0.0 (all interfaces):")
    if check_port("127.0.0.1", PORT):
        print(f"  ✓ Port {PORT} appears free")
    else:
        print(f"  ✗ Port {PORT} is in use")
    
    print()
    print("Testing if we can bind to 0.0.0.0:")
    if test_bind("0.0.0.0", PORT):
        print(f"  ✓ Can bind to 0.0.0.0:{PORT}")
    else:
        print(f"  ✗ Cannot bind to 0.0.0.0:{PORT}")
        print("  Try using 127.0.0.1 instead")
else:
    print(f"Testing if we can bind to {HOST}:")
    if test_bind(HOST, PORT):
        print(f"  ✓ Can bind to {HOST}:{PORT}")
    else:
        print(f"  ✗ Cannot bind to {HOST}:{PORT}")

print()
print("=" * 60)
print("Recommendation:")
if HOST == "0.0.0.0":
    print("  Try changing HOST to '127.0.0.1' in backend/config.py")
    print("  Or set environment variable: set HOST=127.0.0.1")
else:
    print(f"  Current HOST ({HOST}) should work")
print("=" * 60)
