"""Structured table extraction for standard-document chunks."""

from __future__ import annotations

import copy
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any

from rag.app.standard.chunks import (
    add_chunk_positions,
    dedupe_positions,
    extract_standard_metadata,
    section_path as build_section_path,
    tokenize_chunk,
)
from rag.app.standard.clauses import HeadingMatch, detect_heading
from rag.app.standard.cleanup import clean_section_records, extract_position_tags, normalize_for_detection


TABLE_CAPTION_RE = re.compile(
    r"^(?P<label>Table|表)\s*(?P<number>[A-Z]?(?:\d+(?:\.\d+)*|[A-Z]\.\d+(?:\.\d+)*))"
    r"(?:\s*[-—–:：]?\s*(?P<title>.*))?$",
    re.IGNORECASE,
)
HTML_TABLE_RE = re.compile(r"<table\b.*?</table>", re.IGNORECASE | re.DOTALL)
MARKDOWN_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$")


@dataclass
class TableCaption:
    table_no: str
    title: str
    display: str
    path: list[HeadingMatch] = field(default_factory=list)
    positions: list[list[float]] = field(default_factory=list)


@dataclass
class TableSource:
    raw: Any
    image: Any = None
    positions: list[list[float]] = field(default_factory=list)
    caption: TableCaption | None = None


@dataclass
class ParsedTable:
    text: str
    matrix: list[list[str]]
    ambiguous: bool = False


class SimpleTableHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self.current_row: list[str] | None = None
        self.current_cell: list[str] | None = None
        self.has_spans = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag == "tr":
            self.current_row = []
            return
        if tag in {"td", "th"}:
            if any(name.lower() in {"colspan", "rowspan"} for name, _value in attrs):
                self.has_spans = True
            self.current_cell = []

    def handle_data(self, data: str) -> None:
        if self.current_cell is not None:
            self.current_cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"td", "th"} and self.current_cell is not None:
            if self.current_row is not None:
                self.current_row.append(clean_cell("".join(self.current_cell)))
            self.current_cell = None
            return
        if tag == "tr" and self.current_row is not None:
            if any(cell for cell in self.current_row):
                self.rows.append(self.current_row)
            self.current_row = None


def clean_cell(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def detect_table_caption(line: str, path: list[HeadingMatch] | None = None, positions: list[list[float]] | None = None) -> TableCaption | None:
    display = re.sub(r"\s+", " ", (line or "").strip())
    normalized = normalize_for_detection(display)
    match = TABLE_CAPTION_RE.match(normalized)
    if not match:
        return None
    label = match.group("label")
    if label.lower() == "table":
        label = "Table"
        table_no = f"{label} {match.group('number')}"
    else:
        label = "表"
        table_no = f"{label} {match.group('number')}"
    title = clean_cell(match.group("title") or "")
    return TableCaption(table_no=table_no, title=title, display=display, path=list(path or []), positions=list(positions or []))


def update_heading_stack(stack: list[HeadingMatch], line: str) -> None:
    heading = detect_heading(line)
    if not heading or heading.kind not in {"clause", "annex"}:
        return
    while stack and stack[-1].level >= heading.level:
        stack.pop()
    stack.append(heading)


def collect_table_captions(records: list[tuple[str, list[list[float]]]]) -> list[TableCaption]:
    stack: list[HeadingMatch] = []
    captions: list[TableCaption] = []
    for text, positions in records:
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            update_heading_stack(stack, stripped)
            caption = detect_table_caption(stripped, stack, positions)
            if caption:
                captions.append(caption)
    return captions


def normalize_positions(value: Any) -> list[list[float]]:
    if not value:
        return []
    if isinstance(value, str):
        return extract_position_tags(value)
    if isinstance(value, Iterable):
        normalized: list[list[float]] = []
        for item in value:
            if isinstance(item, (list, tuple)) and len(item) == 5:
                page, left, right, top, bottom = item
                if isinstance(page, list):
                    page = page[0] if page else 0
                try:
                    normalized.append([int(page), float(left), float(right), float(top), float(bottom)])
                except (TypeError, ValueError):
                    continue
        return normalized
    return []


def normalize_parser_tables(tables) -> list[TableSource]:
    sources: list[TableSource] = []
    for item in tables or []:
        image = None
        raw = item
        positions = []
        if isinstance(item, (tuple, list)) and len(item) == 2:
            first, second = item
            positions = normalize_positions(second)
            if isinstance(first, (tuple, list)) and len(first) == 2:
                image, raw = first
            else:
                raw = first
        sources.append(TableSource(raw=raw, image=image, positions=positions))
    return sources


def extract_embedded_table_sources(records: list[tuple[str, list[list[float]]]]) -> list[TableSource]:
    sources: list[TableSource] = []
    stack: list[HeadingMatch] = []
    last_caption: TableCaption | None = None
    for text, positions in records:
        lines = text.splitlines()
        line_index = 0
        while line_index < len(lines):
            line = lines[line_index].strip()
            if line:
                update_heading_stack(stack, line)
                caption = detect_table_caption(line, stack, positions)
                if caption:
                    last_caption = caption
                    line_index += 1
                    continue
            if line_index + 1 < len(lines) and "|" in line and MARKDOWN_SEPARATOR_RE.match(lines[line_index + 1]):
                end = line_index + 2
                while end < len(lines) and "|" in lines[end] and lines[end].strip():
                    end += 1
                sources.append(TableSource(raw="\n".join(lines[line_index:end]), positions=positions, caption=last_caption))
                line_index = end
                continue
            line_index += 1

        for match in HTML_TABLE_RE.finditer(text):
            sources.append(TableSource(raw=match.group(0), positions=positions, caption=last_caption))
    return sources


def parse_html_table(raw: str) -> ParsedTable | None:
    parser = SimpleTableHTMLParser()
    parser.feed(raw)
    matrix = normalize_matrix(parser.rows)
    if not matrix:
        return None
    return ParsedTable(text=matrix_to_markdown(matrix), matrix=matrix, ambiguous=parser.has_spans)


def split_markdown_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [clean_cell(cell) for cell in stripped.split("|")]


def parse_markdown_table(raw: str) -> ParsedTable | None:
    lines = [line.rstrip() for line in str(raw or "").splitlines() if line.strip()]
    if len(lines) < 2:
        return None
    separator_index = next((idx for idx, line in enumerate(lines) if MARKDOWN_SEPARATOR_RE.match(line)), None)
    if separator_index is None or separator_index == 0:
        return None
    header = split_markdown_row(lines[separator_index - 1])
    rows = [split_markdown_row(line) for line in lines[separator_index + 1:] if "|" in line]
    matrix = normalize_matrix([header, *rows])
    if not matrix:
        return None
    return ParsedTable(text=matrix_to_markdown(matrix), matrix=matrix)


def parse_row_sequence(rows: list[Any]) -> ParsedTable | None:
    matrix: list[list[str]] = []
    plain_rows: list[str] = []
    for row in rows:
        if isinstance(row, (list, tuple)):
            matrix.append([clean_cell(cell) for cell in row])
            continue
        row_text = clean_cell(row)
        if not row_text:
            continue
        plain_rows.append(row_text)
        if "\t" in row_text:
            matrix.append([clean_cell(cell) for cell in row_text.split("\t")])
        elif "|" in row_text:
            matrix.append(split_markdown_row(row_text))
        elif "；" in row_text:
            matrix.append([clean_cell(cell) for cell in row_text.split("；")])
        elif "; " in row_text:
            matrix.append([clean_cell(cell) for cell in row_text.split(";")])
    matrix = normalize_matrix(matrix)
    if matrix:
        return ParsedTable(text=matrix_to_markdown(matrix), matrix=matrix)
    text = "\n".join(plain_rows).strip()
    return ParsedTable(text=text, matrix=[]) if text else None


def parse_table(raw: Any) -> ParsedTable | None:
    if isinstance(raw, (list, tuple)):
        return parse_row_sequence(list(raw))
    text = str(raw or "").strip()
    if not text:
        return None
    if "<table" in text.lower():
        parsed = parse_html_table(text)
        if parsed:
            return parsed
    parsed = parse_markdown_table(text)
    if parsed:
        return parsed
    return ParsedTable(text=re.sub(r"\s+", " ", text), matrix=[])


def normalize_matrix(matrix: list[list[str]]) -> list[list[str]]:
    normalized = [[clean_cell(cell) for cell in row] for row in matrix if any(clean_cell(cell) for cell in row)]
    if not normalized:
        return []
    return normalized


def matrix_to_markdown(matrix: list[list[str]]) -> str:
    if not matrix:
        return ""
    width = max(len(row) for row in matrix)
    padded = [row + [""] * (width - len(row)) for row in matrix]
    header = padded[0]
    rows = padded[1:]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] * width) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def is_reliable_row_matrix(matrix: list[list[str]], ambiguous: bool = False) -> bool:
    if ambiguous or len(matrix) < 2:
        return False
    header = [clean_cell(cell) for cell in matrix[0]]
    if len(header) < 2 or any(not cell for cell in header):
        return False
    if len(set(header)) != len(header):
        return False
    data_rows = matrix[1:]
    if not data_rows or len(data_rows) > 100:
        return False
    width = len(header)
    empty = 0
    total = 0
    for row in data_rows:
        if len(row) != width:
            return False
        for cell in row:
            total += 1
            if not clean_cell(cell):
                empty += 1
    return bool(total) and (empty / total) < 0.4


def caption_from_table_text(text: str, path: list[HeadingMatch] | None = None, positions: list[list[float]] | None = None) -> TableCaption | None:
    for line in str(text or "").splitlines()[:3]:
        caption = detect_table_caption(line, path=path, positions=positions)
        if caption:
            return caption
    return None


def select_caption(source: TableSource, captions: list[TableCaption], index: int) -> TableCaption | None:
    if source.caption:
        return source.caption
    inline = caption_from_table_text(str(source.raw or ""), positions=source.positions)
    if inline:
        return inline
    if index < len(captions):
        return captions[index]
    return None


def compose_table_content(parsed: ParsedTable, caption: TableCaption | None) -> str:
    content = parsed.text.strip()
    if caption and caption.display and caption.display not in content:
        return f"{caption.display}\n{content}".strip()
    return content


def add_table_metadata(
    chunk: dict[str, Any],
    *,
    standard_no: str | None,
    standard_year: int | None,
    caption: TableCaption | None,
) -> None:
    if standard_no:
        chunk["standard_no_kwd"] = standard_no
    if standard_year:
        chunk["standard_year_int"] = standard_year
    path = caption.path if caption else []
    if caption:
        chunk["table_no_kwd"] = caption.table_no
        chunk["table_title_tks"] = caption.title
    if path:
        chunk["section_path_kwd"] = build_section_path(standard_no, path)
        chunk["clause_no_kwd"] = path[-1].number
    elif standard_no:
        chunk["section_path_kwd"] = standard_no


def build_row_chunks(
    parsed: ParsedTable,
    base_chunk: dict[str, Any],
    eng: bool,
    tokenize_fn: Callable[[dict[str, Any], str, bool], None],
) -> list[dict[str, Any]]:
    if not is_reliable_row_matrix(parsed.matrix, parsed.ambiguous):
        return []
    header = parsed.matrix[0]
    chunks: list[dict[str, Any]] = []
    for row_index, row in enumerate(parsed.matrix[1:], start=1):
        row_chunk = copy.deepcopy(base_chunk)
        row_chunk["doc_type_kwd"] = "table_row"
        row_chunk["row_index_int"] = row_index
        row_chunk["columns_obj"] = dict(zip(header, row, strict=True))
        row_text = "\n".join(f"- {column}: {value}" for column, value in row_chunk["columns_obj"].items())
        tokenize_fn(row_chunk, row_text, eng)
        chunks.append(row_chunk)
    return chunks


def dedupe_sources(sources: list[TableSource]) -> list[TableSource]:
    deduped: list[TableSource] = []
    seen: set[str] = set()
    for source in sources:
        parsed = parse_table(source.raw)
        if not parsed:
            continue
        key = re.sub(r"\s+", " ", parsed.text).strip().lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(source)
    return deduped


def build_standard_table_chunks(
    sections,
    tables,
    doc: dict[str, Any],
    filename: str,
    eng: bool,
    *,
    tokenize_fn: Callable[[dict[str, Any], str, bool], None] | None = None,
    positions_fn: Callable[[dict[str, Any], list[list[float]]], None] | None = None,
) -> list[dict[str, Any]]:
    records = clean_section_records(sections)
    cleaned_texts = [text for text, _positions in records]
    standard_no, standard_year = extract_standard_metadata(filename, cleaned_texts)
    captions = collect_table_captions(records)
    sources = dedupe_sources(normalize_parser_tables(tables) + extract_embedded_table_sources(records))
    tokenize_fn = tokenize_fn or tokenize_chunk
    positions_fn = positions_fn or add_chunk_positions

    chunks: list[dict[str, Any]] = []
    for index, source in enumerate(sources):
        parsed = parse_table(source.raw)
        if not parsed:
            continue
        caption = select_caption(source, captions, index)
        content = compose_table_content(parsed, caption)
        if not content:
            continue

        table_chunk = copy.deepcopy(doc)
        table_chunk["doc_type_kwd"] = "table"
        add_table_metadata(table_chunk, standard_no=standard_no, standard_year=standard_year, caption=caption)
        if source.image is not None:
            table_chunk["image"] = source.image
        positions = dedupe_positions(source.positions or (caption.positions if caption else []))
        if positions:
            positions_fn(table_chunk, positions)
        tokenize_fn(table_chunk, content, eng)
        chunks.append(table_chunk)
        chunks.extend(build_row_chunks(parsed, table_chunk, eng, tokenize_fn))

    return chunks
