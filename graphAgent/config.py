import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
ASSIGNMENT_ROOT = ROOT.parent
SCHEMA_PATH = ASSIGNMENT_ROOT / "analyzeData" / "graph_schema.yaml"
OUTPUT_DIR = ROOT / "output"
DEFAULTS_PATH = ROOT / "config" / "defaults.yaml"

load_dotenv(ASSIGNMENT_ROOT / ".env")

MONGODB_URL = os.getenv("MONGODB_URL")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

ANTHROPIC_API_KEY = os.getenv("API_KEY_ANTHROPIC") or os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6")


def get_database_name() -> str:
    if not MONGODB_URL:
        raise ValueError("MONGODB_URL is not set in assignment/.env")

    from urllib.parse import urlparse

    path = urlparse(MONGODB_URL).path.strip("/")
    if path:
        return path.split("/")[0]
    return "convi-assessment"


def load_defaults() -> dict:
    if not DEFAULTS_PATH.exists():
        return {}
    return yaml.safe_load(DEFAULTS_PATH.read_text(encoding="utf-8")) or {}
