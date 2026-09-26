from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, is_dataclass
from datetime import UTC, date, datetime
from typing import Any

import pandas as pd

from core.utils import clean_abstract, compact_join, normalize_whitespace, strip_markup
from ingestion.crossref import PaperRecord

CLEAN_COLUMNS = [
    "paper_id",
    "title",
    "summary",
    "authors",
    "categories",
    "primary_category",
    "published",
    "updated",
    "age_days",
    "abs_url",
    "pdf_url",
    "comment",
    "authors_joined",
    "categories_joined",
    "summary_chars",
    "text_for_embedding",
]


def _clean_list(values: Any) -> list[str]:
    """Strip markup from each entry, drop blanks and case-insensitive duplicates, keep order."""
    if isinstance(values, str):
        values = [values]
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values if isinstance(values, Iterable) else []:
        text = strip_markup(value)
        if text and text.lower() not in seen:
            seen.add(text.lower())
            cleaned.append(text)
    return cleaned


def _parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value).strip()[:10])
    except ValueError:
        return None


def build_text_for_embedding(row: Mapping[str, Any]) -> str:
    """5-part document used for embedding: title, authors, categories, published, summary."""
    return "\n".join(
        [
            f"Title: {row['title']}",
            f"Authors: {row['authors_joined']}",
            f"Categories: {row['categories_joined']}",
            f"Published: {row['published']}",
            f"Summary: {row['summary']}",
        ]
    )


def build_clean_dataframe(records: list[PaperRecord], run_date: datetime) -> pd.DataFrame:
    """Normalize raw records into an embed-ready dataframe.

    Rows missing paper_id, title, summary or a valid published date are dropped, duplicates by
    paper_id (case-insensitive) keep the most recently updated version, and the result is sorted
    newest first. `published`/`updated` stay ISO `YYYY-MM-DD` strings so they can be stored as
    Chroma metadata and compared directly against test-set answers.
    """
    run_day = run_date.astimezone(UTC).date() if run_date.tzinfo else run_date.date()

    rows: list[dict[str, Any]] = []
    for record in records:
        raw = asdict(record) if is_dataclass(record) else dict(record)
        paper_id = normalize_whitespace(str(raw.get("paper_id") or ""))
        title = strip_markup(raw.get("title"))
        summary = clean_abstract(raw.get("summary"))
        published = _parse_date(raw.get("published"))
        if not paper_id or not title or not summary or published is None:
            continue

        authors = _clean_list(raw.get("authors"))
        categories = _clean_list(raw.get("categories"))
        row = {
            "paper_id": paper_id,
            "title": title,
            "summary": summary,
            "authors": authors,
            "categories": categories,
            "primary_category": strip_markup(raw.get("primary_category")) or (categories[0] if categories else ""),
            "published": published.isoformat(),
            "updated": (_parse_date(raw.get("updated")) or published).isoformat(),
            "age_days": (run_day - published).days,
            "abs_url": normalize_whitespace(str(raw.get("abs_url") or "")),
            "pdf_url": normalize_whitespace(str(raw.get("pdf_url") or "")),
            "comment": strip_markup(raw.get("comment")),
            "authors_joined": compact_join(authors),
            "categories_joined": compact_join(categories),
            "summary_chars": len(summary),
        }
        row["text_for_embedding"] = build_text_for_embedding(row)
        rows.append(row)

    df = pd.DataFrame(rows, columns=CLEAN_COLUMNS)
    if df.empty:
        return df

    df = (
        df.assign(_key=df["paper_id"].str.lower())
        .sort_values("updated", ascending=False, kind="stable")
        .drop_duplicates("_key")
        .drop(columns="_key")
    )
    return df.sort_values(["published", "paper_id"], ascending=[False, True]).reset_index(drop=True)
