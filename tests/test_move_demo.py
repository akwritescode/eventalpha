"""Keep the UI demo and database seed synchronized."""

import subprocess
import sys
from pathlib import Path


def test_generated_move_demo_is_current():
    root = Path(__file__).resolve().parents[1]
    subprocess.run([sys.executable, str(root / "scripts/render_move_demo.py"), "--check"], check=True)
