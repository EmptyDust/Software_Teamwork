"""Lightweight PDF text-layer quality probe for standard documents."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


QUALITY_TEXT = "text"
QUALITY_OCR_REQUIRED = "ocr_required"
QUALITY_GARBLED = "garbled"
QUALITY_UNKNOWN = "unknown"

REASON_TEXT_LAYER_OK = "text_layer_ok"
REASON_EMPTY_TEXT_LAYER = "empty_text_layer"
REASON_LOW_TEXT_DENSITY = "low_text_density"
REASON_GARBLED_TEXT = "garbled_text"
REASON_PROBE_FAILED = "probe_failed"

MIN_TOTAL_TEXT_CHARS = 50
MIN_AVG_TEXT_CHARS_PER_PAGE = 100
GARBLED_RATIO_THRESHOLD = 0.30
CID_PATTERN = re.compile(r"\(cid\s*:\s*\d+\s*\)", re.IGNORECASE)


@dataclass(frozen=True)
class PDFQualityProbeResult:
    quality: str
    sampled_pages: list[int]
    text_chars: int
    garbled_ratio: float
    reason: str
    page_count: int = 0
    cid_marker_count: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def sample_page_numbers(page_count: int) -> list[int]:
    if page_count <= 0:
        return []
    if page_count == 1:
        return [1]
    middle = (page_count + 1) // 2
    return sorted({1, middle, page_count})


def non_whitespace_count(text: str) -> int:
    return sum(1 for ch in text if not ch.isspace())


def is_garbled_char(ch: str) -> bool:
    if not ch:
        return False
    cp = ord(ch)
    if 0xE000 <= cp <= 0xF8FF:
        return True
    if 0xF0000 <= cp <= 0xFFFFF:
        return True
    if 0x100000 <= cp <= 0x10FFFF:
        return True
    if cp == 0xFFFD:
        return True
    if cp < 0x20 and ch not in ("\t", "\n", "\r"):
        return True
    if 0x80 <= cp <= 0x9F:
        return True
    return False


def garbled_metrics(text: str) -> tuple[int, float, int]:
    total = 0
    garbled = 0
    for ch in text or "":
        if ch.isspace():
            continue
        total += 1
        if is_garbled_char(ch):
            garbled += 1
    ratio = garbled / total if total else 0.0
    return garbled, ratio, len(CID_PATTERN.findall(text or ""))


def classify_text_quality(text: str, sampled_pages: list[int], page_count: int = 0) -> PDFQualityProbeResult:
    text_chars = non_whitespace_count(text or "")
    _garbled_count, garbled_ratio, cid_count = garbled_metrics(text or "")
    rounded_ratio = round(garbled_ratio, 4)

    if cid_count > 0 or garbled_ratio >= GARBLED_RATIO_THRESHOLD:
        return PDFQualityProbeResult(
            quality=QUALITY_GARBLED,
            sampled_pages=sampled_pages,
            text_chars=text_chars,
            garbled_ratio=rounded_ratio,
            reason=REASON_GARBLED_TEXT,
            page_count=page_count,
            cid_marker_count=cid_count,
        )

    if text_chars == 0:
        return PDFQualityProbeResult(
            quality=QUALITY_OCR_REQUIRED,
            sampled_pages=sampled_pages,
            text_chars=text_chars,
            garbled_ratio=rounded_ratio,
            reason=REASON_EMPTY_TEXT_LAYER,
            page_count=page_count,
            cid_marker_count=cid_count,
        )

    avg_chars = text_chars / max(1, len(sampled_pages))
    if text_chars < MIN_TOTAL_TEXT_CHARS or avg_chars < MIN_AVG_TEXT_CHARS_PER_PAGE:
        return PDFQualityProbeResult(
            quality=QUALITY_OCR_REQUIRED,
            sampled_pages=sampled_pages,
            text_chars=text_chars,
            garbled_ratio=rounded_ratio,
            reason=REASON_LOW_TEXT_DENSITY,
            page_count=page_count,
            cid_marker_count=cid_count,
        )

    return PDFQualityProbeResult(
        quality=QUALITY_TEXT,
        sampled_pages=sampled_pages,
        text_chars=text_chars,
        garbled_ratio=rounded_ratio,
        reason=REASON_TEXT_LAYER_OK,
        page_count=page_count,
        cid_marker_count=cid_count,
    )


def probe_pdf_quality(filename: str | Path, binary: bytes | None = None) -> PDFQualityProbeResult:
    try:
        from io import BytesIO

        from pypdf import PdfReader

        reader = PdfReader(BytesIO(binary)) if binary is not None else PdfReader(str(filename))
        page_count = len(reader.pages)
        sampled_pages = sample_page_numbers(page_count)
        page_texts: list[str] = []
        for page_no in sampled_pages:
            page_texts.append(reader.pages[page_no - 1].extract_text() or "")
        return classify_text_quality("\n".join(page_texts), sampled_pages=sampled_pages, page_count=page_count)
    except Exception as exc:  # noqa: BLE001 - probe must not crash the generic parser path.
        return PDFQualityProbeResult(
            quality=QUALITY_UNKNOWN,
            sampled_pages=[],
            text_chars=0,
            garbled_ratio=0.0,
            reason=REASON_PROBE_FAILED,
            error=f"{type(exc).__name__}: {exc}",
        )
