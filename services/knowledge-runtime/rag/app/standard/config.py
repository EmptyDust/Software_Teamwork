"""Configuration helpers for opt-in standard-document parsing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


DEFAULT_TEXT_BACKEND = "DeepDOC"
DEFAULT_OCR_BACKEND = "PaddleOCR"


@dataclass(frozen=True)
class StandardDocumentConfig:
    enabled: bool = False
    auto_ocr: bool = True
    text_backend: str = DEFAULT_TEXT_BACKEND
    ocr_backend: str = DEFAULT_OCR_BACKEND
    cleanup: bool = True
    clause_chunking: bool = True
    extract_tables: bool = True


def _bool_value(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def _str_value(value: Any, default: str) -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


def get_standard_document_config(parser_config: dict[str, Any] | None) -> StandardDocumentConfig:
    raw = (parser_config or {}).get("standard_document")
    if not isinstance(raw, dict):
        return StandardDocumentConfig(enabled=False)

    return StandardDocumentConfig(
        enabled=_bool_value(raw.get("enabled"), False),
        auto_ocr=_bool_value(raw.get("auto_ocr"), True),
        text_backend=_str_value(raw.get("text_backend"), DEFAULT_TEXT_BACKEND),
        ocr_backend=_str_value(raw.get("ocr_backend"), DEFAULT_OCR_BACKEND),
        cleanup=_bool_value(raw.get("cleanup"), True),
        clause_chunking=_bool_value(raw.get("clause_chunking"), True),
        extract_tables=_bool_value(raw.get("extract_tables"), True),
    )
