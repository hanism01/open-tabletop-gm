"""Campaign-owned art search, persistence, and LLM-friendly CLI commands."""

import argparse
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
import ipaddress
import json
import os
import re
import sys
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urlsplit, urlunsplit
from urllib.request import Request, urlopen

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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
CACHE_TTL = timedelta(minutes=10)
_NUMERIC_IP_HOST = re.compile(r"^(?:0[xX][0-9a-fA-F]+|[0-9]+)(?:\.(?:0[xX][0-9a-fA-F]+|[0-9]+)){0,3}$")
_ART_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_DNS_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


class ArtValidationError(ValueError):
    """Raised when art-search data is not safe or well formed."""


def _validate_dns_hostname(hostname: str) -> None:
    """Reject malformed non-IP hostnames after IDNA conversion."""
    try:
        ascii_hostname = hostname.encode("idna").decode("ascii")
    except UnicodeError as error:
        raise ArtValidationError("Hostname is malformed") from error
    if len(ascii_hostname) > 253 or any(
        not _DNS_LABEL.fullmatch(label) for label in ascii_hostname.split(".")
    ):
        raise ArtValidationError("Hostname is malformed")


def art_path(campaign: str):
    """Return the campaign-owned art record file path."""
    return paths.find_campaign(campaign) / "art.json"


def search_cache_path(campaign: str):
    """Return the short-lived search candidate cache path for a campaign."""
    return paths.find_campaign(campaign) / ".art_search_cache.json"


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
    if address is None:
        _validate_dns_hostname(clean_host)

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


def fetch_search_results(query: str) -> list[dict[str, str]]:
    """Fetch and parse DuckDuckGo Lite results without visiting result pages."""
    request = Request(
        "https://lite.duckduckgo.com/lite/?q=" + quote_plus(query),
        headers={"User-Agent": "open-tabletop-gm-art/1.0"},
    )
    try:
        with urlopen(request, timeout=10) as response:
            markup = response.read().decode("utf-8", errors="replace")
    except OSError as error:
        raise ArtValidationError("Art search request failed") from error
    return parse_duckduckgo_lite_results(markup)


def _write_search_cache(campaign: str, candidates: list[dict[str, str]]) -> None:
    path = search_cache_path(campaign)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"created_at": _saved_timestamp(), "candidates": candidates}) + "\n",
        encoding="utf-8",
    )


def _load_search_cache(campaign: str) -> list[dict[str, str]]:
    path = search_cache_path(campaign)
    if not path.exists():
        raise ArtValidationError("No valid art search cache is available; run search first")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        created_at = datetime.fromisoformat(payload["created_at"].replace("Z", "+00:00"))
        candidates = payload["candidates"]
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ArtValidationError("Art search cache is invalid; run search again") from error
    if created_at.tzinfo is None or datetime.now(timezone.utc) - created_at > CACHE_TTL:
        raise ArtValidationError("Art search cache has expired; run search again")
    if not isinstance(candidates, list):
        raise ArtValidationError("Art search cache is invalid; run search again")
    try:
        return [normalize_candidate(candidate) for candidate in candidates]
    except ArtValidationError as error:
        raise ArtValidationError("Art search cache is invalid; run search again") from error


def post_display_art(payload: dict[str, str]) -> None:
    """Post an art display payload. The display endpoint is intentionally pending."""
    del payload


def _display_payload(record: dict[str, Any]) -> dict[str, str]:
    """Build a validated, display-ready payload from a saved record or one-off."""
    title = _normalize_text(record.get("title", ""), "title", MAX_TITLE_LENGTH, required=True)
    kind = record.get("kind", "")
    if kind and kind not in ART_KINDS:
        raise ArtValidationError("Unknown art kind")
    payload = {
        "title": title,
        "category": kind,
        "kind": kind,
        "image_url": "",
        "source_url": "",
        "creator": _normalize_text(record.get("creator", ""), "creator", MAX_CREATOR_LENGTH),
        "alt": title,
    }
    for field in ("image_url", "source_url"):
        value = record.get(field, "")
        if value:
            payload[field] = validate_public_https_url(value)
    return payload


def _csv_values(value: str | None) -> list[str]:
    return [] if value is None else [item.strip() for item in value.split(",") if item.strip()]


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Search and manage campaign art.")
    commands = parser.add_subparsers(dest="command", required=True)
    search = commands.add_parser("search")
    search.add_argument("--campaign", required=True)
    search.add_argument("--query", required=True)
    search.add_argument("--source", choices=sorted(SEARCH_SOURCES), default="deviantart")
    save = commands.add_parser("save")
    save.add_argument("--campaign", required=True)
    save.add_argument("--candidate", required=True, type=int)
    save.add_argument("--as", dest="record_id", required=True)
    save.add_argument("--kind", choices=sorted(ART_KINDS), required=True)
    save.add_argument("--tags")
    find = commands.add_parser("find")
    find.add_argument("--campaign", required=True)
    find.add_argument("--query", required=True)
    listing = commands.add_parser("list")
    listing.add_argument("--campaign", required=True)
    listing.add_argument("--kind", choices=sorted(ART_KINDS))
    update = commands.add_parser("update")
    update.add_argument("--campaign", required=True)
    update.add_argument("--id", required=True)
    for option in ("title", "creator", "notes", "status", "image_url", "thumbnail_url", "source_url"):
        update.add_argument("--" + option.replace("_", "-"), dest=option)
    update.add_argument("--tags")
    update.add_argument("--aliases")
    delete = commands.add_parser("delete")
    delete.add_argument("--campaign", required=True)
    delete.add_argument("--id", required=True)
    show = commands.add_parser("show")
    show.add_argument("--campaign")
    show.add_argument("--id")
    show.add_argument("--url")
    show.add_argument("--source-url")
    show.add_argument("--title")
    commands.add_parser("hide")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the art CLI, returning 0 on success and 2 for malformed input."""
    try:
        args = _parser().parse_args(argv)
    except SystemExit as error:
        return int(error.code)
    try:
        if args.command == "search":
            candidates = fetch_search_results(build_search_query(args.query, args.source))
            _write_search_cache(args.campaign, candidates)
            print(json.dumps(candidates, separators=(",", ":")))
        elif args.command == "save":
            candidates = _load_search_cache(args.campaign)
            if args.candidate < 0 or args.candidate >= len(candidates):
                raise ArtValidationError("Candidate number is not in the search cache")
            candidate = candidates[args.candidate]
            saved = save_record(args.campaign, {
                **candidate, "id": args.record_id, "kind": args.kind, "tags": _csv_values(args.tags),
            })
            search_cache_path(args.campaign).unlink(missing_ok=True)
            print(json.dumps(saved, separators=(",", ":")))
        elif args.command == "find":
            print(json.dumps(find_records(args.campaign, args.query), separators=(",", ":")))
        elif args.command == "list":
            records = list_records(args.campaign)
            if args.kind:
                records = [record for record in records if record["kind"] == args.kind]
            print(json.dumps(records, separators=(",", ":")))
        elif args.command == "update":
            changes = {key: value for key, value in vars(args).items() if key in {
                "title", "creator", "notes", "status", "image_url", "thumbnail_url", "source_url"
            } and value is not None}
            if args.tags is not None:
                changes["tags"] = _csv_values(args.tags)
            if args.aliases is not None:
                changes["aliases"] = _csv_values(args.aliases)
            if not changes:
                raise ArtValidationError("Update requires at least one changed field")
            print(json.dumps(update_record(args.campaign, args.id, changes), separators=(",", ":")))
        elif args.command == "delete":
            if not delete_record(args.campaign, args.id):
                raise ArtValidationError("Art record was not found")
            print(json.dumps({"deleted": args.id}, separators=(",", ":")))
        elif args.command == "show":
            if args.campaign and args.id and not any((args.url, args.source_url, args.title)):
                records = [record for record in list_records(args.campaign) if record["id"] == args.id]
                if not records:
                    raise ArtValidationError("Art record was not found")
                post_display_art(_display_payload(records[0]))
                print(json.dumps(records[0], separators=(",", ":")))
            elif not args.campaign and args.url and args.source_url and args.title:
                post_display_art(_display_payload({
                    "title": args.title, "image_url": args.url, "source_url": args.source_url,
                }))
            else:
                raise ArtValidationError("Show requires either --campaign and --id, or --url, --source-url, and --title")
        else:
            post_display_art({"action": "hide"})
    except (ArtValidationError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
