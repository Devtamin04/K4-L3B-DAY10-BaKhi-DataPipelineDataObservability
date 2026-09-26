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


def _pct(value: Any) -> str:
    return f"{value:.2%}" if isinstance(value, (int, float)) else "n/a"


def _pass_fail(success: Any) -> str:
    return "✅ PASS" if success else "❌ FAIL"


def _delta_pct(baseline: Any, other: Any) -> str:
    if not isinstance(baseline, (int, float)) or not isinstance(other, (int, float)):
        return "n/a"
    delta = (other - baseline) * 100
    sign = "+" if delta >= 0 else ""
    return f"{sign}{delta:.1f} pp"


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
    """Viet markdown report so sanh 3 trang thai: Baseline vs Corrupted vs Repaired."""
    rows = [
        ("Retrieval Hit Rate", "retrieval_hit_rate", _pct),
        ("Mean Token F1", "mean_token_f1", _pct),
        ("Judge Accuracy", "judge_accuracy", _pct),
        ("Mean Judge Score", "mean_judge_score", lambda v: f"{v:.2f} / 5" if isinstance(v, (int, float)) else "n/a"),
    ]

    table_lines = [
        "| Chỉ số | Baseline | Corrupted | Repaired | Δ Corrupted | Δ Repaired |",
        "| :--- | :---: | :---: | :---: | :---: | :---: |",
    ]
    for label, key, fmt in rows:
        baseline_value = baseline_metrics.get(key)
        corrupted_value = corrupted_metrics.get(key)
        repaired_value = repaired_metrics.get(key)
        table_lines.append(
            f"| {label} | {fmt(baseline_value)} | {fmt(corrupted_value)} | {fmt(repaired_value)} | "
            f"{_delta_pct(baseline_value, corrupted_value)} | {_delta_pct(baseline_value, repaired_value)} |"
        )

    recovered = (
        repaired_metrics.get("retrieval_hit_rate") is not None
        and baseline_metrics.get("retrieval_hit_rate") is not None
        and repaired_metrics["retrieval_hit_rate"] >= baseline_metrics["retrieval_hit_rate"]
        and repaired_metrics.get("mean_token_f1", 0) >= corrupted_metrics.get("mean_token_f1", 0)
    )

    lines = [
        "# Corruption Report — Baseline vs Corrupted vs Repaired",
        "",
        "## Bảng đối chiếu chỉ số RAG",
        "",
        *table_lines,
        "",
        "## Data Quality Gate (Great Expectations)",
        f"- Corrupted: {_pass_fail(corrupted_quality.get('success'))}"
        f" ({len(corrupted_quality.get('failed_checks', []))} expectation thất bại: "
        f"{', '.join(corrupted_quality.get('failed_checks', [])) or 'none'})",
        f"- Repaired: {_pass_fail(repaired_quality.get('success'))}",
        "",
        "## Freshness SLA",
        f"- Corrupted: is_fresh={corrupted_freshness.get('is_fresh')} "
        f"({corrupted_freshness.get('stale_rows')}/{corrupted_freshness.get('total_rows')} dòng stale)",
        f"- Repaired: is_fresh={repaired_freshness.get('is_fresh')} "
        f"({repaired_freshness.get('stale_rows')}/{repaired_freshness.get('total_rows')} dòng stale)",
        "",
        "## Kết luận",
        (
            "Khi dữ liệu bị tiêm lỗi (drop latest, blank/noisy summary, truncated title, stale date, "
            "duplicate rows), RAG Agent suy giảm chất lượng một cách âm thầm (Silent Failure): hit rate và "
            "token F1 giảm so với Baseline trong khi Agent vẫn trả lời bình thường, không tự báo lỗi. "
            "Data Quality Gate (GX) phát hiện đúng các vi phạm (uniqueness, độ dài title/summary). "
            + (
                "Sau khi chạy Idempotent Repair (rebuild lại từ `crossref_records.json` — nguồn Raw không bị "
                "ảnh hưởng bởi corruption), Agent phục hồi phong độ về mức tương đương hoặc tốt hơn Baseline."
                if recovered
                else "Sau khi chạy Idempotent Repair, các chỉ số cải thiện trở lại nhưng cần rà soát thêm nếu "
                "vẫn còn chênh lệch so với Baseline."
            )
        ),
        "",
    ]

    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")
