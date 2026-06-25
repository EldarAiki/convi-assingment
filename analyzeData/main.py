"""Convenience entry points for the analyzeData project."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def profile_schema() -> None:
    subprocess.run([sys.executable, str(ROOT / "profile" / "schema_profile.py")], check=True)


def run_agent(argv: list[str] | None = None) -> None:
    cmd = [sys.executable, str(ROOT / "explore" / "run_agent.py")]
    if argv:
        cmd.extend(argv)
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    print("Usage:")
    print("  python main.py profile")
    print("  python main.py agent -- --question 'your question'")
    print("  python main.py agent -- --batch")
