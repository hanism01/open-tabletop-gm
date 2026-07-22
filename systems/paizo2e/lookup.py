"""Shared lookup and formatting helpers for Foundry-source Paizo datasets."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any


_NORMALIZE = re.compile(r"[^a-z0-9]+")


def load_dataset(path: str | Path) -> dict[str, Any]:
    """Load one generated system dataset from *path*."""
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def find_records(
    dataset: dict[str, Any], category: str, query: str, limit: int | None = 1
) -> list[dict[str, Any]]:
    """Find records in a dataset, preferring exact normalized-name matches."""
    normalized_query = _normalize_name(query)
    if not normalized_query:
        return []

    category_key = category.casefold()
    if category_key == "any":
        categories = [name for name in dataset if name != "_meta"]
    elif category_key not in dataset and f"{category_key}s" in dataset:
        categories = [f"{category_key}s"]
    else:
        categories = [category_key]
    records = [
        record
        for name in categories
        for record in dataset.get(name, [])
        if isinstance(record, dict)
    ]
    exact = [
        record for record in records if _normalize_name(str(record.get("name", ""))) == normalized_query
    ]
    substring = [
        record
        for record in records
        if record not in exact
        and normalized_query in _normalize_name(str(record.get("name", "")))
    ]
    found = sorted(exact, key=_record_sort_key) + sorted(substring, key=_record_sort_key)
    return found if limit is None else found[:limit]


def format_record(record: dict[str, Any], source_sha: str) -> str:
    """Format a normalized Foundry record and its source provenance for play."""
    traits = record.get("traits", [])
    traits_text = ", ".join(str(trait) for trait in traits) if traits else "—"
    level = record.get("level")
    level_text = "—" if level is None or level == "" else str(level)
    lines = [
        f"## {record.get('name', '?')}",
        f"Category: {record.get('category', '—')}",
        f"Traits: {traits_text}",
        f"Level: {level_text}",
    ]
    description = record.get("description")
    if description:
        lines.extend(["", str(description)])
    lines.extend(
        [
            "",
            f"Source path: {record.get('source_path', '—')}",
            f"Source SHA: {source_sha[:12]}",
        ]
    )
    return "\n".join(lines)


def _normalize_name(value: str) -> str:
    return _NORMALIZE.sub("-", value.casefold()).strip("-")


def _record_sort_key(record: dict[str, Any]) -> tuple[str, str]:
    return (str(record.get("name", "")).casefold(), str(record.get("source_path", "")))
