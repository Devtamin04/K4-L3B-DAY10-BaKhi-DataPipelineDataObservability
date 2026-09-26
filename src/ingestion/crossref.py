from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from pathlib import Path
import time
from typing import Any

import requests

from core.config import Settings
from core.utils import clean_abstract, normalize_whitespace, read_json, strip_markup, write_json

CROSSREF_WORKS_URL = "https://api.crossref.org/works"
CROSSREF_SELECT_FIELDS = (
    "DOI,title,abstract,author,subject,published,created,deposited,URL,link,"
    "container-title,group-title,institution,publisher,type"
)
WORK_TYPE_LABELS = {
    "journal-article": "Journal Article",
    "posted-content": "Preprint",
    "proceedings-article": "Conference Paper",
    "book-chapter": "Book Chapter",
    "report": "Report",
    "dissertation": "Dissertation",
}
# Crossref venues used for preprints still under review; not a meaningful category.
IGNORED_GROUP_TITLES = {"in review"}
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 3
REQUEST_TIMEOUT_SECONDS = 30


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


def _clean_text(value: Any) -> str:
    """Crossref wraps titles in a list; take the first entry and strip markup."""
    if isinstance(value, list):
        value = value[0] if value else ""
    return strip_markup(value)


def _format_date(date_obj: Any) -> str:
    """Convert Crossref `{"date-parts": [[YYYY, MM, DD]]}` to `YYYY-MM-DD` (missing parts default to 1)."""
    if not isinstance(date_obj, dict):
        return ""
    parts = (date_obj.get("date-parts") or [[]])[0] or []
    if not parts or parts[0] is None:
        date_time = date_obj.get("date-time")
        return date_time[:10] if isinstance(date_time, str) else ""
    year, month, day = (list(parts) + [1, 1])[:3]
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"


def _first_date(item: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        formatted = _format_date(item.get(key))
        if formatted:
            return formatted
    return ""


def _parse_authors(raw_authors: Any) -> list[str]:
    authors: list[str] = []
    for author in raw_authors or []:
        if not isinstance(author, dict):
            continue
        name = normalize_whitespace(f"{author.get('given', '')} {author.get('family', '')}") or _clean_text(
            author.get("name", "")
        )
        if name:
            authors.append(name)
    return authors


def _pdf_url(item: dict[str, Any], fallback: str) -> str:
    for link in item.get("link") or []:
        if isinstance(link, dict) and link.get("content-type") == "application/pdf" and link.get("URL"):
            return link["URL"]
    return fallback


def _venue(item: dict[str, Any]) -> str:
    candidates = [_clean_text(item.get("container-title")), _clean_text(item.get("group-title"))]
    candidates += [_clean_text(inst.get("name")) for inst in item.get("institution") or [] if isinstance(inst, dict)]
    candidates.append(_clean_text(item.get("publisher")))
    return next((name for name in candidates if name and name.lower() not in IGNORED_GROUP_TITLES), "")


def _derive_categories(item: dict[str, Any]) -> list[str]:
    """Use Crossref `subject` when present; most live records omit it, so fall back to venue + work type."""
    subjects = [category for category in (_clean_text(subject) for subject in item.get("subject") or []) if category]
    if subjects:
        return subjects
    work_type = str(item.get("type") or "")
    type_label = WORK_TYPE_LABELS.get(work_type) or work_type.replace("-", " ").title()
    return [category for category in dict.fromkeys((_venue(item), type_label)) if category]


def _parse_item(item: dict[str, Any]) -> PaperRecord | None:
    doi = normalize_whitespace(str(item.get("DOI") or ""))
    title = _clean_text(item.get("title"))
    summary = clean_abstract(item.get("abstract"))
    published = _first_date(item, ("published", "published-print", "published-online", "issued", "created"))
    if not doi or not title or not summary or not published:
        return None

    categories = _derive_categories(item)
    abs_url = item.get("URL") or f"https://doi.org/{doi}"
    return PaperRecord(
        paper_id=doi,
        title=title,
        summary=summary,
        authors=_parse_authors(item.get("author")),
        categories=categories,
        primary_category=categories[0] if categories else "",
        published=published,
        updated=_first_date(item, ("deposited",)) or published,
        abs_url=abs_url,
        pdf_url=_pdf_url(item, abs_url),
        comment=f"Crossref record {doi}",
    )


def parse_crossref_payload(payload: dict) -> list[PaperRecord]:
    items = (payload.get("message") or {}).get("items") or []
    records: list[PaperRecord] = []
    seen_ids: set[str] = set()
    for item in items:
        record = _parse_item(item) if isinstance(item, dict) else None
        if record is None or record.paper_id.lower() in seen_ids:
            continue
        seen_ids.add(record.paper_id.lower())
        records.append(record)
    return records


def _request_crossref(settings: Settings) -> dict[str, Any]:
    params = {
        "query": settings.source_query,
        "filter": settings.source_filter,
        "rows": settings.max_results,
        "select": CROSSREF_SELECT_FIELDS,
    }
    headers = {"User-Agent": "day10-data-observability-lab/0.1 (student lab)"}
    for attempt in range(1, MAX_ATTEMPTS + 1):
        response = requests.get(CROSSREF_WORKS_URL, params=params, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
        if response.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_ATTEMPTS:
            retry_after = response.headers.get("Retry-After", "")
            wait_seconds = int(retry_after) if retry_after.isdigit() else 2**attempt
            print(f"[crossref] HTTP {response.status_code}, retry {attempt}/{MAX_ATTEMPTS - 1} after {wait_seconds}s")
            time.sleep(wait_seconds)
            continue
        response.raise_for_status()
        return response.json()
    raise RuntimeError("Crossref request failed after retries.")  # unreachable: last attempt raises or returns


def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """Load Crossref records, calling the live API only when REFRESH_SOURCE=1 or no snapshot exists.

    The raw response is only overwritten after a successful fetch that returned items, so the
    local snapshot stays intact as the lineage anchor / offline fallback.
    """
    raw_path = settings.paths.raw_api_response
    payload: dict[str, Any] | None = None

    if settings.refresh_source or not raw_path.exists():
        try:
            fetched = _request_crossref(settings)
            if not (fetched.get("message") or {}).get("items"):
                raise ValueError("Crossref returned no items.")
            write_json(raw_path, fetched)
            payload = fetched
            print(f"[crossref] Fetched live data from {CROSSREF_WORKS_URL}")
        except (requests.RequestException, RuntimeError, ValueError) as exc:
            if not raw_path.exists():
                raise RuntimeError(f"Crossref API unavailable and no snapshot at {raw_path}.") from exc
            print(f"[crossref] API unavailable ({exc}); falling back to local snapshot.")

    if payload is None:
        payload = read_json(raw_path)
        print(f"[crossref] Using local snapshot {raw_path.name}")

    records = parse_crossref_payload(payload)
    write_json(settings.paths.raw_records_json, [asdict(record) for record in records])
    return records


def load_raw_records(path: Path) -> list[PaperRecord]:
    field_names = {field.name for field in fields(PaperRecord)}
    return [PaperRecord(**{key: value for key, value in item.items() if key in field_names}) for item in read_json(path)]
