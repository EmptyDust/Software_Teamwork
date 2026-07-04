"""Build runtime chunks for standard-document clauses."""

from __future__ import annotations

import copy
import re
from collections.abc import Callable
from typing import Any

from rag.app.standard.clauses import HeadingMatch, flatten_clauses, parse_clauses
from rag.app.standard.cleanup import clean_section_records


STANDARD_NO_RE = re.compile(r"\b([A-Z]{1,6}[/-]?\s*(?:D)?\d{2,5}(?:[-:]\d{2,4}[a-z]?)?)\b")
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def extract_standard_metadata(filename: str, texts: list[str]) -> tuple[str | None, int | None]:
    haystack = filename + "\n" + "\n".join(texts[:3])
    standard_no = None
    match = STANDARD_NO_RE.search(haystack)
    if match:
        standard_no = re.sub(r"\s+", " ", match.group(1)).strip()
    year_match = YEAR_RE.search(haystack)
    year = int(year_match.group(0)) if year_match else None
    return standard_no, year


def section_path(standard_no: str | None, path: list[HeadingMatch]) -> str:
    parts = [standard_no] if standard_no else []
    for heading in path:
        label = heading.number if heading.kind != "annex" else f"Annex {heading.number}"
        title = f"{label} {heading.title}".strip()
        parts.append(title)
    return " > ".join(part for part in parts if part)


def split_long_text(text: str, max_chars: int = 5000) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.extend(split_oversized_paragraph(paragraph, max_chars))
            continue
        if current and len(current) + len(paragraph) + 1 > max_chars:
            chunks.append(current)
            current = paragraph
        else:
            current = f"{current}\n{paragraph}" if current else paragraph
    if current:
        chunks.append(current)
    return chunks or [text]


def split_oversized_paragraph(paragraph: str, max_chars: int) -> list[str]:
    pieces: list[str] = []
    remaining = paragraph.strip()
    while len(remaining) > max_chars:
        cut_at = remaining.rfind(" ", 0, max_chars)
        if cut_at < max_chars // 2:
            cut_at = max_chars
        pieces.append(remaining[:cut_at].strip())
        remaining = remaining[cut_at:].strip()
    if remaining:
        pieces.append(remaining)
    return pieces


def chunkable_nodes(nodes) -> list[tuple[Any, list[HeadingMatch]]]:
    flattened = flatten_clauses(nodes)
    has_headings = any(node.heading for node, _path in flattened)
    selected = [
        (node, path)
        for node, path in flattened
        if node.heading and (not node.children or has_clause_body(node))
    ]
    if selected:
        return selected
    if has_headings:
        return []
    return [(node, path) for node, path in flattened if node.text.strip()]


def has_clause_body(node) -> bool:
    lines = [line.strip() for line in node.text.splitlines() if line.strip()]
    if not lines:
        return False
    if not node.heading:
        return True
    return any(line != node.heading.display_heading and line != node.heading.title for line in lines[1:])


def dedupe_positions(positions: list[list[float]]) -> list[list[float]]:
    out: list[list[float]] = []
    seen: set[tuple[float, ...]] = set()
    for position in positions:
        key = tuple(position)
        if key in seen:
            continue
        seen.add(key)
        out.append(position)
    return out


def add_chunk_positions(chunk: dict[str, Any], positions: list[list[float]]) -> None:
    from rag.nlp import add_positions

    add_positions(chunk, positions)


def tokenize_chunk(chunk: dict[str, Any], text: str, eng: bool) -> None:
    from rag.nlp import tokenize

    tokenize(chunk, text, eng)


def build_standard_clause_chunks(
    sections,
    doc: dict[str, Any],
    filename: str,
    eng: bool,
    *,
    tokenize_fn: Callable[[dict[str, Any], str, bool], None] | None = None,
    positions_fn: Callable[[dict[str, Any], list[list[float]]], None] | None = None,
) -> list[dict[str, Any]]:
    records = clean_section_records(sections)
    cleaned_texts = [text for text, _positions in records]
    if not cleaned_texts:
        return []

    standard_no, standard_year = extract_standard_metadata(filename, cleaned_texts)
    nodes = parse_clauses(cleaned_texts, [positions for _text, positions in records])
    flattened = chunkable_nodes(nodes)
    chunks: list[dict[str, Any]] = []
    tokenize_fn = tokenize_fn or tokenize_chunk
    positions_fn = positions_fn or add_chunk_positions

    for idx, (node, path) in enumerate(flattened):
        text = node.text.strip()
        if not text:
            continue
        heading = node.heading
        for part_index, part in enumerate(split_long_text(text)):
            chunk = copy.deepcopy(doc)
            chunk["doc_type_kwd"] = "clause"
            if standard_no:
                chunk["standard_no_kwd"] = standard_no
            if standard_year:
                chunk["standard_year_int"] = standard_year
            if heading:
                chunk["clause_no_kwd"] = heading.number
                chunk["clause_title_tks"] = heading.title
                chunk["section_path_kwd"] = section_path(standard_no, path)
            else:
                chunk["section_path_kwd"] = standard_no or filename
            chunk["chunk_part_int"] = part_index + 1
            positions = dedupe_positions(node.positions)
            if positions:
                positions_fn(chunk, positions)
            tokenize_fn(chunk, part, eng)
            chunks.append(chunk)

    return chunks
