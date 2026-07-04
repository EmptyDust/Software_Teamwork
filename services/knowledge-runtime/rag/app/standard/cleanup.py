"""Deterministic cleanup for standard-document text blocks."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import Iterable


POSITION_TAG_RE = re.compile(r"@@[0-9-]+\t[0-9.\t-]+##")
PAGE_NUMBER_RE = re.compile(r"^\s*(?:[-–—]\s*)?\d+\s*(?:[-–—])?\s*$")
URL_RE = re.compile(r"https?://\S+|www\.\S+|[\w.+-]+@[\w.-]+")
BOILERPLATE_RE = re.compile(
    r"(download|copyright|licensed to|provided by|www\.[^\s]+|仅供|下载|标准分享网|"
    r"all rights reserved)",
    re.IGNORECASE,
)
WORD_SPLIT_RE = re.compile(r"([A-Za-z]{2,})-\n([a-z]{2,})")
PREFIX_HYPHEN_RE = re.compile(r"\b(non|pre|post|semi|anti|multi|micro|macro|sub|re)-\n(?=[A-Z])", re.IGNORECASE)
UNIT_TOKENS = {"c", "f", "g", "h", "kg", "kpa", "l", "m", "mg", "min", "ml", "mm", "mpa", "pa", "s"}


def normalize_for_detection(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "")


def section_text(section) -> str:
    if isinstance(section, (tuple, list)) and section:
        text = str(section[0] or "")
        if len(section) > 1 and isinstance(section[1], str) and "@@" in section[1]:
            text += section[1]
        return text
    return str(section or "")


def normalize_line_for_repetition(line: str) -> str:
    line = strip_position_tags(line)
    line = normalize_for_detection(line)
    line = re.sub(r"\d+", "#", line)
    line = re.sub(r"\s+", " ", line).strip().lower()
    return line


def collect_repeated_noise_lines(texts: Iterable[str], min_count: int = 3) -> set[str]:
    counter: Counter[str] = Counter()
    original_by_norm: dict[str, str] = {}
    for text in texts:
        seen_in_block = set()
        lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
        candidates = lines[:3] + lines[-3:] if len(lines) > 6 else lines
        for line in candidates:
            display_line = strip_position_tags(line).strip()
            normalized = normalize_line_for_repetition(line)
            if not normalized or PAGE_NUMBER_RE.match(display_line):
                continue
            if len(normalized) > 160:
                continue
            if normalized in seen_in_block:
                continue
            seen_in_block.add(normalized)
            original_by_norm.setdefault(normalized, line)
            counter[normalized] += 1
    return {norm for norm, count in counter.items() if count >= min_count and not looks_like_clause_heading(original_by_norm.get(norm, ""))}


def looks_like_clause_heading(line: str) -> bool:
    normalized = normalize_for_detection(strip_position_tags(line)).strip()
    return bool(re.match(r"^(\d+(?:\.\d+)*|Annex\s+[A-Z]|Appendix\s+[A-Z]|附录\s*[A-Z0-9])\b", normalized, re.IGNORECASE))


def remove_noise_lines(text: str, repeated_noise: set[str]) -> str:
    kept: list[str] = []
    for raw_line in str(text or "").splitlines():
        line = strip_position_tags(raw_line).strip()
        normalized = normalize_line_for_repetition(line)
        if not line:
            kept.append("")
            continue
        if PAGE_NUMBER_RE.match(line):
            continue
        if normalized in repeated_noise:
            continue
        if BOILERPLATE_RE.search(line) and not looks_like_clause_heading(line):
            continue
        kept.append(raw_line)
    return "\n".join(kept)


def repair_dehyphenation(text: str) -> str:
    protected: list[str] = []

    def protect(match: re.Match[str]) -> str:
        protected.append(match.group(0))
        return f"__STANDARD_URL_{len(protected) - 1}__"

    working = URL_RE.sub(protect, text or "")
    working = PREFIX_HYPHEN_RE.sub(lambda m: f"{m.group(1)}-", working)

    def repair_word_split(match: re.Match[str]) -> str:
        left = match.group(1)
        right = match.group(2)
        if left.isupper() or left.lower() in UNIT_TOKENS or right.lower() in UNIT_TOKENS:
            return f"{left}-{right}"
        return f"{left}{right}"

    working = WORD_SPLIT_RE.sub(repair_word_split, working)
    for idx, value in enumerate(protected):
        working = working.replace(f"__STANDARD_URL_{idx}__", value)
    return working


def strip_position_tags(text: str) -> str:
    return POSITION_TAG_RE.sub("", text or "")


def extract_position_tags(text: str) -> list[list[float]]:
    positions: list[list[float]] = []
    for tag in POSITION_TAG_RE.findall(text or ""):
        fields = tag.strip("#").strip("@").split("\t")
        if len(fields) != 5:
            continue
        pages, left, right, top, bottom = fields
        try:
            first_page = int(pages.split("-")[0]) - 1
            positions.append([first_page, float(left), float(right), float(top), float(bottom)])
        except ValueError:
            continue
    return positions


def is_block_boundary(line: str) -> bool:
    normalized = normalize_for_detection(line).strip()
    if not normalized:
        return True
    if looks_like_clause_heading(normalized):
        return True
    if re.match(r"^(NOTE|Note|注)\s*\d*", normalized):
        return True
    if re.match(r"^(Table|表)\s*[A-Z]?\d", normalized, re.IGNORECASE):
        return True
    if re.match(r"^[-*•]\s+", normalized):
        return True
    return False


def merge_hard_wrapped_lines(text: str) -> str:
    paragraphs: list[str] = []
    current = ""
    for raw_line in (text or "").splitlines():
        line = strip_position_tags(raw_line).strip()
        if not line:
            if current:
                paragraphs.append(current)
                current = ""
            continue
        if is_block_boundary(line):
            if current:
                paragraphs.append(current)
            current = line
            continue
        if not current:
            current = line
        elif is_block_boundary(current):
            current += "\n" + line
        elif current.endswith((".", ":", ";", "?", "!", "。", "：", "；", "？", "！")):
            paragraphs.append(current)
            current = line
        else:
            current += " " + line
    if current:
        paragraphs.append(current)
    return "\n".join(paragraphs)


def clean_sections(sections) -> list[str]:
    return [text for text, _positions in clean_section_records(sections)]


def clean_section_records(sections) -> list[tuple[str, list[list[float]]]]:
    texts = [section_text(section) for section in sections or []]
    repeated_noise = collect_repeated_noise_lines(texts)
    cleaned = []
    for text in texts:
        positions = extract_position_tags(text)
        text = remove_noise_lines(text, repeated_noise)
        text = repair_dehyphenation(text)
        text = merge_hard_wrapped_lines(text)
        if text.strip():
            cleaned.append((text.strip(), positions))
    return cleaned
