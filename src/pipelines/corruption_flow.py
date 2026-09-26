from __future__ import annotations

import sys

import pandas as pd

from core.config import load_settings
from core.utils import read_json
from evaluation.metrics import evaluate_pipeline
from ingestion.corruption import corrupt_clean_dataframe
from observability.quality import build_freshness_report, run_data_quality_checks
from retrieval.index import LocalEmbeddingIndex


def main() -> None:
    """CP4: inject 6 corruption scenarios and measure how far the RAG pipeline degrades.

    TODO(CP5): idempotent repair from data/raw/crossref_records.json + 3-state
    (baseline vs corrupted vs repaired) comparison report at data/reports/corruption_report.md.
    """
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    settings = load_settings()

    baseline_metrics = read_json(settings.paths.baseline_metrics)
    clean_df = pd.read_json(settings.paths.clean_json)

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

    print(f"Tín hiệu hoàn thành: CP4 đã tiêm 6 lỗi dữ liệu ({len(clean_df)} -> {len(corrupted_df)} dòng).")
    print(
        "Retrieval hit rate: baseline="
        f"{baseline_metrics['retrieval_hit_rate']:.2f} -> corrupted={corrupted_bundle.summary['retrieval_hit_rate']:.2f}"
    )
    print(
        "Mean token F1: baseline="
        f"{baseline_metrics['mean_token_f1']:.2f} -> corrupted={corrupted_bundle.summary['mean_token_f1']:.2f}"
    )
    print(f"Data quality gate (corrupted): success={corrupted_quality['success']}")
    print(f"Freshness SLA (corrupted): is_fresh={corrupted_freshness['is_fresh']}")


if __name__ == "__main__":
    main()
