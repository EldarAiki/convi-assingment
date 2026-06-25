"""CLI entry point for MongoDB → Neo4j ingestion."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from config import NEO4J_DATABASE, NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER, OUTPUT_DIR, SCHEMA_PATH
from ingest.neo4j_client import Neo4jClient
from ingest.pipeline import IngestionPipeline


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest MongoDB injury-claim data into Neo4j using graph_schema.yaml (no AI)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read MongoDB and report counts without writing to Neo4j",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Delete all Neo4j nodes/relationships before ingest",
    )
    parser.add_argument(
        "--report",
        default="ingest_report.json",
        help="Report filename under graphIngest/output/",
    )
    args = parser.parse_args()

    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"Schema file not found: {SCHEMA_PATH}")

    neo4j = None
    if not args.dry_run:
        if not NEO4J_PASSWORD:
            raise ValueError(
                "NEO4J_PASSWORD is not set in assignment/.env. "
                "Use --dry-run to validate Mongo mappings without Neo4j."
            )
        neo4j = Neo4jClient(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, NEO4J_DATABASE)
        neo4j.verify()
        print(f"Connected to Neo4j at {NEO4J_URI} (database: {NEO4J_DATABASE})")
    else:
        print("Dry run: MongoDB mappings only, no Neo4j writes.")

    pipeline = IngestionPipeline(neo4j=neo4j, dry_run=args.dry_run)
    try:
        stats = pipeline.run(clear=args.clear and not args.dry_run)
    finally:
        pipeline.close()

    report = {
        "schema": str(SCHEMA_PATH),
        "dryRun": args.dry_run,
        "stats": stats.to_dict(),
    }

    try:
        if neo4j and not args.dry_run:
            report["neo4jCounts"] = {
                "nodes": neo4j.count_nodes(),
                "relationships": neo4j.count_relationships(),
            }
    finally:
        if neo4j:
            neo4j.close()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUTPUT_DIR / args.report
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\nIngestion complete.")
    print("Nodes:", report["stats"]["nodes"])
    print("Relationships:", report["stats"]["relationships"])
    if "neo4jCounts" in report:
        print("Neo4j node counts:", report["neo4jCounts"].get("nodes", report["neo4jCounts"]))
        if "relationships" in report["neo4jCounts"]:
            print("Neo4j relationship counts:", report["neo4jCounts"]["relationships"])
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
