"""Quick Anthropic API key test.

Edit PROMPT below, or pass your own on the command line:

    python test_anthropic.py
    python test_anthropic.py --prompt "Summarize what a graph database is in one sentence."

Requires: pip install anthropic python-dotenv
Reads: assignment/.env (API_KEY_ANTHROPIC, optional ANTHROPIC_MODEL)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

# --- edit this prompt for a quick test ---
PROMPT = "what is a graph database?"


def main() -> None:
    parser = argparse.ArgumentParser(description="Test Anthropic API connectivity")
    parser.add_argument(
        "--prompt",
        "-p",
        default=PROMPT,
        help="Prompt to send (default: built-in PROMPT in this file)",
    )
    parser.add_argument(
        "--model",
        "-m",
        default=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
        help="Model id (default: ANTHROPIC_MODEL from .env or claude-sonnet-4-6)",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=256,
        help="Max tokens in the response",
    )
    args = parser.parse_args()

    api_key = os.getenv("API_KEY_ANTHROPIC") or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("Error: set API_KEY_ANTHROPIC in assignment/.env", file=sys.stderr)
        sys.exit(1)

    try:
        import anthropic
    except ImportError:
        print("Error: pip install anthropic", file=sys.stderr)
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    print(f"Model: {args.model}")
    print(f"Prompt: {args.prompt}\n")

    try:
        message = client.messages.create(
            model=args.model,
            max_tokens=args.max_tokens,
            messages=[{"role": "user", "content": args.prompt}],
        )
    except anthropic.AuthenticationError as exc:
        print(f"Authentication failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except anthropic.APIError as exc:
        print(f"API error: {exc}", file=sys.stderr)
        sys.exit(1)

    parts = []
    for block in message.content:
        if hasattr(block, "text"):
            parts.append(block.text)

    print("Response:")
    print("".join(parts) or "(empty)")
    print(f"\nOK — stop_reason={message.stop_reason}, input_tokens={message.usage.input_tokens}, output_tokens={message.usage.output_tokens}")


if __name__ == "__main__":
    main()
