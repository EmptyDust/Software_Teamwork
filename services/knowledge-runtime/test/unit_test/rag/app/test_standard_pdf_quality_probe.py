from __future__ import annotations

from rag.app.standard import pdf_quality_probe as probe


def test_classifies_empty_text_as_ocr_required():
    result = probe.classify_text_quality("", sampled_pages=[1, 2, 3], page_count=3)
    assert result.quality == probe.QUALITY_OCR_REQUIRED
    assert result.reason == probe.REASON_EMPTY_TEXT_LAYER


def test_classifies_low_density_text_as_ocr_required():
    result = probe.classify_text_quality("short", sampled_pages=[1, 10, 20], page_count=20)
    assert result.quality == probe.QUALITY_OCR_REQUIRED
    assert result.reason == probe.REASON_LOW_TEXT_DENSITY


def test_classifies_cid_markers_as_garbled():
    result = probe.classify_text_quality("normal (cid:123) text", sampled_pages=[1], page_count=1)
    assert result.quality == probe.QUALITY_GARBLED
    assert result.reason == probe.REASON_GARBLED_TEXT
    assert result.cid_marker_count == 1


def test_classifies_text_rich_sample_as_text():
    text = "This is a usable standard document text layer. " * 20
    result = probe.classify_text_quality(text, sampled_pages=[1, 2, 3], page_count=3)
    assert result.quality == probe.QUALITY_TEXT
    assert result.reason == probe.REASON_TEXT_LAYER_OK


def test_sample_page_numbers_are_first_middle_last():
    assert probe.sample_page_numbers(0) == []
    assert probe.sample_page_numbers(1) == [1]
    assert probe.sample_page_numbers(10) == [1, 5, 10]
