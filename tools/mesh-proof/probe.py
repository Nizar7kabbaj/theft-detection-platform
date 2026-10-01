import json
import socket
import ssl
import sys
from concurrent.futures import ThreadPoolExecutor

TIMEOUT = 3.0
H2_PREFACE = b"PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n" + bytes([0, 0, 0, 4, 0, 0, 0, 0, 0])


def tls_reachable(sock):
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    try:
        with context.wrap_socket(sock, server_hostname=None):
            return True
    except ssl.SSLEOFError:
        return False
    except ssl.SSLError:
        return True


def h2c_reachable(sock):
    sock.sendall(H2_PREFACE)
    return bool(sock.recv(1))


def probe(check):
    try:
        with socket.create_connection((check["host"], check["port"]), timeout=TIMEOUT) as sock:
            sock.settimeout(TIMEOUT)
            if check["kind"] == "h2c":
                return check["id"], h2c_reachable(sock)
            return check["id"], tls_reachable(sock)
    except OSError:
        return check["id"], False


checks = json.loads(sys.argv[-1])
with ThreadPoolExecutor(max_workers=32) as pool:
    print(json.dumps(dict(pool.map(probe, checks))))
