import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "solarni_server" / "app"))
sys.path.insert(0, str(ROOT / "solarni_dashboard" / "app"))
