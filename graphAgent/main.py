"""CLI for the graph-backed case reasoning agent."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from agent.graph import build_agent_graph
from agent.bidi import improve_terminal_bidi, write_html_answer_report
from agent.progress import log_progress, log_step, reset_progress, set_verbose
from agent.usage import format_usage_summary
from clients.mongo_client import MongoReadClient
from clients.neo4j_client import Neo4jReadClient
from config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, NEO4J_DATABASE, NEO4J_PASSWORD, NEO4J_URI, NEO4J_USER, OUTPUT_DIR
from tools.registry import build_toolkit


def main() -> None:
    parser = argparse.ArgumentParser(description="Graph-backed injury-claims reasoning agent")
    parser.add_argument("--question", "-q", required=True, help="Question to answer")
    parser.add_argument("--report", default="agent_run.json", help="Output filename under graphAgent/output/")
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Disable progress logs (final answer and token summary still print)",
    )
    parser.add_argument(
        "--html",
        action="store_true",
        help="Also write an RTL-friendly HTML answer report under graphAgent/output/",
    )
    parser.add_argument(
        "--no-bidi",
        action="store_true",
        help="Skip terminal bidi isolates for Hebrew output",
    )
    args = parser.parse_args()

    if not ANTHROPIC_API_KEY:
        raise ValueError("API_KEY_ANTHROPIC is not set in assignment/.env")
    if not NEO4J_PASSWORD:
        raise ValueError("NEO4J_PASSWORD is not set in assignment/.env")

    set_verbose(not args.quiet)
    reset_progress()

    neo4j = Neo4jReadClient(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, NEO4J_DATABASE)
    mongo = MongoReadClient()
    try:
        if not args.quiet:
            log_progress(f"Connecting to Neo4j ({NEO4J_URI}, db={NEO4J_DATABASE})")
        neo4j.verify()
        tools = build_toolkit(neo4j, mongo)
        graph = build_agent_graph(tools)
        if not args.quiet:
            log_progress(f"Agent ready — model={ANTHROPIC_MODEL}, tools={len(tools)}")

        initial_state = {
            "messages": [],
            "question": args.question,
            "intent": None,
            "case_ids": [],
            "evidence": [],
            "tool_call_count": 0,
            "outer_iteration": 0,
            "empty_streak": 0,
            "stop_reason": None,
            "sufficient": False,
            "final_answer": None,
            "token_usage": {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "llm_calls": 0,
                "estimated_cost_usd": 0.0,
            },
        }

        if not args.quiet:
            log_progress("Starting agent run")
        result = graph.invoke(initial_state)
        if not args.quiet:
            log_step("Run complete")
    finally:
        neo4j.close()
        mongo.close()

    token_usage = result.get("token_usage") or {}
    report = {
        "generatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "model": ANTHROPIC_MODEL,
        "question": args.question,
        "sufficient": result.get("sufficient"),
        "stopReason": result.get("stop_reason"),
        "toolCallCount": result.get("tool_call_count"),
        "evidence": result.get("evidence"),
        "tokenUsage": token_usage,
        "answer": result.get("final_answer"),
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUTPUT_DIR / args.report
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    answer_text = report["answer"] or ""
    if not args.no_bidi:
        answer_text = improve_terminal_bidi(answer_text)

    html_path: Path | None = None
    if args.html:
        html_path = OUTPUT_DIR / (report_path.stem + ".html")
        write_html_answer_report(
            html_path,
            question=args.question,
            answer=report["answer"] or "",
            metadata={
                "sufficient": report["sufficient"],
                "toolCalls": report["toolCallCount"],
                "tokens": format_usage_summary(token_usage),
            },
        )
        if not args.quiet:
            log_progress(f"HTML answer report: {html_path}")

    print(answer_text)
    print()
    print(format_usage_summary(token_usage))
    suffix = f" | HTML: {html_path}" if html_path else ""
    print(
        f"Sufficient: {report['sufficient']} | Tool calls: {report['toolCallCount']} | Report: {report_path}{suffix}"
    )


if __name__ == "__main__":
    main()
