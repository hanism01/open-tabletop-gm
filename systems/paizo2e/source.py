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
import zlib


GITHUB_API = "https://api.github.com"
GITHUB_CODELOAD = "https://codeload.github.com"
USER_AGENT = "ttrpg-skill-foundry-source/1.0"
HTTP_TIMEOUT_SECONDS = 30
# These limits keep a corrupted or unexpectedly large upstream archive bounded.
_MEBIBYTE = 1024 * 1024
MAX_ARCHIVE_BYTES = 256 * _MEBIBYTE
MAX_MEMBER_BYTES = 16 * _MEBIBYTE
MAX_SELECTED_BYTES = 160 * _MEBIBYTE

# Conservative high-water marks observed for the v14-dev source archive and its
# selected pack roots. Keep these explicit so future source growth is reviewed
# before it reaches a production cap.
CURRENT_EXPECTED_ARCHIVE_BYTES = 192 * _MEBIBYTE
CURRENT_EXPECTED_MEMBER_BYTES = 4 * _MEBIBYTE
CURRENT_EXPECTED_SELECTED_BYTES = {
    "packs/pf2e": 128 * _MEBIBYTE,
    "packs/sf2e": 32 * _MEBIBYTE,
}


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


def needs_rebuild(path: str | Path, spec: SourceSpec, sha: str) -> bool:
    """Return whether *path* is absent or lacks the exact expected provenance."""
    try:
        with Path(path).open(encoding="utf-8") as handle:
            dataset = json.load(handle)
        metadata = dataset["_meta"]
        origin = metadata["source"]
        return not (
            metadata["schema_version"] == 1
            and metadata["system"] == spec.system
            and origin["repo"] == spec.repo
            and origin["ref"] == spec.ref
            and origin["sha"] == sha
            and origin["pack_root"] == spec.pack_root
        )
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
            length = response.headers.get("Content-Length")
            if length is not None and int(length) > MAX_ARCHIVE_BYTES:
                raise RuntimeError(f"Source archive exceeds {MAX_ARCHIVE_BYTES} byte limit")
            payload = response.read(MAX_ARCHIVE_BYTES + 1)
            if len(payload) > MAX_ARCHIVE_BYTES:
                raise RuntimeError(f"Source archive exceeds {MAX_ARCHIVE_BYTES} byte limit")
            return ZipFile(BytesIO(payload))
    except (HTTPError, URLError, OSError, BadZipFile) as exc:
        raise RuntimeError(f"GitHub source archive request failed for {sha}: {exc}") from exc


def _candidate_members(archive: ZipFile, pack_root: str) -> list[tuple[str, str, int]]:
    """Return (archive member, repository path) pairs for candidate documents."""
    root = pack_root.strip("/") + "/"
    candidates: list[tuple[str, str, int]] = []
    for info in archive.infolist():
        member = info.filename
        path = member if member.startswith(root) else member.partition("/")[2]
        if (
            not path.startswith(root)
            or path.rsplit("/", 1)[-1] == "_folders.json"
            or not path.lower().endswith((".yaml", ".yml", ".json"))
        ):
            continue
        candidates.append((member, path, info.file_size))
    return candidates


def build_dataset(spec: SourceSpec, output_path: str | Path, force: bool = False) -> bool:
    """Build a normalized dataset, replacing its output only after full success."""
    sha = resolve_ref(spec)
    if not force and not needs_rebuild(output_path, spec, sha):
        print(f"{spec.system} dataset is up to date.")
        return False

    # Import lazily so the source and normalization modules remain independently usable.
    from systems.paizo2e.packs import normalize_document, pack_category

    records: dict[str, list[dict[str, object]]] = {}
    with source_archive(spec, sha) as archive:
        candidates = _candidate_members(archive, spec.pack_root)
        if not candidates:
            raise ValueError(f"No candidate documents found under {spec.pack_root}")
        selected_bytes = 0
        for member, path, member_size in candidates:
            category = pack_category(path)
            if category is None:
                continue
            if member_size > MAX_MEMBER_BYTES:
                raise ValueError(f"Source member {path} exceeds size limit")
            selected_bytes += member_size
            if selected_bytes > MAX_SELECTED_BYTES:
                raise ValueError("Selected source documents exceed size limit")
            try:
                raw_text = archive.read(member).decode("utf-8")
                record = normalize_document(raw_text, path, category)
            except (BadZipFile, EOFError, OSError, RuntimeError, UnicodeDecodeError, ValueError, zlib.error) as exc:
                raise ValueError(f"Malformed source document {path}: {exc}") from exc
            if record is not None:
                records.setdefault(category, []).append(record)

    ordered_records = {category: records[category] for category in sorted(records)}
    if not ordered_records:
        raise ValueError(f"No usable records found under {spec.pack_root}")
    counts = {category: len(records) for category, records in ordered_records.items()}
    dataset = {"_meta": dataset_metadata(spec, sha, counts), **ordered_records}
    write_dataset(output_path, dataset)
    return True
