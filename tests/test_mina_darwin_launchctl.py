"""Run the Darwin launchctl fallback shell contract."""

import subprocess
from pathlib import Path


def test_mina_darwin_launchctl_fallback():
    script = Path(__file__).resolve().parent / "test_mina_darwin_launchctl.sh"
    subprocess.run(["bash", str(script)], check=True)
