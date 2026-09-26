from __future__ import annotations

from datetime import UTC, datetime

from core.config import load_settings
from evaluation.metrics import evaluate_pipeline
from evaluation.testset import build_test_set
from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import fetch_source_records, load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_phase1_report
from retrieval.index import LocalEmbeddingIndex


def main() -> None:
    settings = load_settings()

    if settings.paths.raw_records_json.exists() and not settings.refresh_source:
        records = load_raw_records(settings.paths.raw_records_json)
    else:
        records = fetch_source_records(settings)

    run_date = datetime.now(UTC)
    df = build_clean_dataframe(records, run_date)

    settings.paths.clean_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(settings.paths.clean_csv, index=False)
    df.to_json(settings.paths.clean_json, orient="records", indent=2, force_ascii=False)

    index = LocalEmbeddingIndex.build(df, settings)

    if settings.paths.eval_testset.exists() and not settings.refresh_test_set:
        test_set_path = settings.paths.eval_testset
    else:
        build_test_set(df, settings.paths.eval_testset)
        test_set_path = settings.paths.eval_testset

    bundle = evaluate_pipeline(
        settings=settings,
        index=index,
        test_set_path=test_set_path,
        metrics_output_path=settings.paths.baseline_metrics,
        answers_output_path=settings.paths.baseline_answers,
    )

    quality = run_data_quality_checks(df, settings, "baseline")
    freshness = build_freshness_report(df, settings, settings.paths.freshness_report)

    source_summary = {
        "total_documents": len(df),
        "collection_name": index.collection_name,
        "embedding_model": settings.embedding_model,
        "run_date": run_date.isoformat(),
    }

    generate_phase1_report(
        report_path=settings.paths.baseline_report,
        source_summary=source_summary,
        metrics=bundle.summary,
        quality=quality,
        freshness=freshness,
    )

    print(f"Tín hiệu hoàn thành: Phase1 pipeline chạy xong với {len(df)} tài liệu.")
    print(f"Retrieval hit rate: {bundle.summary['retrieval_hit_rate']:.2f}")


if __name__ == "__main__":
    main()
