"""Foundry VTT source retrieval and generated-dataset helpers."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
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
    temporary = destination.with_name(f"{destination.name}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(dataset, handle, ensure_ascii=False, separators=(",", ":"))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, destination)


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
    try:
        return payload["tree"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError(f"GitHub tree response lacked a tree for {sha}") from exc
