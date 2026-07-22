"""Foundry VTT source retrieval and generated-dataset helpers."""

from __future__ import annotations

from dataclasses import dataclass
import base64
import json
import os
from pathlib import Path
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


GITHUB_API = "https://api.github.com"
USER_AGENT = "ttrpg-skill-foundry-source/1.0"
HTTP_TIMEOUT_SECONDS = 30


@dataclass(frozen=True)
class SourceSpec:
    """The Foundry repository location used to build one system's dataset."""

    system: str
    pack_root: str
    repo: str = "foundryvtt/pf2e"
    ref: str = "v14-dev"


def dataset_metadata(spec: SourceSpec, sha: str, counts: dict[str, int]) -> dict:
    """Build stable provenance metadata for a generated Foundry dataset."""
    return {
        "schema_version": 1,
        "system": spec.system,
        "source": {
            "repo": spec.repo,
            "ref": spec.ref,
            "sha": sha,
            "pack_root": spec.pack_root,
        },
        "record_counts": counts,
    }


def write_dataset(path: str | Path, dataset: dict) -> None:
    """Atomically replace *path* with a compact JSON dataset."""
    destination = Path(path)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(dataset, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def needs_rebuild(path: str | Path, sha: str) -> bool:
    """Return whether *path* is absent, unreadable, or from another source SHA."""
    try:
        with Path(path).open(encoding="utf-8") as handle:
            dataset = json.load(handle)
        return dataset["_meta"]["source"]["sha"] != sha
    except (OSError, ValueError, KeyError, TypeError):
        return True


def _github_json(path: str) -> dict:
    """Request and decode one GitHub API JSON response."""
    request = Request(
        f"{GITHUB_API}{path}",
        headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"},
    )
    try:
        with urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            return json.load(response)
    except (HTTPError, URLError, OSError, ValueError) as exc:
        raise RuntimeError(f"GitHub API request failed for {path}: {exc}") from exc


def resolve_ref(spec: SourceSpec) -> str:
    """Resolve the configured repository ref to an immutable commit SHA."""
    ref = quote(spec.ref, safe="")
    payload = _github_json(f"/repos/{spec.repo}/commits/{ref}")
    try:
        return payload["sha"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError(f"GitHub commits response lacked a SHA for {spec.ref}") from exc


def tree_at_sha(spec: SourceSpec, sha: str) -> list[dict]:
    """Return the complete recursive repository tree for *sha*."""
    encoded_sha = quote(sha, safe="")
    payload = _github_json(
        f"/repos/{spec.repo}/git/trees/{encoded_sha}?recursive=1"
    )
    if not isinstance(payload, dict):
        raise RuntimeError(f"GitHub tree response was invalid for {sha}")
    if payload.get("truncated") is True:
        raise RuntimeError(f"GitHub tree response was truncated for {sha}")
    tree = payload.get("tree")
    if not isinstance(tree, list):
        raise RuntimeError(f"GitHub tree response lacked a tree list for {sha}")
    return tree


def blob_text(spec: SourceSpec, sha: str) -> str:
    """Fetch and decode one UTF-8 Git blob by its immutable SHA."""
    payload = _github_json(f"/repos/{spec.repo}/git/blobs/{quote(sha, safe='')}")
    try:
        if payload["encoding"] != "base64":
            raise RuntimeError(f"GitHub blob response used unsupported encoding for {sha}")
        content = payload["content"]
        if not isinstance(content, str):
            raise TypeError("content was not a string")
        return base64.b64decode("".join(content.split()), validate=True).decode("utf-8")
    except (KeyError, TypeError, UnicodeDecodeError, ValueError) as exc:
        raise RuntimeError(f"GitHub blob response was invalid for {sha}: {exc}") from exc


def _candidate_blobs(tree: list[dict], pack_root: str) -> list[tuple[str, str]]:
    """Return supported document blobs directly below the configured pack root."""
    root = pack_root.strip("/") + "/"
    candidates: list[tuple[str, str]] = []
    for entry in tree:
        if not isinstance(entry, dict) or entry.get("type") != "blob":
            continue
        path = entry.get("path")
        blob_sha = entry.get("sha")
        if not isinstance(path, str) or not isinstance(blob_sha, str):
            continue
        if not path.startswith(root) or not path.lower().endswith((".yaml", ".yml", ".json")):
            continue
        candidates.append((path, blob_sha))
    return candidates


def build_dataset(spec: SourceSpec, output_path: str | Path, force: bool = False) -> bool:
    """Build a normalized dataset, replacing its output only after full success."""
    sha = resolve_ref(spec)
    if not force and not needs_rebuild(output_path, sha):
        print(f"{spec.system} dataset is up to date.")
        return False

    # Import lazily so the source and normalization modules remain independently usable.
    from systems.paizo2e.packs import normalize_document, pack_category

    records: dict[str, list[dict[str, object]]] = {}
    for path, blob_sha in _candidate_blobs(tree_at_sha(spec, sha), spec.pack_root):
        category = pack_category(path)
        if category is None:
            continue
        record = normalize_document(blob_text(spec, blob_sha), path, category)
        if record is not None:
            records.setdefault(category, []).append(record)

    ordered_records = {category: records[category] for category in sorted(records)}
    counts = {category: len(records) for category, records in ordered_records.items()}
    dataset = {"_meta": dataset_metadata(spec, sha, counts), **ordered_records}
    write_dataset(output_path, dataset)
    return True
