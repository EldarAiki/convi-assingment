"""Register all agent tools."""

from __future__ import annotations

from clients.mongo_client import MongoReadClient
from clients.neo4j_client import Neo4jReadClient
from tools.neo4j_tools import build_neo4j_tools


def build_toolkit(neo4j: Neo4jReadClient, mongo: MongoReadClient) -> list:
    return build_neo4j_tools(neo4j, mongo)
