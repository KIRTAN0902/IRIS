import os
import sys
import urllib.request
import traceback

log_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_daemon.log")

def log(msg):
    with open(log_file_path, "a", encoding="utf-8") as f:
        f.write(msg + "\n")

def is_backend_healthy():
    try:
        req = urllib.request.Request("http://127.0.0.1:8000/health")
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            return resp.status == 200
    except Exception:
        return False

try:
    log("=== Daemon starting ===")
    log(f"sys.executable: {sys.executable}")
    log(f"cwd: {os.getcwd()}")
    
    if is_backend_healthy():
        log("Backend is already running and healthy on port 8000. Exiting.")
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
