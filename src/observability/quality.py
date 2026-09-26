from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import great_expectations as gx
import great_expectations.expectations as gxe
import pandas as pd

from core.config import Settings


def run_data_quality_checks(df: pd.DataFrame, settings: Settings, report_name: str) -> dict[str, Any]:
    """Chay bo Great Expectations 1.x quality checks tren dataframe."""
    context = gx.get_context(mode="ephemeral")
    data_source = context.data_sources.add_pandas(name=f"{report_name}_source")
    data_asset = data_source.add_dataframe_asset(name=f"{report_name}_asset")
    batch_def = data_asset.add_batch_definition_whole_dataframe(f"{report_name}_batch")
    batch = batch_def.get_batch(batch_parameters={"dataframe": df})

    suite = context.suites.add(gx.ExpectationSuite(name=f"{report_name}_suite"))
    suite.add_expectation(
        gxe.ExpectTableRowCountToBeBetween(min_value=1, max_value=1000)
    )
    suite.add_expectation(gxe.ExpectColumnValuesToNotBeNull(column="paper_id"))
    suite.add_expectation(gxe.ExpectColumnValuesToBeUnique(column="paper_id"))
    suite.add_expectation(gxe.ExpectColumnValuesToNotBeNull(column="title"))
    suite.add_expectation(
        gxe.ExpectColumnValueLengthsToBeBetween(column="summary", min_value=10, max_value=5000)
    )

    validation_result = batch.validate(suite)
    result = validation_result.to_json_dict()

    settings.paths.quality_dir.mkdir(parents=True, exist_ok=True)
    report_path = settings.paths.quality_dir / f"{report_name}_quality_report.json"
    report_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")

    return result


def build_freshness_report(df: pd.DataFrame, settings: Settings, report_path) -> dict[str, Any]:
    """Tong hop freshness report dua tren age_days va Freshness SLA."""
    total_rows = len(df)
    published = pd.to_datetime(df["published"], errors="coerce", utc=True)

    stale_mask = df["age_days"] > settings.freshness_threshold_days
    stale_rows = int(stale_mask.sum())
    stale_ratio = stale_rows / total_rows if total_rows else 0.0

    report = {
        "latest_published": published.max().date().isoformat() if total_rows else None,
        "oldest_published": published.min().date().isoformat() if total_rows else None,
        "stale_rows": stale_rows,
        "total_rows": total_rows,
        "stale_ratio": stale_ratio,
        "freshness_threshold_days": settings.freshness_threshold_days,
        "is_fresh": stale_ratio <= 0.25,
    }

    report_path = Path(report_path) if not isinstance(report_path, Path) else report_path
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    return report
