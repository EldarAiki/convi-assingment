import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
ASSIGNMENT_ROOT = ROOT.parent
SCHEMA_PATH = ASSIGNMENT_ROOT / "analyzeData" / "graph_schema.yaml"
OUTPUT_DIR = ROOT / "output"

load_dotenv(ASSIGNMENT_ROOT / ".env")

MONGODB_URL = os.getenv("MONGODB_URL")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

BATCH_SIZE = int(os.getenv("INGEST_BATCH_SIZE", "100"))


def get_database_name() -> str:
    if not MONGODB_URL:
        raise ValueError("MONGODB_URL is not set in assignment/.env")

    path = urlparse(MONGODB_URL).path.strip("/")
    if path:
        return path.split("/")[0]
    return "convi-assessment"
