"""Read-only MongoDB helpers for drill-down tools."""

from __future__ import annotations

from typing import Any

from pymongo import MongoClient

from config import MONGODB_URL, get_database_name


class MongoReadClient:
    def __init__(self) -> None:
        self.client = MongoClient(MONGODB_URL, serverSelectionTimeoutMS=20000)
        self.db = self.client[get_database_name()]

    def close(self) -> None:
        self.client.close()

    def find_one(self, collection: str, query: dict[str, Any], projection: dict[str, Any] | None = None):
        return self.db[collection].find_one(query, projection)
