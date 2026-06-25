"""Build the LangGraph case reasoning workflow."""

from __future__ import annotations

import json

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

from agent.progress import log_progress, log_step
from agent.prompts.system import INSUFFICIENT_PROMPT, SYNTHESIZE_PROMPT, SYSTEM_PROMPT
from agent.state import AgentState
from agent.usage import extract_message_usage, merge_usage
from config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL, load_defaults


def _extract_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            part.get("text", "")
            for part in content
            if isinstance(part, dict) and part.get("type") == "text"
        ]
        return "\n".join(parts)
    return str(content)


def _is_empty_tool_result(content: str) -> bool:
    lowered = content.lower()
    return (
        '"count": 0' in lowered
        or '"found": false' in lowered
        or '"cases": []' in lowered
        or content.strip() in ("[]", "{}")
    )


def _summarize_tool_result(tool_name: str, content: str) -> str:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        preview = content[:120].replace("\n", " ")
        return f"{tool_name} returned text ({len(content)} chars): {preview}"

    if tool_name == "search_cases":
        return f"{tool_name}: {payload.get('count', 0)} case(s) matched"
    if tool_name == "list_case_types":
        return f"{tool_name}: {payload.get('count', 0)} type(s) listed"
    if tool_name == "search_injury_cases":
        return f"{tool_name}: {payload.get('count', 0)} case(s) matched"
    if tool_name == "compare_injury_cases":
        shared = payload.get("sharedBodyParts") or []
        return f"{tool_name}: compared 2 cases, {len(shared)} shared body part(s)"
    if tool_name == "get_case_timeline":
        return f"{tool_name}: {payload.get('eventCount', 0)} event(s)"
    if isinstance(payload, dict) and "found" in payload:
        return f"{tool_name}: found={payload.get('found')}"
    return f"{tool_name}: result received ({len(content)} chars)"


def build_agent_graph(tools: list):
    limits = load_defaults().get("limits", {})
    max_tool_calls = int(limits.get("max_tool_calls", 10))
    max_empty_streak = int(limits.get("max_empty_streak", 2))

    llm = ChatAnthropic(
        model=ANTHROPIC_MODEL,
        temperature=0,
        api_key=ANTHROPIC_API_KEY,
    )
    llm_with_tools = llm.bind_tools(tools)
    tool_node = ToolNode(tools)

    def prepare(state: AgentState) -> dict:
        log_step(f"Preparing question: {state['question'][:120]}")
        return {
            "messages": [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=state["question"]),
            ],
            "tool_call_count": 0,
            "outer_iteration": 0,
            "empty_streak": 0,
            "evidence": [],
            "sufficient": False,
            "stop_reason": None,
            "final_answer": None,
            "case_ids": [],
            "intent": None,
            "token_usage": state.get("token_usage") or {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "llm_calls": 0,
                "estimated_cost_usd": 0.0,
            },
        }

    def call_model(state: AgentState) -> dict:
        if state.get("stop_reason"):
            return {}
        log_step("Thinking — planning tool use or final response")
        response = llm_with_tools.invoke(state["messages"])
        token_usage = merge_usage(state.get("token_usage"), extract_message_usage(response))

        tool_calls = getattr(response, "tool_calls", None) or []
        if tool_calls:
            names = ", ".join(call.get("name", "?") for call in tool_calls)
            log_progress(f"  LLM requested {len(tool_calls)} tool call(s): {names}")
        else:
            log_progress("  LLM finished without further tool calls")

        return {"messages": [response], "token_usage": token_usage}

    def run_tools(state: AgentState) -> dict:
        last = state["messages"][-1]
        for call in getattr(last, "tool_calls", None) or []:
            args_preview = json.dumps(call.get("args", {}), ensure_ascii=False)[:160]
            log_progress(f"  Running {call.get('name')}({args_preview})")
        return tool_node.invoke(state)

    def track_tools(state: AgentState) -> dict:
        tool_messages = [message for message in state["messages"] if message.type == "tool"]
        if not tool_messages:
            return {}

        latest = tool_messages[-1]
        content = _extract_text(latest.content)
        log_progress(f"  Done: {_summarize_tool_result(latest.name, content)}")

        evidence = list(state.get("evidence", []))
        evidence.append(
            {
                "tool": latest.name,
                "contentPreview": content[:2000],
            }
        )

        empty_streak = state.get("empty_streak", 0)
        if _is_empty_tool_result(content):
            empty_streak += 1
            log_progress("  Empty result — empty-result streak increased")
        else:
            empty_streak = 0

        tool_call_count = state.get("tool_call_count", 0) + 1
        stop_reason = state.get("stop_reason")
        if tool_call_count >= max_tool_calls:
            stop_reason = "max_tool_calls"
            log_progress(f"  Reached max tool calls ({max_tool_calls})")
        elif empty_streak >= max_empty_streak:
            stop_reason = "empty_evidence"
            log_progress(f"  Reached empty-result limit ({max_empty_streak})")

        return {
            "tool_call_count": tool_call_count,
            "empty_streak": empty_streak,
            "evidence": evidence,
            "stop_reason": stop_reason,
        }

    def synthesize(state: AgentState) -> dict:
        log_step("Synthesizing final answer from retrieved evidence")
        response = llm.invoke(
            [SystemMessage(content=SYNTHESIZE_PROMPT)]
            + state["messages"]
            + [HumanMessage(content="Write the final answer now.")]
        )
        token_usage = merge_usage(state.get("token_usage"), extract_message_usage(response))
        return {
            "final_answer": _extract_text(response.content),
            "messages": [response],
            "sufficient": True,
            "token_usage": token_usage,
        }

    def insufficient(state: AgentState) -> dict:
        log_step(f"Stopping early — reason: {state.get('stop_reason') or 'unknown'}")
        response = llm.invoke(
            [
                SystemMessage(content=INSUFFICIENT_PROMPT),
                HumanMessage(
                    content=(
                        f"Question: {state['question']}\n"
                        f"Stop reason: {state.get('stop_reason')}\n"
                        f"Evidence: {state.get('evidence')}"
                    )
                ),
            ]
        )
        token_usage = merge_usage(state.get("token_usage"), extract_message_usage(response))
        return {
            "final_answer": _extract_text(response.content),
            "messages": [response],
            "sufficient": False,
            "token_usage": token_usage,
        }

    def route_after_model(state: AgentState) -> str:
        if state.get("stop_reason"):
            return "insufficient"
        last = state["messages"][-1]
        if getattr(last, "tool_calls", None):
            return "tools"
        return "synthesize"

    def route_after_track(state: AgentState) -> str:
        if state.get("stop_reason"):
            return "insufficient"
        return "agent"

    graph = StateGraph(AgentState)
    graph.add_node("prepare", prepare)
    graph.add_node("agent", call_model)
    graph.add_node("tools", run_tools)
    graph.add_node("track", track_tools)
    graph.add_node("synthesize", synthesize)
    graph.add_node("insufficient", insufficient)

    graph.set_entry_point("prepare")
    graph.add_edge("prepare", "agent")
    graph.add_conditional_edges(
        "agent",
        route_after_model,
        {"tools": "tools", "synthesize": "synthesize", "insufficient": "insufficient"},
    )
    graph.add_edge("tools", "track")
    graph.add_conditional_edges("track", route_after_track, {"agent": "agent", "insufficient": "insufficient"})
    graph.add_edge("synthesize", END)
    graph.add_edge("insufficient", END)

    return graph.compile()
