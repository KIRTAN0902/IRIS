import sys
from pathlib import Path

# Ensure backend directory is in sys.path for Vercel serverless execution
backend_dir = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

from app.main import app  # noqa: E402
