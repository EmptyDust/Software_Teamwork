"""Evaluate a local standard-document PDF corpus.

The probe mode is intentionally lightweight: it only inspects PDF metadata and
sampled text layers. It does not read environment secrets, call OCR providers,
or require runtime services.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


TOOL_VERSION = 1
DEFAULT_MAX_PREVIEW_CHARS = 500
DEFAULT_CHUNK_TOKEN_NUM = 512
DEFAULT_DELIMITER = "\n!?。；！？"

BUCKET_ZERO_TEXT = "zero_text"
BUCKET_LT_100 = "lt_100_chars"
BUCKET_100_TO_999 = "chars_100_to_999"
BUCKET_GTE_1000 = "gte_1000_chars"
TEXT_BUCKETS = (BUCKET_ZERO_TEXT, BUCKET_LT_100, BUCKET_100_TO_999, BUCKET_GTE_1000)

CID_PATTERN = re.compile(r"\(cid\s*:\s*\d+\s*\)", re.IGNORECASE)
GARBLED_RATIO_THRESHOLD = 0.30


def sanitize_text(text: str) -> str:
    """Return text that can be safely written as UTF-8 JSON/Markdown."""
    return (text or "").encode("utf-8", errors="replace").decode("utf-8")


@dataclass
class PdfProbe:
    file: str
    size_bytes: int
    page_count: int
    sampled_pages: list[int]
    sampled_chars: int
    bucket: str
    cid_marker_count: int
    garbled_char_count: int
    garbled_ratio: float
    text_preview: str = ""
    error: str | None = None

    @property
    def is_garbled_candidate(self) -> bool:
        return self.cid_marker_count > 0 or self.garbled_ratio >= GARBLED_RATIO_THRESHOLD


def sample_page_numbers(page_count: int) -> list[int]:
    """Return 1-based first/middle/last page numbers without duplicates."""
    if page_count <= 0:
        return []
    if page_count == 1:
        return [1]
    middle = (page_count + 1) // 2
    return sorted({1, middle, page_count})


def bucket_for_chars(char_count: int) -> str:
    if char_count <= 0:
        return BUCKET_ZERO_TEXT
    if char_count < 100:
        return BUCKET_LT_100
    if char_count < 1000:
        return BUCKET_100_TO_999
    return BUCKET_GTE_1000


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
    for ch in text:
        if ch.isspace():
            continue
        total += 1
        if is_garbled_char(ch):
            garbled += 1
    ratio = garbled / total if total else 0.0
    return garbled, ratio, len(CID_PATTERN.findall(text or ""))


def preview_text(text: str, max_chars: int = DEFAULT_MAX_PREVIEW_CHARS) -> str:
    collapsed = re.sub(r"\s+", " ", sanitize_text(text)).strip()
    if max_chars <= 0 or len(collapsed) <= max_chars:
        return collapsed
    return collapsed[: max_chars - 1].rstrip() + "…"


def find_pdfs(input_dir: Path) -> list[Path]:
    return sorted((path for path in input_dir.rglob("*") if path.is_file() and path.suffix.lower() == ".pdf"), key=lambda path: path.relative_to(input_dir).as_posix().lower())


def relative_pdf_path(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def safe_file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return -1


def file_list_sha256(pdf_paths: list[Path], root: Path) -> str:
    digest = hashlib.sha256()
    for path in pdf_paths:
        line = f"{relative_pdf_path(path, root)}\t{safe_file_size(path)}\n"
        digest.update(line.encode("utf-8"))
    return digest.hexdigest()


def probe_pdf(path: Path, root: Path, max_preview_chars: int = DEFAULT_MAX_PREVIEW_CHARS) -> PdfProbe:
    rel_path = relative_pdf_path(path, root)
    size_bytes = safe_file_size(path)
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        page_count = len(reader.pages)
        sampled_pages = sample_page_numbers(page_count)
        page_texts: list[str] = []
        page_errors: list[str] = []
        for page_no in sampled_pages:
            try:
                page_texts.append(reader.pages[page_no - 1].extract_text() or "")
            except Exception as exc:  # noqa: BLE001 - keep corpus evaluation resilient.
                page_errors.append(f"page {page_no}: {type(exc).__name__}: {exc}")

        sampled_text = "\n".join(page_texts)
        sampled_chars = non_whitespace_count(sampled_text)
        garbled_count, garbled_ratio, cid_count = garbled_metrics(sampled_text)
        return PdfProbe(
            file=rel_path,
            size_bytes=size_bytes,
            page_count=page_count,
            sampled_pages=sampled_pages,
            sampled_chars=sampled_chars,
            bucket=bucket_for_chars(sampled_chars),
            cid_marker_count=cid_count,
            garbled_char_count=garbled_count,
            garbled_ratio=round(garbled_ratio, 4),
            text_preview=preview_text(sampled_text, max_preview_chars),
            error=sanitize_text("; ".join(page_errors)) if page_errors else None,
        )
    except Exception as exc:  # noqa: BLE001 - record bad PDFs without aborting the run.
        return PdfProbe(
            file=rel_path,
            size_bytes=size_bytes,
            page_count=0,
            sampled_pages=[],
            sampled_chars=0,
            bucket=BUCKET_ZERO_TEXT,
            cid_marker_count=0,
            garbled_char_count=0,
            garbled_ratio=0.0,
            error=sanitize_text(f"{type(exc).__name__}: {exc}"),
        )


def summarize_text_probe(probes: list[PdfProbe]) -> dict[str, int]:
    summary = {bucket: 0 for bucket in TEXT_BUCKETS}
    summary["garbled_candidates"] = 0
    summary["read_errors"] = 0
    for probe in probes:
        summary[probe.bucket] = summary.get(probe.bucket, 0) + 1
        if probe.is_garbled_candidate:
            summary["garbled_candidates"] += 1
        if probe.error:
            summary["read_errors"] += 1
    return summary


def chunk_text(chunk: dict[str, Any]) -> str:
    value = chunk.get("content_with_weight")
    if value is None:
        value = chunk.get("content")
    return str(value or "")


def empty_runtime_parse(mode: str, configured_backend: str, skipped_reason: str) -> dict[str, Any]:
    return {
        "mode": mode,
        "configured_backend": configured_backend,
        "attempted": 0,
        "ready": 0,
        "failed": 0,
        "empty_outputs": 0,
        "skipped_reason": skipped_reason,
        "documents": [],
    }


def run_current_parser_sample(pdf_paths: list[Path], root: Path, sample_size: int, layout_recognize: str, max_preview_chars: int) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    runtime_parse = empty_runtime_parse("current", layout_recognize, "parse_sample_not_requested")
    chunks_summary = {
        "total": 0,
        "empty": 0,
        "avg_chars": 0,
        "median_chars": 0,
        "table_chunks": 0,
    }
    samples: list[dict[str, Any]] = []

    if sample_size <= 0:
        return runtime_parse, chunks_summary, samples

    try:
        from rag.app import naive
    except Exception as exc:  # noqa: BLE001 - heavy runtime imports may be unavailable locally.
        runtime_parse["skipped_reason"] = f"parser_import_failed: {type(exc).__name__}: {exc}"
        return runtime_parse, chunks_summary, samples

    runtime_parse["skipped_reason"] = None
    parser_config = {
        "chunk_token_num": DEFAULT_CHUNK_TOKEN_NUM,
        "delimiter": DEFAULT_DELIMITER,
        "layout_recognize": layout_recognize,
        "analyze_hyperlink": False,
    }
    lengths: list[int] = []
    selected = pdf_paths[:sample_size]
    runtime_parse["attempted"] = len(selected)

    def noop_callback(*_args: Any, **_kwargs: Any) -> None:
        return None

    for path in selected:
        rel_path = relative_pdf_path(path, root)
        doc_result = {"file": rel_path, "backend": layout_recognize, "status": "failed", "chunk_count": 0, "empty_chunks": 0, "table_chunks": 0, "error": None}
        try:
            chunks = naive.chunk(
                path.name,
                binary=path.read_bytes(),
                callback=noop_callback,
                parser_config=dict(parser_config),
                is_root=False,
            ) or []
            doc_result["chunk_count"] = len(chunks)
            doc_result["empty_chunks"] = sum(1 for chunk in chunks if not chunk_text(chunk).strip())
            doc_result["table_chunks"] = sum(1 for chunk in chunks if str(chunk.get("doc_type_kwd") or "").lower() == "table")
            if chunks and doc_result["empty_chunks"] < len(chunks):
                doc_result["status"] = "ready"
                runtime_parse["ready"] += 1
            else:
                doc_result["status"] = "empty"
                runtime_parse["empty_outputs"] += 1

            for chunk in chunks:
                text = chunk_text(chunk)
                lengths.append(len(text))
                if len(samples) < 5 and text.strip():
                    samples.append(
                        {
                            "file": rel_path,
                            "page": None,
                            "kind": "current_chunk",
                            "text_preview": preview_text(text, max_preview_chars),
                        }
                    )
        except Exception as exc:  # noqa: BLE001 - record per-document parser failures.
            doc_result["error"] = f"{type(exc).__name__}: {exc}"
            runtime_parse["failed"] += 1
        runtime_parse["documents"].append(doc_result)

    chunks_summary["total"] = sum(doc["chunk_count"] for doc in runtime_parse["documents"])
    chunks_summary["empty"] = sum(doc["empty_chunks"] for doc in runtime_parse["documents"])
    chunks_summary["table_chunks"] = sum(doc["table_chunks"] for doc in runtime_parse["documents"])
    if lengths:
        chunks_summary["avg_chars"] = round(sum(lengths) / len(lengths), 2)
        chunks_summary["median_chars"] = statistics.median(lengths)

    return runtime_parse, chunks_summary, samples


def build_report(input_dir: Path, mode: str, parse_sample: int, layout_recognize: str, max_preview_chars: int) -> dict[str, Any]:
    root = input_dir.resolve()
    if not root.exists():
        raise FileNotFoundError(f"input directory does not exist: {input_dir}")
    if not root.is_dir():
        raise NotADirectoryError(f"input path is not a directory: {input_dir}")

    started_at = datetime.now().astimezone().isoformat(timespec="seconds")
    pdf_paths = find_pdfs(root)
    probes = [probe_pdf(path, root, max_preview_chars=max_preview_chars) for path in pdf_paths]

    if mode == "current":
        runtime_parse, chunks_summary, parser_samples = run_current_parser_sample(pdf_paths, root, parse_sample, layout_recognize, max_preview_chars)
    else:
        runtime_parse = empty_runtime_parse(mode, layout_recognize, "probe_only")
        chunks_summary = {
            "total": 0,
            "empty": 0,
            "avg_chars": 0,
            "median_chars": 0,
            "table_chunks": 0,
        }
        parser_samples = []

    probe_samples = [
        {
            "file": probe.file,
            "page": probe.sampled_pages[0] if probe.sampled_pages else None,
            "kind": "probe_text",
            "text_preview": probe.text_preview,
        }
        for probe in probes
        if probe.text_preview
    ][:5]

    return {
        "run": {
            "input_dir": str(input_dir),
            "mode": mode,
            "started_at": started_at,
            "tool_version": TOOL_VERSION,
        },
        "corpus": {
            "pdf_count": len(pdf_paths),
            "total_pages": sum(probe.page_count for probe in probes),
            "file_list_sha256": file_list_sha256(pdf_paths, root),
        },
        "text_probe": summarize_text_probe(probes),
        "runtime_parse": runtime_parse,
        "chunks": chunks_summary,
        "samples": probe_samples + parser_samples,
        "documents": [asdict(probe) | {"garbled_candidate": probe.is_garbled_candidate} for probe in probes],
    }


def write_json(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def render_summary(report: dict[str, Any]) -> str:
    corpus = report["corpus"]
    text_probe = report["text_probe"]
    runtime_parse = report["runtime_parse"]
    chunks = report["chunks"]

    lines = [
        "# Standard Corpus Baseline",
        "",
        f"- Input: `{report['run']['input_dir']}`",
        f"- Mode: `{report['run']['mode']}`",
        f"- Started at: `{report['run']['started_at']}`",
        f"- Tool version: `{report['run']['tool_version']}`",
        "",
        "## Corpus",
        "",
        f"- PDFs: {corpus['pdf_count']}",
        f"- Pages: {corpus['total_pages']}",
        f"- File list SHA256: `{corpus['file_list_sha256']}`",
        "",
        "## Text Probe",
        "",
        "| Bucket | Count |",
        "| --- | ---: |",
        f"| zero text | {text_probe.get(BUCKET_ZERO_TEXT, 0)} |",
        f"| 1-99 chars | {text_probe.get(BUCKET_LT_100, 0)} |",
        f"| 100-999 chars | {text_probe.get(BUCKET_100_TO_999, 0)} |",
        f"| 1000+ chars | {text_probe.get(BUCKET_GTE_1000, 0)} |",
        f"| garbled candidates | {text_probe.get('garbled_candidates', 0)} |",
        f"| read errors | {text_probe.get('read_errors', 0)} |",
        "",
        "## Runtime Parse",
        "",
        f"- Configured backend: `{runtime_parse.get('configured_backend')}`",
        f"- Attempted: {runtime_parse.get('attempted', 0)}",
        f"- Ready: {runtime_parse.get('ready', 0)}",
        f"- Failed: {runtime_parse.get('failed', 0)}",
        f"- Empty outputs: {runtime_parse.get('empty_outputs', 0)}",
        f"- Skipped reason: `{runtime_parse.get('skipped_reason')}`",
        "",
        "## Chunks",
        "",
        f"- Total chunks: {chunks.get('total', 0)}",
        f"- Empty chunks: {chunks.get('empty', 0)}",
        f"- Average chars: {chunks.get('avg_chars', 0)}",
        f"- Median chars: {chunks.get('median_chars', 0)}",
        f"- Table chunks: {chunks.get('table_chunks', 0)}",
        "",
        "## Samples",
        "",
    ]

    samples = report.get("samples") or []
    if not samples:
        lines.append("- No text samples captured.")
    else:
        for sample in samples:
            page = sample.get("page")
            page_label = f" page {page}" if page else ""
            lines.append(f"- `{sample.get('file')}`{page_label} ({sample.get('kind')}): {sample.get('text_preview')}")

    lines.extend(
        [
            "",
            "## Safety",
            "",
            "This artifact is generated from local source PDFs. It does not include OCR tokens, provider credentials, or copied source PDFs.",
        ]
    )
    return "\n".join(lines) + "\n"


def write_summary(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_summary(report), encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate a local standard-document PDF corpus.")
    parser.add_argument("--input", required=True, type=Path, help="Directory containing standard PDFs.")
    parser.add_argument("--output", required=True, type=Path, help="Path for machine-readable JSON output.")
    parser.add_argument("--summary", required=True, type=Path, help="Path for Markdown summary output.")
    parser.add_argument("--mode", choices=("probe", "current"), default="current", help="Evaluation mode. Current mode may also run parser sampling when --parse-sample is set.")
    parser.add_argument("--parse-sample", type=int, default=0, help="Number of PDFs to run through the current parser path. Default 0 keeps evaluation probe-only.")
    parser.add_argument("--layout-recognize", default="DeepDOC", help="Current parser backend to report/use for --parse-sample.")
    parser.add_argument("--max-preview-chars", type=int, default=DEFAULT_MAX_PREVIEW_CHARS, help="Maximum characters per local preview snippet.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(
        input_dir=args.input,
        mode=args.mode,
        parse_sample=max(0, args.parse_sample),
        layout_recognize=args.layout_recognize,
        max_preview_chars=max(0, args.max_preview_chars),
    )
    write_json(args.output, report)
    write_summary(args.summary, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
