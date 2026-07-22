"""Normalize selected fields from PF2e and SF2e Foundry pack documents."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from html.parser import HTMLParser
from math import isfinite

try:
    import yaml
except ImportError as exc:  # pragma: no cover - depends on the runtime environment
    raise ImportError(
        "PyYAML is required to normalize Foundry pack documents. "
        "Install it with: pip3 install pyyaml"
    ) from exc


_CATEGORIES = frozenset(
    {
        "actions",
        "ancestries",
        "backgrounds",
        "classes",
        "conditions",
        "creatures",
        "equipment",
        "feats",
        "hazards",
        "items",
        "rules",
        "spells",
        "vehicles",
    }
)
_CREATURE_PACKS = frozenset({"alien-core"})
_MEDIA_SUFFIXES = frozenset({".webp", ".png", ".jpg", ".mp3", ".ogg"})
_BLANK_LINES = re.compile(r"\n[ \t]*\n(?:[ \t]*\n)+")
_SLUG_CHARS = re.compile(r"[^a-z0-9]+")
_DOCUMENT_SUFFIXES = frozenset({".yaml", ".yml", ".json"})
_BLOCK_TAGS = frozenset({"p", "div", "li", "br", "h1", "h2", "h3", "h4", "h5", "h6"})


class _FoundryHTMLTextExtractor(HTMLParser):
    """Extract text while retaining paragraph boundaries from Foundry HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "br":
            self.parts.append("\n\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in _BLOCK_TAGS:
            self.parts.append("\n\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        return "".join(self.parts)


def pack_category(path: str) -> str | None:
    """Return the supported category for a Foundry pack file path."""
    normalized = path.replace("\\", "/").lower()
    parts = normalized.split("/")
    if (
        len(parts) < 4
        or any(part in {"", ".", ".."} for part in parts)
        or parts[0] != "packs"
        or parts[1] not in {"pf2e", "sf2e"}
    ):
        return None
    filename = parts[-1]
    if any(normalized.endswith(suffix) for suffix in _MEDIA_SUFFIXES):
        return None
    if not any(filename.endswith(suffix) for suffix in _DOCUMENT_SUFFIXES):
        return None

    pack_name = parts[2]
    if pack_name in _CATEGORIES:
        return pack_name
    if pack_name in _CREATURE_PACKS or pack_name.endswith("-bestiary"):
        return "creatures"
    return None


def strip_foundry_markup(value: str) -> str:
    """Convert Foundry inline references and HTML into compact plain text."""
    text = _strip_foundry_tokens(value)
    extractor = _FoundryHTMLTextExtractor()
    extractor.feed(text)
    extractor.close()
    text = extractor.text()
    text = "\n".join(line.strip() for line in text.splitlines())
    return _BLANK_LINES.sub("\n\n", text).strip()


def _strip_foundry_tokens(value: str) -> str:
    """Remove balanced ``@Token[...]`` references, preserving UUID/check labels."""
    output: list[str] = []
    index = 0
    while index < len(value):
        if value[index] != "@":
            output.append(value[index])
            index += 1
            continue

        token_end = index + 1
        while token_end < len(value) and value[token_end].isalpha():
            token_end += 1
        if token_end == index + 1 or token_end >= len(value) or value[token_end] != "[":
            output.append(value[index])
            index += 1
            continue

        content_end = _balanced_end(value, token_end, "[", "]")
        if content_end is None:
            output.append(value[index])
            index += 1
            continue
        token_name = value[index + 1 : token_end]
        label = ""
        label_start = content_end
        while label_start < len(value) and value[label_start].isspace():
            label_start += 1
        if label_start < len(value) and value[label_start] == "{":
            label_end = _balanced_end(value, label_start, "{", "}")
            if label_end is not None:
                label = value[label_start + 1 : label_end - 1]
                index = label_end
            else:
                index = content_end
        else:
            index = content_end
        if token_name in {"UUID", "Check"}:
            output.append(label)
    return "".join(output)


def _balanced_end(value: str, start: int, opening: str, closing: str) -> int | None:
    """Return the index after a balanced delimiter sequence beginning at *start*."""
    depth = 0
    for index in range(start, len(value)):
        if value[index] == opening:
            depth += 1
        elif value[index] == closing:
            depth -= 1
            if depth == 0:
                return index + 1
    return None


def _slugify(name: str) -> str:
    return _SLUG_CHARS.sub("-", name.lower()).strip("-")


def normalize_document(
    raw_text: str, source_path: str, category: str
) -> dict[str, object] | None:
    """Extract searchable fields, raising ValueError for malformed documents."""
    try:
        document = (
            json.loads(raw_text)
            if source_path.lower().endswith(".json")
            else yaml.safe_load(raw_text)
        )
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ValueError("invalid YAML or JSON") from exc
    if not isinstance(document, Mapping):
        raise ValueError("document must be a mapping")

    name = document.get("name")
    if not isinstance(name, str) or not name.strip():
        return None

    system = document.get("system")
    if not isinstance(system, Mapping):
        system = {}
    description = system.get("description")
    traits = system.get("traits")
    level = system.get("level")

    document_type = document.get("type", "")
    trait_values = traits.get("value", []) if isinstance(traits, Mapping) else []
    level_value = level.get("value") if isinstance(level, Mapping) else None
    if not isinstance(document_type, str):
        document_type = ""
    if not isinstance(trait_values, list) or not all(
        isinstance(trait, str) for trait in trait_values
    ):
        trait_values = []
    if isinstance(level_value, bool) or not isinstance(level_value, (int, float, str)):
        level_value = None
    elif isinstance(level_value, float) and not isfinite(level_value):
        level_value = None

    return {
        "name": name,
        "index": _slugify(name),
        "category": category,
        "type": document_type,
        "description": strip_foundry_markup(description.get("value", ""))
        if isinstance(description, Mapping) and isinstance(description.get("value", ""), str)
        else "",
        "traits": trait_values,
        "level": level_value,
        "source_path": source_path,
    }
