import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
ASSIGNMENT_ROOT = ROOT.parent
OUTPUT_DIR = ROOT / "output"

load_dotenv(ASSIGNMENT_ROOT / ".env")
load_dotenv(ROOT / ".env")

MONGODB_URL = os.getenv("MONGODB_URL")
ANTHROPIC_API_KEY = os.getenv("API_KEY_ANTHROPIC") or os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")


def get_database_name() -> str:
    if not MONGODB_URL:
        raise ValueError("MONGODB_URL is not set in .env")

    path = urlparse(MONGODB_URL).path.strip("/")
    if path:
        return path.split("/")[0]
    return "convi-assessment"
