"""Pytest configuration that puts the backend package on the import path"""

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "app" / "backend"
sys.path.insert(0, str(BACKEND))
