from __future__ import annotations

import random

import pandas as pd

from core.utils import now_utc, write_json

RANDOM_SEED = 42
DROP_LATEST_RATIO = 0.20
BLANK_SUMMARY_ROWS = 3
NOISE_ROWS = 3
TRUNCATE_TITLE_ROWS = 2
TRUNCATE_TITLE_LEN = 6
STALE_DATE_ROWS = 2
STALE_DATE_YEARS_BACK = 3
DUPLICATE_ROWS = 2
NOISE_CHARS = "@#$%^&*!?><~`"


def _rebuild_text_for_embedding(df: pd.DataFrame) -> pd.DataFrame:
    df["authors_joined"] = df["authors"].apply(lambda a: ", ".join(a) if isinstance(a, list) else str(a or ""))
    df["categories_joined"] = df["categories"].apply(lambda c: ", ".join(c) if isinstance(c, list) else str(c or ""))
    df["summary_chars"] = df["summary"].str.len()
    df["text_for_embedding"] = (
        "Title: " + df["title"].astype(str)
        + "\nAuthors: " + df["authors_joined"]
        + "\nPublished: " + df["published"].astype(str)
        + "\nCategories: " + df["categories_joined"]
        + "\nSummary: " + df["summary"].astype(str)
    )
    return df


def corrupt_clean_dataframe(df: pd.DataFrame, output_log_path) -> pd.DataFrame:
    """Simulate 6 data corruption scenarios on the clean dataframe and log every injected error."""
    rng = random.Random(RANDOM_SEED)
    corrupted = df.copy().reset_index(drop=True)
    log: dict[str, list] = {
        "drop_latest": [],
        "blank_summary": [],
        "inject_noise": [],
        "truncate_title": [],
        "stale_date": [],
        "duplicate_rows": [],
    }

    # 1. Drop latest records (~20% newest by published date).
    sorted_idx = corrupted.sort_values("published", ascending=False).index.tolist()
    n_drop = max(1, int(len(corrupted) * DROP_LATEST_RATIO))
    drop_idx = sorted_idx[:n_drop]
    log["drop_latest"] = corrupted.loc[drop_idx, "paper_id"].tolist()
    corrupted = corrupted.drop(index=drop_idx).reset_index(drop=True)

    remaining_idx = corrupted.index.tolist()
    rng.shuffle(remaining_idx)

    # 2. Blank summary on a few rows.
    blank_idx = remaining_idx[:BLANK_SUMMARY_ROWS]
    for idx in blank_idx:
        log["blank_summary"].append(corrupted.at[idx, "paper_id"])
        corrupted.at[idx, "summary"] = ""

    # 3. Inject noise characters into the summary.
    noise_idx = remaining_idx[BLANK_SUMMARY_ROWS : BLANK_SUMMARY_ROWS + NOISE_ROWS]
    for idx in noise_idx:
        noise = "".join(rng.choice(NOISE_CHARS) for _ in range(20))
        corrupted.at[idx, "summary"] = f"{noise} {corrupted.at[idx, 'summary']} {noise}"
        log["inject_noise"].append(corrupted.at[idx, "paper_id"])

    # 4. Truncate title below the GX min-length threshold.
    truncate_idx = remaining_idx[
        BLANK_SUMMARY_ROWS + NOISE_ROWS : BLANK_SUMMARY_ROWS + NOISE_ROWS + TRUNCATE_TITLE_ROWS
    ]
    for idx in truncate_idx:
        original_title = corrupted.at[idx, "title"]
        corrupted.at[idx, "title"] = original_title[:TRUNCATE_TITLE_LEN]
        log["truncate_title"].append(corrupted.at[idx, "paper_id"])

    # 5. Push the published date into the past to trip the Freshness SLA.
    stale_idx = remaining_idx[
        BLANK_SUMMARY_ROWS + NOISE_ROWS + TRUNCATE_TITLE_ROWS
        : BLANK_SUMMARY_ROWS + NOISE_ROWS + TRUNCATE_TITLE_ROWS + STALE_DATE_ROWS
    ]
    for idx in stale_idx:
        original_date = pd.to_datetime(corrupted.at[idx, "published"])
        stale_date = original_date.replace(year=original_date.year - STALE_DATE_YEARS_BACK)
        corrupted.at[idx, "published"] = stale_date.date().isoformat()
        log["stale_date"].append(corrupted.at[idx, "paper_id"])

    # 6. Duplicate a couple of untouched rows.
    used = BLANK_SUMMARY_ROWS + NOISE_ROWS + TRUNCATE_TITLE_ROWS + STALE_DATE_ROWS
    dup_idx = remaining_idx[used : used + DUPLICATE_ROWS]
    dup_rows = corrupted.loc[dup_idx]
    log["duplicate_rows"] = corrupted.loc[dup_idx, "paper_id"].tolist()
    corrupted = pd.concat([corrupted, dup_rows], ignore_index=True)

    published_dt = pd.to_datetime(corrupted["published"], errors="coerce", utc=True)
    run_date = now_utc()
    corrupted["age_days"] = (pd.Timestamp(run_date) - published_dt).dt.days
    corrupted = _rebuild_text_for_embedding(corrupted)

    report = {
        "generated_at": run_date.isoformat(timespec="seconds"),
        "original_row_count": len(df),
        "corrupted_row_count": len(corrupted),
        "scenarios": {
            "drop_latest": {"count": len(log["drop_latest"]), "paper_ids": log["drop_latest"]},
            "blank_summary": {"count": len(log["blank_summary"]), "paper_ids": log["blank_summary"]},
            "inject_noise": {"count": len(log["inject_noise"]), "paper_ids": log["inject_noise"]},
            "truncate_title": {"count": len(log["truncate_title"]), "paper_ids": log["truncate_title"]},
            "stale_date": {"count": len(log["stale_date"]), "paper_ids": log["stale_date"]},
            "duplicate_rows": {"count": len(log["duplicate_rows"]), "paper_ids": log["duplicate_rows"]},
        },
    }
    write_json(output_log_path, report)

    return corrupted
