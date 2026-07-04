from __future__ import annotations

import json
from pathlib import Path

from tools import evaluate_standard_corpus as evaluator


def _probe(file: str, chars: int, pages: int = 1, preview: str = "preview", error: str | None = None) -> evaluator.PdfProbe:
    garbled_count, garbled_ratio, cid_count = evaluator.garbled_metrics(preview)
    return evaluator.PdfProbe(
        file=file,
        size_bytes=123,
        page_count=pages,
        sampled_pages=evaluator.sample_page_numbers(pages),
        sampled_chars=chars,
        bucket=evaluator.bucket_for_chars(chars),
        cid_marker_count=cid_count,
        garbled_char_count=garbled_count,
        garbled_ratio=round(garbled_ratio, 4),
        text_preview=evaluator.preview_text(preview),
        error=error,
    )


def test_sample_page_numbers_are_first_middle_last_unique():
    assert evaluator.sample_page_numbers(0) == []
    assert evaluator.sample_page_numbers(1) == [1]
    assert evaluator.sample_page_numbers(2) == [1, 2]
    assert evaluator.sample_page_numbers(3) == [1, 2, 3]
    assert evaluator.sample_page_numbers(10) == [1, 5, 10]


def test_bucket_for_chars_matches_baseline_boundaries():
    assert evaluator.bucket_for_chars(0) == evaluator.BUCKET_ZERO_TEXT
    assert evaluator.bucket_for_chars(99) == evaluator.BUCKET_LT_100
    assert evaluator.bucket_for_chars(100) == evaluator.BUCKET_100_TO_999
    assert evaluator.bucket_for_chars(999) == evaluator.BUCKET_100_TO_999
    assert evaluator.bucket_for_chars(1000) == evaluator.BUCKET_GTE_1000


def test_garbled_metrics_detects_cid_and_private_use_chars():
    garbled_count, ratio, cid_count = evaluator.garbled_metrics("normal (cid:123) \uE000")
    assert cid_count == 1
    assert garbled_count == 1
    assert ratio > 0
    assert evaluator.garbled_metrics("normal text")[2] == 0


def test_preview_text_replaces_invalid_surrogates():
    preview = evaluator.preview_text("bad \ud835 text")
    assert "\ud835" not in preview
    assert "bad" in preview


def test_build_report_counts_pdf_buckets_with_relative_files(tmp_path: Path, monkeypatch):
    input_dir = tmp_path / "standards"
    nested = input_dir / "nested"
    nested.mkdir(parents=True)
    (input_dir / "a.pdf").write_bytes(b"%PDF fake")
    (nested / "b.PDF").write_bytes(b"%PDF fake")
    (nested / "ignored.txt").write_text("not a pdf")

    def fake_probe(path: Path, root: Path, max_preview_chars: int = evaluator.DEFAULT_MAX_PREVIEW_CHARS) -> evaluator.PdfProbe:
        rel = path.relative_to(root).as_posix()
        if rel == "a.pdf":
            return _probe(rel, 0, pages=2, preview="")
        return _probe(rel, 1200, pages=3, preview="This is useful standard text.")

    monkeypatch.setattr(evaluator, "probe_pdf", fake_probe)
    report = evaluator.build_report(input_dir, mode="probe", parse_sample=0, layout_recognize="DeepDOC", max_preview_chars=80)

    assert report["corpus"]["pdf_count"] == 2
    assert report["corpus"]["total_pages"] == 5
    assert report["text_probe"][evaluator.BUCKET_ZERO_TEXT] == 1
    assert report["text_probe"][evaluator.BUCKET_GTE_1000] == 1
    assert report["runtime_parse"]["skipped_reason"] == "probe_only"
    assert [doc["file"] for doc in report["documents"]] == ["a.pdf", "nested/b.PDF"]
    assert report["backend_selection"]["ocr_routed_document_count"] == 1
    assert report["backend_selection"]["selected_backend_counts"]["PaddleOCR"] == 1
    assert report["backend_selection"]["selected_backend_counts"]["DeepDOC"] == 1


def test_main_writes_json_and_markdown_without_env_secret(tmp_path: Path, monkeypatch):
    input_dir = tmp_path / "standards"
    input_dir.mkdir()
    (input_dir / "a.pdf").write_bytes(b"%PDF fake")
    output = tmp_path / "baseline.json"
    summary = tmp_path / "baseline.md"
    monkeypatch.setenv("PADDLEOCR_ACCESS_TOKEN", "sk-test-should-not-leak")

    def fake_probe(path: Path, root: Path, max_preview_chars: int = evaluator.DEFAULT_MAX_PREVIEW_CHARS) -> evaluator.PdfProbe:
        rel = path.relative_to(root).as_posix()
        return _probe(rel, 42, pages=1, preview="short text")

    monkeypatch.setattr(evaluator, "probe_pdf", fake_probe)
    rc = evaluator.main(
        [
            "--input",
            str(input_dir),
            "--output",
            str(output),
            "--summary",
            str(summary),
            "--mode",
            "current",
        ]
    )

    assert rc == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["corpus"]["pdf_count"] == 1
    assert payload["runtime_parse"]["skipped_reason"] == "parse_sample_not_requested"
    combined = output.read_text(encoding="utf-8") + summary.read_text(encoding="utf-8")
    assert "sk-test-should-not-leak" not in combined
    assert "Standard Corpus Baseline" in summary.read_text(encoding="utf-8")


def test_report_records_clause_chunk_coverage_when_parse_sample_requested(tmp_path: Path, monkeypatch):
    input_dir = tmp_path / "standards"
    input_dir.mkdir()
    pdf_path = input_dir / "a.pdf"
    pdf_path.write_bytes(b"%PDF fake")

    class FakePage:
        def extract_text(self):
            return "1 Scope\nThis standard covers testing.\n1.1 Terms are defined here."

    class FakeReader:
        pages = [FakePage()]

        def __init__(self, _path):
            pass

    def fake_probe(path: Path, root: Path, max_preview_chars: int = evaluator.DEFAULT_MAX_PREVIEW_CHARS) -> evaluator.PdfProbe:
        rel = path.relative_to(root).as_posix()
        return _probe(rel, 1200, pages=1, preview="1 Scope This standard covers testing.")

    def fake_build_standard_clause_chunks(_sections, _doc, _filename, eng, tokenize_fn=None, positions_fn=None):
        assert eng is True
        assert tokenize_fn is evaluator.lightweight_tokenize_chunk
        assert positions_fn is evaluator.lightweight_add_positions
        return [
            {"doc_type_kwd": "clause", "clause_no_kwd": "1", "section_path_kwd": "1 Scope", "content_with_weight": "1 Scope\nThis standard covers testing."},
            {"doc_type_kwd": "clause", "clause_no_kwd": "1.1", "section_path_kwd": "1 Scope > 1.1 Terms", "content_with_weight": "1.1 Terms are defined here."},
        ]

    monkeypatch.setattr(evaluator, "probe_pdf", fake_probe)
    monkeypatch.setitem(__import__("sys").modules, "pypdf", type("FakePypdf", (), {"PdfReader": FakeReader}))
    monkeypatch.setattr(evaluator, "load_standard_clause_chunk_builder", lambda: fake_build_standard_clause_chunks)

    report = evaluator.build_report(input_dir, mode="probe", parse_sample=1, layout_recognize="DeepDOC", max_preview_chars=80)

    assert report["standard_clause_chunking"]["total_clause_chunks"] == 2
    assert report["chunks"]["clause_chunks"] == 2
    assert report["chunks"]["section_path_coverage"] == 1
    assert report["chunks"]["clean_public_content_coverage"] == 1
