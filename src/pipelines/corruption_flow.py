from __future__ import annotations

import sys

import pandas as pd

from core.config import load_settings
from core.utils import now_utc, read_json
from evaluation.metrics import evaluate_pipeline
from ingestion.cleaning import build_clean_dataframe
from ingestion.corruption import corrupt_clean_dataframe
from ingestion.crossref import load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_corruption_report
from retrieval.index import LocalEmbeddingIndex


def main() -> None:
    """CP4+CP5: inject corruption, measure degradation, repair from raw, compare 3 states."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    settings = load_settings()

    baseline_metrics = read_json(settings.paths.baseline_metrics)
    clean_df = pd.read_json(settings.paths.clean_json)

    # --- CP4: corrupt the clean dataset and measure the degradation. ---
    corrupted_df = corrupt_clean_dataframe(clean_df, settings.paths.corruption_log)

    settings.paths.corrupted_clean_csv.parent.mkdir(parents=True, exist_ok=True)
    corrupted_df.to_csv(settings.paths.corrupted_clean_csv, index=False)
    corrupted_df.to_json(settings.paths.corrupted_clean_json, orient="records", indent=2, force_ascii=False)

    corrupted_index = LocalEmbeddingIndex.build(corrupted_df, settings, settings.paths.corrupted_embeddings_json)

    corrupted_bundle = evaluate_pipeline(
        settings=settings,
        index=corrupted_index,
        test_set_path=settings.paths.eval_testset,
        metrics_output_path=settings.paths.corrupted_metrics,
        answers_output_path=settings.paths.corrupted_answers,
    )

    corrupted_quality = run_data_quality_checks(corrupted_df, settings, "corrupted")
    corrupted_freshness = build_freshness_report(
        corrupted_df, settings, settings.paths.quality_dir / "corrupted_freshness_report.json"
    )

    # --- CP5: idempotent repair. Rebuild straight from the immutable raw snapshot, so the
    # corrupted clean/embeddings artifacts are never touched or repaired in place. ---
    raw_records = load_raw_records(settings.paths.raw_records_json)
    repaired_df = build_clean_dataframe(raw_records, now_utc())

    settings.paths.repaired_clean_csv.parent.mkdir(parents=True, exist_ok=True)
    repaired_df.to_csv(settings.paths.repaired_clean_csv, index=False)
    repaired_df.to_json(settings.paths.repaired_clean_json, orient="records", indent=2, force_ascii=False)

    repaired_index = LocalEmbeddingIndex.build(repaired_df, settings, settings.paths.repaired_embeddings_json)

    repaired_bundle = evaluate_pipeline(
        settings=settings,
        index=repaired_index,
        test_set_path=settings.paths.eval_testset,
        metrics_output_path=settings.paths.repaired_metrics,
        answers_output_path=settings.paths.repaired_answers,
    )

    repaired_quality = run_data_quality_checks(repaired_df, settings, "repaired")
    repaired_freshness = build_freshness_report(
        repaired_df, settings, settings.paths.quality_dir / "repaired_freshness_report.json"
    )

    # --- 3-state comparison report. ---
    generate_corruption_report(
        report_path=settings.paths.comparison_report,
        baseline_metrics=baseline_metrics,
        corrupted_metrics=corrupted_bundle.summary,
        repaired_metrics=repaired_bundle.summary,
        corrupted_quality=corrupted_quality,
        repaired_quality=repaired_quality,
        corrupted_freshness=corrupted_freshness,
        repaired_freshness=repaired_freshness,
    )

    print(f"Tín hiệu hoàn thành: CP4 đã tiêm 6 lỗi dữ liệu ({len(clean_df)} -> {len(corrupted_df)} dòng).")
    print(f"Tín hiệu hoàn thành: CP5 đã phục hồi dữ liệu từ raw ({len(repaired_df)} dòng) và sinh báo cáo đối chiếu.")
    print(
        "Retrieval hit rate: baseline="
        f"{baseline_metrics['retrieval_hit_rate']:.2f}"
        f" -> corrupted={corrupted_bundle.summary['retrieval_hit_rate']:.2f}"
        f" -> repaired={repaired_bundle.summary['retrieval_hit_rate']:.2f}"
    )
    print(
        "Mean token F1: baseline="
        f"{baseline_metrics['mean_token_f1']:.2f}"
        f" -> corrupted={corrupted_bundle.summary['mean_token_f1']:.2f}"
        f" -> repaired={repaired_bundle.summary['mean_token_f1']:.2f}"
    )
    print(
        f"Data quality gate: corrupted success={corrupted_quality['success']}"
        f" -> repaired success={repaired_quality['success']}"
    )
    print(
        f"Freshness SLA: corrupted is_fresh={corrupted_freshness['is_fresh']}"
        f" -> repaired is_fresh={repaired_freshness['is_fresh']}"
    )
    print(f"Báo cáo đối chiếu: {settings.paths.comparison_report}")


if __name__ == "__main__":
    main()
