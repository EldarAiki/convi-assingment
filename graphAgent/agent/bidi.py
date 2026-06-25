"""Bidirectional text helpers for Hebrew terminal and HTML output."""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

# Unicode directional controls (strip from HTML; optional for terminal)
BIDI_CONTROLS = re.compile(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069]")
RLI = "\u2067"
LRI = "\u2066"
PDI = "\u2069"

HEBREW_CHAR = re.compile(r"[\u0590-\u05FF\uFB1D-\uFB4F]")
LATIN_RUN = re.compile(r"[A-Za-z0-9_`.\-/\\|:]+")
# Latin/code spans to embed inside RTL paragraphs (caseId, tool names, numbers)
LTR_EMBED = re.compile(
    r"`[^`]+`|"  # backtick code
    r"caseId:\s*`[^`]+`|"  # caseId: `...`
    r"\b[A-Za-z][A-Za-z0-9_]{2,}\b|"  # identifiers / snake_case
    r"₪[\d,]+|"  # shekel amounts
    r"\b\d[\d,.\s]*\d\b"  # numbers
)
_HTML_TAG = re.compile(r"(<[^>]+>)")


def contains_hebrew(text: str) -> bool:
    return bool(HEBREW_CHAR.search(text or ""))


def hebrew_ratio(text: str) -> float:
    if not text:
        return 0.0
    hebrew = len(HEBREW_CHAR.findall(text))
    letters = sum(1 for char in text if char.isalpha() or _is_hebrew_char(char))
    return hebrew / letters if letters else 0.0


def strip_bidi_controls(text: str) -> str:
    return BIDI_CONTROLS.sub("", text or "")


def _is_hebrew_char(char: str) -> bool:
    return bool(HEBREW_CHAR.match(char))


def improve_terminal_bidi(text: str) -> str:
    """Wrap Hebrew and Latin runs so terminals with BiDi support display more naturally."""
    text = strip_bidi_controls(text)
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


def _embed_ltr_spans(text: str) -> str:
    """Wrap Latin/code runs in LTR spans without touching HTML tag names."""
    parts = _HTML_TAG.split(text)
    out: list[str] = []
    for index, part in enumerate(parts):
        if index % 2 == 1:
            out.append(part)
        else:
            out.append(
                LTR_EMBED.sub(r'<span dir="ltr" class="ltr-embed">\g<0></span>', part)
            )
    return "".join(out)


def _inline_format(line: str) -> str:
    """Minimal inline markdown → HTML with LTR embeds for Latin/code inside RTL."""
    escaped = html.escape(line)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    if contains_hebrew(line):
        escaped = _embed_ltr_spans(escaped)
    return escaped


def render_answer_html(answer: str) -> str:
    """Convert agent markdown-ish answer to HTML with explicit RTL for Hebrew."""
    answer = strip_bidi_controls(answer or "")
    if not answer.strip():
        return "<p>(empty answer)</p>"

    rtl = hebrew_ratio(answer) >= 0.15
    blocks: list[str] = []
    list_items: list[str] = []

    def flush_list() -> None:
        nonlocal list_items
        if not list_items:
            return
        dir_attr = ' dir="rtl"' if rtl else ""
        blocks.append(f"<ul{dir_attr}>" + "".join(list_items) + "</ul>")
        list_items = []

    for raw_line in answer.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            flush_list()
            continue
        if line.strip() == "---":
            flush_list()
            blocks.append("<hr>")
            continue
        if line.startswith("### "):
            flush_list()
            blocks.append(f"<h3>{_inline_format(line[4:])}</h3>")
            continue
        if line.startswith("## "):
            flush_list()
            blocks.append(f"<h2>{_inline_format(line[3:])}</h2>")
            continue
        if line.startswith("# "):
            flush_list()
            blocks.append(f"<h1>{_inline_format(line[2:])}</h1>")
            continue
        if line.startswith("> "):
            flush_list()
            dir_attr = ' dir="rtl"' if rtl else ""
            blocks.append(f'<blockquote{dir_attr}>{_inline_format(line[2:])}</blockquote>')
            continue
        if line.startswith("- ") or line.startswith("* "):
            list_items.append(f"<li>{_inline_format(line[2:])}</li>")
            continue
        flush_list()
        dir_attr = ' dir="rtl"' if rtl else ""
        blocks.append(f"<p{dir_attr}>{_inline_format(line)}</p>")

    flush_list()
    return "\n".join(blocks)


def write_html_answer_report(
    path: Path,
    *,
    question: str,
    answer: str,
    metadata: dict,
) -> Path:
    """Write an RTL-friendly HTML view of the answer."""
    answer = strip_bidi_controls(answer or "")
    question = strip_bidi_controls(question or "")
    rtl = hebrew_ratio(answer) >= 0.15 or hebrew_ratio(question) >= 0.15
    html_dir = ' dir="rtl"' if rtl else ""
    lang = "he" if rtl else "en"

    meta_rows = "".join(
        f"<tr><th>{html.escape(str(key))}</th><td dir=\"ltr\">{html.escape(str(value))}</td></tr>"
        for key, value in metadata.items()
    )

    question_html = _inline_format(question)
    answer_html = render_answer_html(answer)

    document = f"""<!DOCTYPE html>
<html lang="{lang}"{html_dir}>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Agent answer</title>
  <style>
    body {{
      font-family: "Segoe UI", "Rubik", "Arial Hebrew", Arial, sans-serif;
      margin: 2rem;
      background: #fafafa;
      color: #111;
      line-height: 1.6;
    }}
    .card {{
      background: #fff;
      border: 1px solid #ddd;
      border-radius: 8px;
      padding: 1.25rem 1.5rem;
      max-width: 960px;
      box-shadow: 0 1px 3px rgba(0,0,0,.06);
    }}
    h1.page-title {{ font-size: 1.2rem; margin-top: 0; }}
    .question {{
      background: #f3f4f6;
      padding: 0.75rem 1rem;
      border-radius: 6px;
      margin-bottom: 1rem;
    }}
    .answer h1, .answer h2, .answer h3 {{ margin: 1rem 0 0.5rem; }}
    .answer p, .answer li, .answer blockquote {{ margin: 0.4rem 0; }}
    .answer ul {{ padding-right: 1.25rem; padding-left: 0; }}
    .answer blockquote {{
      border-right: 3px solid #ccc;
      border-left: none;
      margin-right: 0;
      padding-right: 0.75rem;
      color: #444;
    }}
    code {{
      background: #f3f4f6;
      padding: 0.1rem 0.35rem;
      border-radius: 4px;
      font-family: Consolas, "Courier New", monospace;
      direction: ltr;
      unicode-bidi: embed;
    }}
    .ltr-embed {{
      direction: ltr;
      unicode-bidi: embed;
      display: inline-block;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 1.5rem;
      font-size: 0.9rem;
      direction: ltr;
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
<body{html_dir}>
  <div class="card">
    <h1 class="page-title">Graph agent answer</h1>
    <div class="question"{html_dir}>{question_html}</div>
    <div class="answer"{html_dir}>
{answer_html}
    </div>
    <table>{meta_rows}</table>
  </div>
</body>
</html>
"""
    path.write_text(document, encoding="utf-8-sig")
    return path


def open_html_in_browser(path: Path) -> None:
    """Open HTML report in the default browser (Windows-friendly)."""
    resolved = path.resolve()
    uri = resolved.as_uri()
    try:
        if sys.platform == "win32":
            import os

            os.startfile(str(resolved))  # noqa: S606 — intentional on Windows
            return
    except OSError:
        pass
    import webbrowser

    webbrowser.open(uri)
