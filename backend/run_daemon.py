import os
import sys
import socket
import traceback

log_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_daemon.log")

def log(msg):
    with open(log_file_path, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

def is_port_in_use(port=8000):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex(('127.0.0.1', port)) == 0
    except Exception:
        return False

try:
    log("=== Daemon starting ===")
    log(f"sys.executable: {sys.executable}")
    log(f"cwd: {os.getcwd()}")
    
    if is_port_in_use(8000):
        log("Port 8000 is already in use by an active IRIS daemon. Exiting cleanly.")
        sys.exit(0)
    
    # Ensure stdout/stderr/stdin
    log_fp = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "uvicorn.log"), "a", encoding="utf-8", buffering=1)
    sys.stdout = log_fp
    sys.stderr = log_fp
    if sys.stdin is None:
        import io
        sys.stdin = io.StringIO()

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    
    import uvicorn
    log("Imported uvicorn, starting server...")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, log_level="info")
except Exception as e:
    log(f"Exception occurred: {e}")
    log(traceback.format_exc())
