"""LangGraph agent state."""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    question: str
    intent: str | None
    case_ids: list[str]
    evidence: list[dict[str, Any]]
    tool_call_count: int
    outer_iteration: int
    empty_streak: int
    stop_reason: str | None
    sufficient: bool
    final_answer: str | None
    token_usage: dict[str, Any]
