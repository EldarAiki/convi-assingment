"""Run LangChain MongoDB agent for graph-discovery questions."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from langchain_core.messages import HumanMessage
from langchain_mongodb.agent_toolkit import (
    MONGODB_AGENT_SYSTEM_PROMPT,
    MongoDBDatabase,
    MongoDBDatabaseToolkit,
)
from langchain_anthropic import ChatAnthropic
from langgraph.prebuilt import create_react_agent

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import (  # noqa: E402
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    MONGODB_URL,
    OUTPUT_DIR,
    get_database_name,
)
from explore.graph_questions import GRAPH_DISCOVERY_QUESTIONS  # noqa: E402

GRAPH_CONTEXT = """
You are helping design a graph database layer for a legal firm's injury-claims platform.
The data is in Hebrew and English. Focus on:
- entity types that should become graph nodes (Case, Person, Organization, Document, Event, etc.)
- relationships that should become edges (HAS_CLIENT, ASSIGNED_TO, HAS_DOCUMENT, etc.)
- fields suitable as node/edge properties vs foreign-key join fields
- cardinality (one-to-many, many-to-many)

When answering, cite collection names and field paths explicitly.
Prefer aggregation pipelines over returning full documents.
"""


def build_agent():
    if not ANTHROPIC_API_KEY:
        raise ValueError(
            "Missing API key. Set API_KEY_ANTHROPIC in analyzeData/.env"
        )

    db = MongoDBDatabase.from_connection_string(
        MONGODB_URL,
        database=get_database_name(),
    )
    llm = ChatAnthropic(
        model=ANTHROPIC_MODEL,
        temperature=0,
        api_key=ANTHROPIC_API_KEY,
    )
    toolkit = MongoDBDatabaseToolkit(db=db, llm=llm)

    system_prompt = MONGODB_AGENT_SYSTEM_PROMPT.format(top_k=10) + GRAPH_CONTEXT
    agent = create_react_agent(llm, toolkit.get_tools(), prompt=system_prompt)
    return agent


def _extract_final_answer(messages) -> str:
    for message in reversed(messages):
        content = getattr(message, "content", None)
        if content and getattr(message, "type", "") == "ai":
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                text_parts = [
                    part.get("text", "")
                    for part in content
                    if isinstance(part, dict) and part.get("type") == "text"
                ]
                if text_parts:
                    return "\n".join(text_parts)
    return ""


def ask_question(agent, question: str) -> dict:
    final_state = agent.invoke({"messages": [HumanMessage(content=question)]})
    messages = final_state["messages"]
    return {
        "question": question,
        "answer": _extract_final_answer(messages),
        "messageCount": len(messages),
    }


def run_batch(agent, question_ids: list[str] | None = None) -> list[dict]:
    selected = GRAPH_DISCOVERY_QUESTIONS
    if question_ids:
        allowed = set(question_ids)
        selected = [q for q in GRAPH_DISCOVERY_QUESTIONS if q["id"] in allowed]

    results = []
    for item in selected:
        print(f"\n=== {item['id']} ({item['category']}) ===")
        print(item["question"])
        result = ask_question(agent, item["question"])
        result.update({"id": item["id"], "category": item["category"]})
        results.append(result)
        print(result["answer"][:500] + ("..." if len(result["answer"]) > 500 else ""))
    return results


def save_results(results: list[dict], output_name: str = "exploration_results.json") -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "generatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "model": ANTHROPIC_MODEL,
        "results": results,
    }
    output_path = OUTPUT_DIR / output_name
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Explore MongoDB for graph design")
    parser.add_argument(
        "--question",
        "-q",
        help="Ask a single custom question",
    )
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Run all predefined graph-discovery questions",
    )
    parser.add_argument(
        "--ids",
        nargs="+",
        help="Run specific predefined question ids (use with --batch)",
    )
    parser.add_argument(
        "--output",
        default="exploration_results.json",
        help="Output filename under output/",
    )
    args = parser.parse_args()

    if not args.question and not args.batch:
        parser.error("Provide --question or --batch")

    agent = build_agent()
    results: list[dict] = []

    if args.question:
        print(f"Asking: {args.question}")
        results.append(ask_question(agent, args.question))
        print(results[-1]["answer"])

    if args.batch:
        results.extend(run_batch(agent, args.ids))

    if results:
        output_path = save_results(results, args.output)
        print(f"\nSaved {len(results)} result(s) to {output_path}")


if __name__ == "__main__":
    main()
