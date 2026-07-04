import pytest

from rag.app.standard.pdf_quality_probe import PDFQualityProbeResult
from rag.app.standard.routing import select_standard_pdf_backend


def _config(**overrides):
    standard_document = {
        "enabled": True,
        "auto_ocr": True,
        "text_backend": "DeepDOC",
        "ocr_backend": "PaddleOCR",
    }
    standard_document.update(overrides.pop("standard_document", {}))
    return {"layout_recognize": "Auto", "standard_document": standard_document, **overrides}


def _probe(quality: str, reason: str = "test") -> PDFQualityProbeResult:
    return PDFQualityProbeResult(
        quality=quality,
        sampled_pages=[1],
        text_chars=1000,
        garbled_ratio=0.0,
        reason=reason,
        page_count=1,
    )


def test_standard_disabled_preserves_layout_recognizer():
    layout, model, probe = select_standard_pdf_backend(
        filename="a.pdf",
        binary=b"",
        parser_config={"layout_recognize": "DeepDOC"},
        scope_id=None,
        callback=None,
    )
    assert layout == "DeepDOC"
    assert model is None
    assert probe is None


def test_text_quality_selects_text_backend():
    layout, model, probe = select_standard_pdf_backend(
        filename="a.pdf",
        binary=b"",
        parser_config=_config(),
        scope_id=None,
        callback=None,
        probe_func=lambda *_args: _probe("text"),
    )
    assert layout == "DeepDOC"
    assert model is None
    assert probe.quality == "text"


def test_ocr_required_resolves_paddleocr_model():
    layout, model, probe = select_standard_pdf_backend(
        filename="a.pdf",
        binary=b"",
        parser_config=_config(),
        scope_id="tenant",
        callback=None,
        probe_func=lambda *_args: _probe("ocr_required"),
        first_model_resolver=lambda *_args: "PP-StructureV3@PP-StructureV3@PaddleOCR",
    )
    assert layout == "PaddleOCR"
    assert model == "PP-StructureV3@PP-StructureV3@PaddleOCR"
    assert probe.quality == "ocr_required"


def test_missing_paddleocr_credentials_fail_safely():
    with pytest.raises(RuntimeError, match="PaddleOCR credentials are not configured"):
        select_standard_pdf_backend(
            filename="a.pdf",
            binary=b"",
            parser_config=_config(),
            scope_id="tenant",
            callback=None,
            probe_func=lambda *_args: _probe("ocr_required"),
            first_model_resolver=lambda *_args: None,
            env_model_resolver=lambda *_args: None,
        )


def test_missing_scope_for_ocr_fails_safely():
    with pytest.raises(RuntimeError, match="runtime scope is not configured"):
        select_standard_pdf_backend(
            filename="a.pdf",
            binary=b"",
            parser_config=_config(),
            scope_id=None,
            callback=None,
            probe_func=lambda *_args: _probe("garbled"),
        )
