from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, asdict
from pathlib import Path

import requests

from core.config import Settings

CROSSREF_API_URL = "https://api.crossref.org/works"


@dataclass(frozen=True)
class PaperRecord:
    paper_id: str
    title: str
    summary: str
    authors: list[str]
    categories: list[str]
    primary_category: str
    published: str
    updated: str
    abs_url: str
    pdf_url: str
    comment: str


def _strip_jats_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()


def _format_date(date_parts: dict | None) -> str:
    if not date_parts:
        return ""
    parts = date_parts.get("date-parts", [[]])[0]
    if not parts:
        return ""
    year = parts[0]
    month = parts[1] if len(parts) > 1 else 1
    day = parts[2] if len(parts) > 2 else 1
    return f"{year:04d}-{month:02d}-{day:02d}"


def parse_crossref_payload(payload: dict) -> list[PaperRecord]:
    """Parse Crossref payload thanh list PaperRecord."""
    records: list[PaperRecord] = []
    items = payload.get("message", {}).get("items", [])
    for item in items:
        doi = item.get("DOI")
        titles = item.get("title") or []
        if not doi or not titles:
            continue

        title = titles[0].strip()
        summary = _strip_jats_tags(item.get("abstract", ""))
        authors = [
            " ".join(part for part in (author.get("given"), author.get("family")) if part)
            for author in item.get("author", [])
        ]
        authors = [a for a in authors if a]
        categories = list(item.get("subject", []))
        primary_category = categories[0] if categories else "Uncategorized"
        published = _format_date(item.get("published") or item.get("published-print") or item.get("published-online"))
        updated = _format_date(item.get("created")) or published
        url = item.get("URL", f"https://doi.org/{doi}")

        records.append(
            PaperRecord(
                paper_id=doi,
                title=title,
                summary=summary,
                authors=authors,
                categories=categories,
                primary_category=primary_category,
                published=published,
                updated=updated,
                abs_url=url,
                pdf_url=url,
                comment=f"Crossref record {doi}",
            )
        )
    return records


def _save_records(records: list[PaperRecord], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([asdict(r) for r in records], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """Goi Crossref API (voi retry va fallback local) roi parse thanh records."""
    params = {
        "query": settings.source_query,
        "filter": settings.source_filter,
        "rows": settings.max_results,
    }

    max_attempts = 3
    payload: dict | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.get(CROSSREF_API_URL, params=params, timeout=30)
            if response.status_code in (429, 503):
                time.sleep(2**attempt)
                continue
            response.raise_for_status()
            payload = response.json()
            break
        except requests.RequestException:
            if attempt == max_attempts:
                payload = None
            else:
                time.sleep(2**attempt)

    if payload is None:
        return load_raw_records(settings.paths.raw_records_json)

    settings.paths.raw_api_response.parent.mkdir(parents=True, exist_ok=True)
    settings.paths.raw_api_response.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    records = parse_crossref_payload(payload)
    _save_records(records, settings.paths.raw_records_json)
    return records


def load_raw_records(path: Path) -> list[PaperRecord]:
    """Doc JSON snapshot va map thanh `PaperRecord`."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return [PaperRecord(**item) for item in data]
