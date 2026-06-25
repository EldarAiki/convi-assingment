"""Bidirectional text helpers for Hebrew terminal and HTML output."""

from __future__ import annotations

import html
import re
from pathlib import Path

# Unicode directional isolates (Unicode BiDi algorithm)
RLI = "\u2067"  # Right-to-Left Isolate
LRI = "\u2066"  # Left-to-Right Isolate
PDI = "\u2069"  # Pop Directional Isolate

HEBREW_CHAR = re.compile(r"[\u0590-\u05FF\uFB1D-\uFB4F]")
LATIN_RUN = re.compile(r"[A-Za-z0-9_`.\-/\\|:]+")


def contains_hebrew(text: str) -> bool:
    return bool(HEBREW_CHAR.search(text or ""))


def _is_hebrew_char(char: str) -> bool:
    return bool(HEBREW_CHAR.match(char))


def improve_terminal_bidi(text: str) -> str:
    """Wrap Hebrew and Latin runs so terminals with BiDi support display more naturally."""
    if not text or not contains_hebrew(text):
        return text
    return "\n".join(_bidi_line(line) for line in text.splitlines())


def _bidi_line(line: str) -> str:
    if not line.strip() or not contains_hebrew(line):
        return line

    runs: list[tuple[str, str]] = []
    current: list[str] = []
    current_kind: str | None = None

    for char in line:
        if _is_hebrew_char(char):
            kind = "he"
        elif char.isascii() and char.isalnum():
            kind = "lat"
        else:
            kind = current_kind or "neutral"

        if current_kind is None:
            current_kind = kind
            current.append(char)
            continue

        if kind == current_kind or kind == "neutral":
            current.append(char)
        else:
            runs.append((current_kind, "".join(current)))
            current = [char]
            current_kind = kind

    if current:
        runs.append((current_kind or "neutral", "".join(current)))

    parts: list[str] = []
    for kind, segment in runs:
        if not segment:
            continue
        if kind == "he":
            parts.append(f"{RLI}{segment}{PDI}")
        elif kind == "lat" and LATIN_RUN.search(segment):
            parts.append(f"{LRI}{segment}{PDI}")
        else:
            parts.append(segment)
    return "".join(parts)


def write_html_answer_report(
    path: Path,
    *,
    question: str,
    answer: str,
    metadata: dict,
) -> Path:
    """Write an RTL-friendly HTML view of the answer (best Hebrew rendering)."""
    meta_rows = "".join(
        f"<tr><th>{html.escape(str(key))}</th><td>{html.escape(str(value))}</td></tr>"
        for key, value in metadata.items()
    )
    document = f"""<!DOCTYPE html>
<html lang="he">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Agent answer</title>
  <style>
    body {{
      font-family: "Segoe UI", Arial, sans-serif;
      margin: 2rem;
      background: #fafafa;
      color: #111;
    }}
    .card {{
      background: #fff;
      border: 1px solid #ddd;
      border-radius: 8px;
      padding: 1.25rem 1.5rem;
      max-width: 960px;
      box-shadow: 0 1px 3px rgba(0,0,0,.06);
    }}
    h1 {{ font-size: 1.2rem; margin-top: 0; }}
    .question {{
      unicode-bidi: plaintext;
      white-space: pre-wrap;
      background: #f3f4f6;
      padding: 0.75rem 1rem;
      border-radius: 6px;
      margin-bottom: 1rem;
    }}
    .answer {{
      unicode-bidi: plaintext;
      white-space: pre-wrap;
      line-height: 1.6;
      font-size: 1rem;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 1.5rem;
      font-size: 0.9rem;
    }}
    th, td {{
      border-top: 1px solid #eee;
      padding: 0.45rem 0.25rem;
      text-align: left;
      vertical-align: top;
    }}
    th {{ width: 180px; color: #555; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>Graph agent answer</h1>
    <div class="question">{html.escape(question)}</div>
    <div class="answer">{html.escape(answer or "")}</div>
    <table>{meta_rows}</table>
  </div>
</body>
</html>
"""
    path.write_text(document, encoding="utf-8")
    return path
