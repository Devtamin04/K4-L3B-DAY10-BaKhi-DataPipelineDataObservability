from __future__ import annotations

from datetime import datetime

import pandas as pd

from ingestion.crossref import PaperRecord


def build_clean_dataframe(records: list[PaperRecord], run_date: datetime) -> pd.DataFrame:
    """Clean raw records thanh dataframe san sang de embed."""
    rows = []
    for r in records:
        title = (r.title or "").strip()
        summary = (r.summary or "").strip()
        if not r.paper_id or not title or not summary:
            continue
        rows.append(
            {
                "paper_id": r.paper_id.strip(),
                "title": title,
                "summary": summary,
                "authors": [a.strip() for a in r.authors if a.strip()],
                "categories": [c.strip() for c in r.categories if c.strip()],
                "primary_category": (r.primary_category or "Uncategorized").strip(),
                "published": r.published,
                "updated": r.updated,
                "abs_url": r.abs_url,
                "pdf_url": r.pdf_url,
                "comment": r.comment,
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df = df.drop_duplicates(subset="paper_id", keep="first").reset_index(drop=True)

    published_dt = pd.to_datetime(df["published"], errors="coerce", utc=True)
    df["age_days"] = (pd.Timestamp(run_date) - published_dt).dt.days

    df["authors_joined"] = df["authors"].apply(lambda a: ", ".join(a))
    df["categories_joined"] = df["categories"].apply(lambda c: ", ".join(c))
    df["summary_chars"] = df["summary"].str.len()
    df["text_for_embedding"] = (
        "Title: " + df["title"]
        + "\nAuthors: " + df["authors_joined"]
        + "\nPublished: " + df["published"]
        + "\nCategories: " + df["categories_joined"]
        + "\nSummary: " + df["summary"]
    )

    df = df.sort_values("published", ascending=False).reset_index(drop=True)
    return df
