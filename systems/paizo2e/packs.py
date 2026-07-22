"""Normalize selected fields from PF2e and SF2e Foundry pack documents."""

from __future__ import annotations

import re
from collections.abc import Mapping

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
_UUID_OR_CHECK = re.compile(r"@(UUID|Check)\[[^\]]*\](?:\{([^}]*)\})?")
_FOUNDRY_TOKEN = re.compile(r"@[A-Za-z]+\[[^\]]*\](?:\{[^}]*\})?")
_HTML_TAG = re.compile(r"<[^>]+>")
_BLANK_LINES = re.compile(r"\n[ \t]*\n(?:[ \t]*\n)+")
_SLUG_CHARS = re.compile(r"[^a-z0-9]+")


def pack_category(path: str) -> str | None:
    """Return the supported category for a Foundry pack file path."""
    normalized = path.replace("\\", "/").lower()
    if any(normalized.endswith(suffix) for suffix in _MEDIA_SUFFIXES):
        return None

    directories = normalized.split("/")[:-1]
    for directory in reversed(directories):
        if directory in _CATEGORIES:
            return directory
        if directory in _CREATURE_PACKS or directory.endswith("-bestiary"):
            return "creatures"
    return None


def strip_foundry_markup(value: str) -> str:
    """Convert Foundry inline references and HTML into compact plain text."""
    text = _UUID_OR_CHECK.sub(lambda match: match.group(2) or "", value)
    text = _FOUNDRY_TOKEN.sub("", text)
    text = re.sub(r"<(?:br\s*/?|/p|/div|/li|/h[1-6])\s*>", "\n\n", text, flags=re.IGNORECASE)
    text = _HTML_TAG.sub("", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    return _BLANK_LINES.sub("\n\n", text).strip()


def _slugify(name: str) -> str:
    return _SLUG_CHARS.sub("-", name.lower()).strip("-")


def normalize_document(
    raw_text: str, source_path: str, category: str
) -> dict[str, object] | None:
    """Extract the stable, searchable fields from one Foundry YAML document."""
    try:
        document = yaml.safe_load(raw_text)
    except yaml.YAMLError:
        return None
    if not isinstance(document, Mapping):
        return None

    name = document.get("name")
    if not isinstance(name, str) or not name.strip():
        return None

    system = document.get("system")
    if not isinstance(system, Mapping):
        system = {}
    description = system.get("description")
    traits = system.get("traits")
    level = system.get("level")

    return {
        "name": name,
        "index": _slugify(name),
        "category": category,
        "type": document.get("type", ""),
        "description": strip_foundry_markup(description.get("value", ""))
        if isinstance(description, Mapping) and isinstance(description.get("value", ""), str)
        else "",
        "traits": traits.get("value", []) if isinstance(traits, Mapping) else [],
        "level": level.get("value") if isinstance(level, Mapping) else None,
        "source_path": source_path,
    }
