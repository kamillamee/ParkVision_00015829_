"""Quick port test"""
import socket

def test_port(host, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    result = sock.connect_ex((host, port))
    sock.close()
    return result == 0  # True if port is in use

port = 8000
print(f"Testing port {port}...")

if test_port("127.0.0.1", port):
    print(f"❌ Port {port} is IN USE on 127.0.0.1")
    print("   Something is already running on this port!")
else:
    print(f"✓ Port {port} is FREE on 127.0.0.1")
    print("   Server should be able to bind to this port")
