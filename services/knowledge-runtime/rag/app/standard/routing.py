"""Backend routing for opt-in standard-document parsing."""

from __future__ import annotations

from typing import Any, Callable

from rag.app.standard.config import get_standard_document_config
from rag.app.standard.pdf_quality_probe import (
    QUALITY_GARBLED,
    QUALITY_OCR_REQUIRED,
    QUALITY_TEXT,
    PDFQualityProbeResult,
    probe_pdf_quality,
)


class StandardOCRRoutingError(RuntimeError):
    """Raised when standard mode requires OCR but no safe OCR route exists."""


def select_standard_pdf_backend(
    *,
    filename: str,
    binary: bytes | None,
    parser_config: dict[str, Any],
    scope_id: str | None,
    callback: Callable[[float, str], None] | None = None,
    first_model_resolver: Callable[[str, str, Any], str | None] | None = None,
    env_model_resolver: Callable[[str], str | None] | None = None,
    probe_func: Callable[[str, bytes | None], PDFQualityProbeResult] | None = None,
    ocr_model_type: Any = None,
) -> tuple[str, str | None, PDFQualityProbeResult | None]:
    standard_config = get_standard_document_config(parser_config)
    layout_recognizer = parser_config.get("layout_recognize", "DeepDOC")
    parser_model_name = None
    probe = None

    if not standard_config.enabled:
        return layout_recognizer, parser_model_name, probe

    if not standard_config.auto_ocr:
        if str(layout_recognizer).strip().lower() == "auto":
            layout_recognizer = standard_config.text_backend
        return layout_recognizer, parser_model_name, probe

    probe_runner = probe_func or (lambda fn, data: probe_pdf_quality(fn, binary=data))
    probe = probe_runner(filename, binary)
    if probe.quality == QUALITY_TEXT:
        layout_recognizer = standard_config.text_backend
    elif probe.quality in {QUALITY_OCR_REQUIRED, QUALITY_GARBLED}:
        if standard_config.ocr_backend.strip().lower() != "paddleocr":
            raise StandardOCRRoutingError(f"Standard document requires OCR but OCR backend {standard_config.ocr_backend!r} is not supported")
        if not scope_id:
            raise StandardOCRRoutingError("Standard document requires OCR but runtime scope is not configured")
        try:
            parser_model_name = (first_model_resolver(scope_id, "PaddleOCR", ocr_model_type) if first_model_resolver else None) or (env_model_resolver(scope_id) if env_model_resolver else None)
        except Exception as exc:
            raise StandardOCRRoutingError("Standard document requires OCR but PaddleOCR credentials are not configured") from exc
        if not parser_model_name:
            raise StandardOCRRoutingError("Standard document requires OCR but PaddleOCR credentials are not configured")
        layout_recognizer = "PaddleOCR"
    elif str(layout_recognizer).strip().lower() == "auto":
        layout_recognizer = standard_config.text_backend

    parser_config["standard_pdf_quality"] = probe.to_dict()
    parser_config["standard_selected_backend"] = layout_recognizer
    if callback:
        callback(0.08, f"Standard PDF probe: {probe.quality} ({probe.reason}); backend={layout_recognizer}")

    return layout_recognizer, parser_model_name, probe
