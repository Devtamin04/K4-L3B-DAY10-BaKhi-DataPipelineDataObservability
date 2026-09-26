from __future__ import annotations

import json
import math
import os
from typing import Any

# GX 1.x sends usage analytics by default; keep the lab offline unless the user opts in.
os.environ.setdefault("GX_ANALYTICS_ENABLED", "False")

import great_expectations as gx
from great_expectations.data_context.types.base import ProgressBarsConfig
import pandas as pd

from core.config import Settings
from core.utils import now_utc, write_json

MIN_ROW_RATIO = 0.8
TITLE_MIN_CHARS = 8
SUMMARY_MIN_CHARS = 100
SUMMARY_MAX_CHARS = 5000
MAX_STALE_RATIO = 0.25
NOT_NULL_COLUMNS = ("paper_id", "title", "summary", "published", "text_for_embedding")


def _jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def _build_suite(settings: Settings, suite_name: str) -> gx.ExpectationSuite:
    suite = gx.ExpectationSuite(name=suite_name)
    suite.add_expectation(
        gx.expectations.ExpectTableRowCountToBeBetween(
            min_value=math.ceil(settings.max_results * MIN_ROW_RATIO),
            max_value=settings.max_results,
        )
    )
    for column in NOT_NULL_COLUMNS:
        suite.add_expectation(gx.expectations.ExpectColumnValuesToNotBeNull(column=column))
    suite.add_expectation(gx.expectations.ExpectColumnValuesToBeUnique(column="paper_id"))
    suite.add_expectation(gx.expectations.ExpectColumnValueLengthsToBeBetween(column="title", min_value=TITLE_MIN_CHARS))
    suite.add_expectation(
        gx.expectations.ExpectColumnValueLengthsToBeBetween(
            column="summary",
            min_value=SUMMARY_MIN_CHARS,
            max_value=SUMMARY_MAX_CHARS,
        )
    )
    # Freshness SLA inside the gate: at most MAX_STALE_RATIO of rows may be older than the threshold.
    suite.add_expectation(
        gx.expectations.ExpectColumnValuesToBeBetween(
            column="age_days",
            min_value=0,
            max_value=settings.freshness_threshold_days,
            mostly=1 - MAX_STALE_RATIO,
        )
    )
    return suite


def run_data_quality_checks(df: pd.DataFrame, settings: Settings, report_name: str) -> dict[str, Any]:
    """Validate `df` with a GX 1.x ephemeral context and write the report to `data/quality/`.

    Writes `<report_name>_quality_report.json` (summary) plus the raw GX suite and validation
    result under `data/quality/gx/` as evidence.
    """
    context = gx.get_context(mode="ephemeral")
    context.variables.progress_bars = ProgressBarsConfig(globally=False)
    data_source = context.data_sources.add_pandas(name="papers_source")
    data_asset = data_source.add_dataframe_asset(name="papers_asset")
    batch_def = data_asset.add_batch_definition_whole_dataframe("papers_batch")
    batch = batch_def.get_batch(batch_parameters={"dataframe": df})

    suite = context.suites.add(_build_suite(settings, f"{report_name}_papers_suite"))
    validation = batch.validate(suite)

    checks: list[dict[str, Any]] = []
    for result in validation.results:
        config = result.expectation_config
        kwargs = {key: value for key, value in config.kwargs.items() if key != "batch_id"}
        checks.append(
            {
                "expectation": config.type,
                "column": kwargs.pop("column", None),
                "kwargs": kwargs,
                "success": bool(result.success),
                "observed_value": result.result.get("observed_value"),
                "unexpected_count": result.result.get("unexpected_count"),
                "unexpected_percent": result.result.get("unexpected_percent"),
            }
        )

    report = _jsonable(
        {
            "report_name": report_name,
            "generated_at": now_utc().isoformat(timespec="seconds"),
            "gx_version": gx.__version__,
            "row_count": len(df),
            "success": bool(validation.success),
            "statistics": validation.statistics,
            "failed_checks": [
                f"{check['expectation']}({check['column']})" if check["column"] else check["expectation"]
                for check in checks
                if not check["success"]
            ],
            "checks": checks,
        }
    )

    write_json(settings.paths.quality_dir / f"{report_name}_quality_report.json", report)
    write_json(settings.paths.gx_dir / f"{report_name}_suite.json", _jsonable(suite.to_json_dict()))
    write_json(settings.paths.gx_dir / f"{report_name}_validation.json", _jsonable(validation.to_json_dict()))

    stats = validation.statistics
    print(
        f"[quality] {report_name}: success={report['success']} "
        f"({stats['successful_expectations']}/{stats['evaluated_expectations']} expectations passed)"
    )
    return report


def build_freshness_report(df: pd.DataFrame, settings: Settings, report_path) -> dict[str, Any]:
    """Summarize publication age against the freshness SLA and write it to `report_path`.

    Rows with a missing/invalid `age_days` cannot prove they are fresh, so they count as stale.
    """
    threshold = settings.freshness_threshold_days
    total_rows = len(df)
    ages = pd.to_numeric(df["age_days"], errors="coerce") if "age_days" in df else pd.Series(float("nan"), index=df.index)
    published = pd.to_datetime(df["published"], errors="coerce") if "published" in df else pd.Series(dtype="datetime64[ns]")

    stale_rows = int((ages.isna() | (ages > threshold)).sum())
    stale_ratio = stale_rows / total_rows if total_rows else 1.0
    valid_ages = ages.dropna()
    valid_published = published.dropna()

    payload = {
        "generated_at": now_utc().isoformat(timespec="seconds"),
        "threshold_days": threshold,
        "max_stale_ratio": MAX_STALE_RATIO,
        "latest_published": valid_published.max().date().isoformat() if not valid_published.empty else None,
        "oldest_published": valid_published.min().date().isoformat() if not valid_published.empty else None,
        "min_age_days": int(valid_ages.min()) if not valid_ages.empty else None,
        "median_age_days": float(valid_ages.median()) if not valid_ages.empty else None,
        "max_age_days": int(valid_ages.max()) if not valid_ages.empty else None,
        "stale_rows": stale_rows,
        "total_rows": total_rows,
        "stale_ratio": round(stale_ratio, 4),
        "is_fresh": total_rows > 0 and stale_ratio <= MAX_STALE_RATIO,
    }
    write_json(report_path, payload)
    print(
        f"[freshness] is_fresh={payload['is_fresh']} "
        f"({stale_rows}/{total_rows} rows older than {threshold} days, max allowed {MAX_STALE_RATIO:.0%})"
    )
    return payload
