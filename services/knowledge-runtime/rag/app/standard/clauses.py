"""Clause detection for standards."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from rag.app.standard.cleanup import normalize_for_detection


@dataclass
class HeadingMatch:
    kind: str
    number: str
    title: str
    level: int
    display_heading: str


@dataclass
class ClauseNode:
    heading: HeadingMatch | None
    text: str = ""
    children: list["ClauseNode"] = field(default_factory=list)
    positions: list[list[float]] = field(default_factory=list)


NUMERIC_HEADING_RE = re.compile(r"^(?P<number>\d+(?:\.\d+)*)(?:\s+|[、.．])(?P<title>\S.*)?$")
ANNEX_RE = re.compile(r"^(?P<label>Annex|Appendix)\s+(?P<number>[A-Z])(?:\s+(?P<title>.*))?$", re.IGNORECASE)
CN_ANNEX_RE = re.compile(r"^附录\s*(?P<number>[A-Z0-9])(?:\s+(?P<title>.*))?$", re.IGNORECASE)
NOTE_RE = re.compile(r"^(?P<label>NOTE|注)\s*(?P<number>\d+)?(?:\s+(?P<title>.*))?$", re.IGNORECASE)
TABLE_RE = re.compile(r"^(?P<label>Table|表)\s*(?P<number>[A-Z]?\d+(?:\.\d+)*)(?:\s*[-—–]?\s*(?P<title>.*))?$", re.IGNORECASE)


def detect_heading(line: str) -> HeadingMatch | None:
    display = (line or "").strip()
    normalized = normalize_for_detection(display)
    if not normalized:
        return None

    match = NUMERIC_HEADING_RE.match(normalized)
    if match:
        number = match.group("number")
        title = (match.group("title") or "").strip()
        return HeadingMatch("clause", number, title, number.count(".") + 1, display)

    match = ANNEX_RE.match(normalized) or CN_ANNEX_RE.match(normalized)
    if match:
        number = match.group("number")
        title = (match.group("title") or "").strip()
        return HeadingMatch("annex", number, title, 1, display)

    match = NOTE_RE.match(normalized)
    if match:
        number = match.group("number") or ""
        title = (match.group("title") or "").strip()
        return HeadingMatch("note", number, title, 99, display)

    match = TABLE_RE.match(normalized)
    if match:
        number = match.group("number")
        title = (match.group("title") or "").strip()
        return HeadingMatch("table_caption", number, title, 99, display)

    return None


def parse_clauses(texts: list[str], positions_by_text: list[list[list[float]]] | None = None) -> list[ClauseNode]:
    nodes: list[ClauseNode] = []
    stack: list[ClauseNode] = []
    current: ClauseNode | None = None

    for text_index, text in enumerate(texts):
        block_positions = positions_by_text[text_index] if positions_by_text and text_index < len(positions_by_text) else []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            heading = detect_heading(line)
            if heading and heading.kind in {"clause", "annex"}:
                node = ClauseNode(heading=heading, text=line, positions=list(block_positions))
                while stack and stack[-1].heading and stack[-1].heading.level >= heading.level:
                    stack.pop()
                if stack:
                    stack[-1].children.append(node)
                else:
                    nodes.append(node)
                stack.append(node)
                current = node
                continue

            if current is None:
                current = ClauseNode(heading=None, text=line, positions=list(block_positions))
                nodes.append(current)
            else:
                current.text = f"{current.text}\n{line}" if current.text else line
                if block_positions:
                    current.positions.extend(block_positions)

    return nodes


def flatten_clauses(nodes: list[ClauseNode], ancestors: list[HeadingMatch] | None = None) -> list[tuple[ClauseNode, list[HeadingMatch]]]:
    ancestors = ancestors or []
    out: list[tuple[ClauseNode, list[HeadingMatch]]] = []
    for node in nodes:
        path = ancestors + ([node.heading] if node.heading else [])
        out.append((node, path))
        out.extend(flatten_clauses(node.children, path))
    return out
