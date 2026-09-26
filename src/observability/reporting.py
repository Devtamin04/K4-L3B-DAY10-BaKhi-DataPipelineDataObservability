from __future__ import annotations

from pathlib import Path
from typing import Any


def generate_phase1_report(
    report_path,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
) -> None:
    """Viet markdown report cho baseline phase."""
    lines = [
        "# Phase 1 Report — Baseline RAG Pipeline",
        "",
        "## Nguồn dữ liệu",
        f"- Tổng số tài liệu: {source_summary.get('total_documents')}",
        f"- ChromaDB collection: `{source_summary.get('collection_name')}`",
        f"- Embedding model: `{source_summary.get('embedding_model')}`",
        f"- Thời điểm chạy: {source_summary.get('run_date')}",
        "",
        "## Chỉ số đánh giá RAG",
        f"- Số câu hỏi test: {metrics.get('samples')}",
        f"- Retrieval Hit Rate: {metrics.get('retrieval_hit_rate'):.2%}",
        f"- Mean Token F1: {metrics.get('mean_token_f1'):.2%}",
        f"- Judge Accuracy: {metrics.get('judge_accuracy'):.2%}",
        f"- Mean Judge Score: {metrics.get('mean_judge_score'):.2f} / 5",
        "",
        "## Data Quality (Great Expectations)",
        f"- Trạng thái: {'PASS' if quality.get('success') else 'FAIL'}",
        "",
        "## Freshness SLA",
        f"- Tổng số dòng: {freshness.get('total_rows')}",
        f"- Số dòng stale (> {freshness.get('threshold_days')} ngày): {freshness.get('stale_rows')}",
        f"- Tỷ lệ stale: {freshness.get('stale_ratio'):.2%}",
        f"- Is fresh: {'✅ YES' if freshness.get('is_fresh') else '❌ NO'}",
        f"- Bài mới nhất: {freshness.get('latest_published')}",
        f"- Bài cũ nhất: {freshness.get('oldest_published')}",
        "",
    ]

    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")


def generate_corruption_report(
    report_path,
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
) -> None:
    """TODO(student): viet markdown report so sanh baseline/corrupted/repaired."""
    raise NotImplementedError("Student task: implement corruption comparison report.")
