from __future__ import annotations

import re
from typing import Any

import pandas as pd

from core.utils import first_sentence, normalize_whitespace, write_json

# 10 questions over the 4 required types (summary 3, authors 3, date 2, categories 2).
QUESTION_PLAN = (
    "summary",
    "authors",
    "date",
    "categories",
    "summary",
    "authors",
    "date",
    "categories",
    "summary",
    "authors",
)
MIN_DOCUMENTS = len(QUESTION_PLAN)

# Phrases must match the intent detection in retrieval/qa.py (`who authored`, `when was`, `what categories`),
# and the title goes in single quotes so qa.py can do an exact title lookup.
QUESTION_TEMPLATES = {
    "summary": "What is the paper '{title}' about?",
    "authors": "Who authored the paper '{title}'?",
    "date": "When was the paper '{title}' published?",
    "categories": "What categories does the paper '{title}' belong to?",
}
# Most constrained types pick their papers first so they are not starved by the others.
PICK_ORDER = ("categories", "authors", "date", "summary")

ENGLISH_STOPWORDS = frozenset(
    "the of and to in a is for with that this we are on by as an be from it which our these using".split()
)
MIN_ENGLISH_STOPWORD_RATIO = 0.08
MIN_LATIN_LETTER_RATIO = 0.9


def _text(value: Any) -> str:
    return "" if value is None or (isinstance(value, float) and pd.isna(value)) else normalize_whitespace(str(value))


def _is_english(text: str) -> bool:
    """Cheap language filter: English prose has a high share of common stopwords."""
    tokens = re.findall(r"[^\W\d_]+", text.lower())
    return bool(tokens) and sum(token in ENGLISH_STOPWORDS for token in tokens) / len(tokens) >= MIN_ENGLISH_STOPWORD_RATIO


def _is_latin(text: str) -> bool:
    """Titles in other scripts (e.g. Cyrillic) embed poorly with the English MiniLM model."""
    letters = [char for char in text if char.isalpha()]
    return bool(letters) and sum(char.isascii() for char in letters) / len(letters) >= MIN_LATIN_LETTER_RATIO


def _ground_truth(row: pd.Series, question_type: str) -> str:
    if question_type == "summary":
        return first_sentence(_text(row["summary"]))
    if question_type == "authors":
        return _text(row["authors_joined"])
    if question_type == "date":
        return _text(row["published"])[:10]
    return _text(row["categories_joined"])


def _eligible(df: pd.DataFrame, question_type: str) -> pd.DataFrame:
    """English papers whose title can be quoted and whose answer field is present (and unambiguous for categories)."""
    mask = df["title"].map(lambda title: "'" not in title and _is_latin(title)) & df["summary"].map(_is_english)
    mask &= df.apply(lambda row: bool(_ground_truth(row, question_type)), axis=1)
    if question_type == "categories":
        mask &= ~df["categories_joined"].duplicated(keep=False)
    return df[mask]


def build_test_set(df: pd.DataFrame, output_path) -> list[dict[str, Any]]:
    """Build a deterministic 10-question evaluation set from the clean dataframe and write it as JSON.

    Each question targets a different paper when possible (papers ordered by `paper_id`, so the
    selection does not depend on the run date). A paper is reused only when a type runs out of
    eligible unused papers.
    """
    if len(df) < MIN_DOCUMENTS:
        raise ValueError(f"Need at least {MIN_DOCUMENTS} documents to build the test set, got {len(df)}.")

    papers = df.sort_values("paper_id").reset_index(drop=True)
    used_ids: set[str] = set()
    picks: dict[int, pd.Series] = {}
    for question_type in PICK_ORDER:
        slots = [index for index, planned in enumerate(QUESTION_PLAN) if planned == question_type]
        candidates = _eligible(papers, question_type)
        if candidates.empty:
            raise ValueError(f"No eligible papers for '{question_type}' questions.")
        ordered = pd.concat([candidates[~candidates["paper_id"].isin(used_ids)], candidates[candidates["paper_id"].isin(used_ids)]])
        for slot, (_, row) in zip(slots, ordered.head(len(slots)).iterrows(), strict=False):
            picks[slot] = row
            used_ids.add(row["paper_id"])
        if len(ordered) < len(slots):
            raise ValueError(f"Only {len(ordered)} eligible papers for {len(slots)} '{question_type}' questions.")

    test_set = [
        {
            "id": f"q{slot + 1:02d}",
            "question_type": QUESTION_PLAN[slot],
            "question": QUESTION_TEMPLATES[QUESTION_PLAN[slot]].format(title=picks[slot]["title"]),
            "ground_truth": _ground_truth(picks[slot], QUESTION_PLAN[slot]),
            "ground_truth_doc_ids": [picks[slot]["paper_id"]],
        }
        for slot in range(len(QUESTION_PLAN))
    ]
    write_json(output_path, test_set)
    return test_set
