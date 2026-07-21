"""Small, network-free helpers for campaign-owned art searches."""

from html.parser import HTMLParser
import ipaddress
import json
import os
import re
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit, urlunsplit

from scripts import paths


ART_KINDS = {"place", "npc", "creature"}
SEARCH_SOURCES = {"deviantart", "web"}
MAX_RESULTS = 5
ART_FILE_VERSION = 1
MAX_TITLE_LENGTH = 200
MAX_LIST_ITEMS = 20
MAX_LIST_ITEM_LENGTH = 80
MAX_CREATOR_LENGTH = 200
MAX_NOTES_LENGTH = 2_000
MAX_STATUS_LENGTH = 80
MAX_ENTITY_ID_LENGTH = 120
_NUMERIC_IP_HOST = re.compile(r"^(?:0[xX][0-9a-fA-F]+|[0-9]+)(?:\.(?:0[xX][0-9a-fA-F]+|[0-9]+)){0,3}$")
_ART_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class ArtValidationError(ValueError):
    """Raised when art-search data is not safe or well formed."""


def art_path(campaign: str):
    """Return the campaign-owned art record file path."""
    return paths.find_campaign(campaign) / "art.json"


def _normalize_text(value: Any, field: str, limit: int, *, required: bool = False) -> str:
    if not isinstance(value, str):
        raise ArtValidationError(f"{field} must be a string")
    normalized = " ".join(value.split())
    if required and not normalized:
        raise ArtValidationError(f"{field} cannot be blank")
    if len(normalized) > limit:
        raise ArtValidationError(f"{field} is too long")
    return normalized


def _normalize_text_list(value: Any, field: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ArtValidationError(f"{field} must be a list")
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        normalized = _normalize_text(item, field, MAX_LIST_ITEM_LENGTH)
        if not normalized:
            continue
        key = normalized.casefold()
        if key not in seen:
            result.append(normalized)
            seen.add(key)
    if len(result) > MAX_LIST_ITEMS:
        raise ArtValidationError(f"{field} has too many values")
    return result


def validate_record(record: dict[str, Any], *, saved_at: str | None = None) -> dict[str, Any]:
    """Return a normalized campaign art record or raise ArtValidationError."""
    if not isinstance(record, dict):
        raise ArtValidationError("Record must be a dictionary")
    record_id = record.get("id")
    if not isinstance(record_id, str) or not _ART_ID.fullmatch(record_id):
        raise ArtValidationError("id must be a lowercase slug")
    kind = record.get("kind")
    if not isinstance(kind, str) or kind not in ART_KINDS:
        raise ArtValidationError("Unknown art kind")

    result: dict[str, Any] = {
        "id": record_id,
        "kind": kind,
        "title": _normalize_text(record.get("title", ""), "title", MAX_TITLE_LENGTH, required=True),
        "aliases": _normalize_text_list(record.get("aliases", []), "aliases"),
        "tags": _normalize_text_list(record.get("tags", []), "tags"),
    }
    for field, limit in (
        ("creator", MAX_CREATOR_LENGTH),
        ("notes", MAX_NOTES_LENGTH),
        ("status", MAX_STATUS_LENGTH),
        ("linked_entity_id", MAX_ENTITY_ID_LENGTH),
    ):
        if field in record and record[field] is not None:
            result[field] = _normalize_text(record[field], field, limit)
    for field in ("image_url", "thumbnail_url", "source_url"):
        if field in record and record[field] is not None:
            value = _normalize_text(record[field], field, 2_000)
            if value:
                result[field] = validate_public_https_url(value)
    result["source_host"] = (urlsplit(result.get("source_url", "")).hostname or "").rstrip(".").lower()
    if saved_at is not None:
        result["saved_at"] = saved_at
    elif "saved_at" in record:
        result["saved_at"] = _normalize_text(record["saved_at"], "saved_at", 80, required=True)
    return result


def _load_records(campaign: str) -> list[dict[str, Any]]:
    path = art_path(campaign)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ArtValidationError("Campaign art file is corrupt") from error
    if not isinstance(payload, dict) or set(payload) != {"version", "records"}:
        raise ArtValidationError("Campaign art file has an invalid root")
    if payload["version"] != ART_FILE_VERSION or not isinstance(payload["records"], list):
        raise ArtValidationError("Campaign art file has an invalid version or records")
    try:
        return [validate_record(record) for record in payload["records"]]
    except ArtValidationError as error:
        raise ArtValidationError("Campaign art file contains an invalid record") from error


def _write_records(campaign: str, records: list[dict[str, Any]]) -> None:
    path = art_path(campaign)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    try:
        temporary_path.write_text(
            json.dumps({"version": ART_FILE_VERSION, "records": records}, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _saved_timestamp() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def save_record(campaign: str, record: dict[str, Any]) -> dict[str, Any]:
    """Validate and atomically persist a new art record for a campaign."""
    records = _load_records(campaign)
    saved = validate_record(record, saved_at=_saved_timestamp())
    if any(existing["id"] == saved["id"] for existing in records):
        raise ArtValidationError("An art record with that id already exists")
    records.append(saved)
    _write_records(campaign, records)
    return saved


def list_records(campaign: str) -> list[dict[str, Any]]:
    """Return campaign art records in deterministic title and ID order."""
    return sorted(_load_records(campaign), key=lambda record: (record["title"].casefold(), record["id"]))


def find_records(campaign: str, query: str) -> list[dict[str, Any]]:
    """Find records by case-insensitive text across their searchable fields."""
    needle = _normalize_text(query, "query", MAX_TITLE_LENGTH, required=True).casefold()
    fields = ("id", "title", "kind", "aliases", "tags")
    matches = []
    for record in list_records(campaign):
        haystack = " ".join(
            " ".join(record[field]) if isinstance(record[field], list) else record[field]
            for field in fields
        ).casefold()
        if needle in haystack:
            matches.append(record)
    return matches


def update_record(campaign: str, record_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    """Apply validated changes to one record, preserving its identity and kind."""
    if not isinstance(changes, dict):
        raise ArtValidationError("changes must be a dictionary")
    if "id" in changes and changes["id"] != record_id:
        raise ArtValidationError("Record id cannot be changed")
    records = _load_records(campaign)
    for index, existing in enumerate(records):
        if existing["id"] == record_id:
            if "kind" in changes and changes["kind"] != existing["kind"]:
                raise ArtValidationError("Record kind cannot be changed")
            updated = validate_record({**existing, **changes}, saved_at=_saved_timestamp())
            records[index] = updated
            _write_records(campaign, records)
            return updated
    raise ArtValidationError("Art record was not found")


def delete_record(campaign: str, record_id: str) -> bool:
    """Delete one record by ID, returning whether a record was removed."""
    if not isinstance(record_id, str) or not _ART_ID.fullmatch(record_id):
        raise ArtValidationError("id must be a lowercase slug")
    records = _load_records(campaign)
    remaining = [record for record in records if record["id"] != record_id]
    if len(remaining) == len(records):
        return False
    _write_records(campaign, remaining)
    return True


def build_search_query(query: str, source: str = "deviantart") -> str:
    """Return a normalized DuckDuckGo query for the requested search source."""
    normalized_query = " ".join(str(query).split())
    if not normalized_query:
        raise ArtValidationError("Search query cannot be blank")
    if source not in SEARCH_SOURCES:
        raise ArtValidationError("Unknown search source")
    if source == "deviantart":
        return normalized_query + " site:deviantart.com"
    return normalized_query


def validate_public_https_url(value: str) -> str:
    """Validate and normalize a URL without resolving or fetching it."""
    if not isinstance(value, str):
        raise ArtValidationError("URL must be a string")

    normalized = value.strip()
    try:
        parts = urlsplit(normalized)
        hostname = parts.hostname
        # Accessing port catches malformed port values, such as ':not-a-port'.
        parts.port
    except ValueError as error:
        raise ArtValidationError("URL is malformed") from error

    if parts.scheme.lower() != "https" or not parts.netloc or not hostname:
        raise ArtValidationError("URL must be absolute HTTPS")
    if parts.username is not None or parts.password is not None:
        raise ArtValidationError("URL credentials are not allowed")

    clean_host = hostname.rstrip(".").lower()
    # This is syntax-only validation. A future fetcher must resolve and
    # revalidate the connection destination to guard against DNS rebinding.
    if clean_host == "localhost" or clean_host.endswith(".localhost"):
        raise ArtValidationError("Local URLs are not allowed")
    if clean_host == "nip.io" or clean_host.endswith(".nip.io"):
        raise ArtValidationError("Wildcard IP aliases are not allowed")
    if _NUMERIC_IP_HOST.fullmatch(clean_host):
        raise ArtValidationError("Numeric IP address forms are not allowed")
    try:
        address = ipaddress.ip_address(clean_host)
    except ValueError:
        address = None
    if address is not None and not address.is_global:
        raise ArtValidationError("Non-public IP addresses are not allowed")

    return urlunsplit((parts.scheme.lower(), parts.netloc, parts.path, parts.query, parts.fragment))


def normalize_candidate(candidate: dict[str, Any]) -> dict[str, str]:
    """Return the stable candidate shape, validating any provided URL fields."""
    if not isinstance(candidate, dict):
        raise ArtValidationError("Candidate must be a dictionary")

    result = {
        "title": str(candidate.get("title", "")).strip(),
        "image_url": "",
        "thumbnail_url": "",
        "source_url": "",
        "creator": str(candidate.get("creator", "")).strip(),
    }
    for key in ("image_url", "thumbnail_url", "source_url"):
        value = candidate.get(key, "")
        if value is None:
            value = ""
        if not isinstance(value, str):
            raise ArtValidationError(f"{key} must be a string")
        if value.strip():
            result[key] = validate_public_https_url(value)

    source_host = urlsplit(result["source_url"]).hostname or ""
    result["source_host"] = source_host.rstrip(".").lower()
    return result


def _canonical_result_url(href: str) -> str:
    """Unwrap DuckDuckGo's `uddg` redirect parameter when present."""
    parts = urlsplit(href)
    redirect_target = parse_qs(parts.query).get("uddg", [""])[0]
    return unquote(redirect_target) if redirect_target else href


class _DuckDuckGoLiteParser(HTMLParser):
    """Extract title/link/image triples from the small DuckDuckGo Lite result markup."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[dict[str, str]] = []
        self._div_depth = 0
        self._result_div_depth: int | None = None
        self._active: dict[str, str] | None = None
        self._in_title_anchor = False

    def _append_active(self) -> None:
        if self._active is not None:
            self.results.append(self._active)
            self._active = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        classes = set((attributes.get("class") or "").split())
        if tag == "div":
            self._div_depth += 1
            if "result" in classes and self._result_div_depth is None:
                self._result_div_depth = self._div_depth
                self._active = {"title": "", "source_url": "", "thumbnail_url": ""}
            return
        if self._active is None:
            if tag != "a" or not ("result-link" in classes or "result__a" in classes):
                return
            self._active = {"title": "", "source_url": "", "thumbnail_url": ""}
        if tag == "a" and ("result-link" in classes or "result__a" in classes):
            if self._result_div_depth is None and self._active["source_url"]:
                self._append_active()
                self._active = {"title": "", "source_url": "", "thumbnail_url": ""}
            self._active["source_url"] = _canonical_result_url(attributes.get("href") or "")
            self._in_title_anchor = True
        elif tag == "img" and not self._active["thumbnail_url"]:
            self._active["thumbnail_url"] = attributes.get("src") or ""

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self._in_title_anchor = False
        if tag == "div":
            if self._result_div_depth == self._div_depth and self._active is not None:
                self._append_active()
                self._result_div_depth = None
            self._div_depth = max(0, self._div_depth - 1)

    def handle_data(self, data: str) -> None:
        if self._active is not None and self._in_title_anchor:
            self._active["title"] += data

    def finish(self) -> None:
        """Store a table-based Lite result after the final tag is consumed."""
        self._append_active()


def parse_duckduckgo_lite_results(markup: str) -> list[dict[str, str]]:
    """Parse up to five normalized result candidates without fetching source pages."""
    parser = _DuckDuckGoLiteParser()
    parser.feed(markup)
    parser.close()
    parser.finish()

    candidates: list[dict[str, str]] = []
    for result in parser.results:
        if len(candidates) == MAX_RESULTS or not result["source_url"]:
            continue
        thumbnail_url = result["thumbnail_url"]
        try:
            candidates.append(
                normalize_candidate(
                    {
                        "title": result["title"],
                        "source_url": result["source_url"],
                        "image_url": thumbnail_url,
                        "thumbnail_url": thumbnail_url,
                        "creator": "",
                    }
                )
            )
        except ArtValidationError:
            continue
    return candidates
