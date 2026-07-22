"""Foundry VTT source retrieval and generated-dataset helpers."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
import json
import os
from pathlib import Path
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile


GITHUB_API = "https://api.github.com"
GITHUB_CODELOAD = "https://codeload.github.com"
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


def source_archive(spec: SourceSpec, sha: str) -> ZipFile:
    """Download the pinned source archive without writing it to the repository."""
    request = Request(
        f"{GITHUB_CODELOAD}/{spec.repo}/zip/{quote(sha, safe='')}",
        headers={"User-Agent": USER_AGENT},
    )
    try:
        with urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            return ZipFile(BytesIO(response.read()))
    except (HTTPError, URLError, OSError, BadZipFile) as exc:
        raise RuntimeError(f"GitHub source archive request failed for {sha}: {exc}") from exc


def _candidate_members(archive: ZipFile, pack_root: str) -> list[tuple[str, str]]:
    """Return (archive member, repository path) pairs for candidate documents."""
    root = pack_root.strip("/") + "/"
    candidates: list[tuple[str, str]] = []
    for info in archive.infolist():
        member = info.filename
        path = member if member.startswith(root) else member.partition("/")[2]
        if not path.startswith(root) or not path.lower().endswith((".yaml", ".yml", ".json")):
            continue
        candidates.append((member, path))
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
    with source_archive(spec, sha) as archive:
        for member, path in _candidate_members(archive, spec.pack_root):
            category = pack_category(path)
            if category is None:
                continue
            try:
                raw_text = archive.read(member).decode("utf-8")
                record = normalize_document(raw_text, path, category)
            except (OSError, UnicodeDecodeError, ValueError) as exc:
                raise ValueError(f"Malformed source document {path}: {exc}") from exc
            if record is not None:
                records.setdefault(category, []).append(record)

    ordered_records = {category: records[category] for category in sorted(records)}
    counts = {category: len(records) for category, records in ordered_records.items()}
    dataset = {"_meta": dataset_metadata(spec, sha, counts), **ordered_records}
    write_dataset(output_path, dataset)
    return True
