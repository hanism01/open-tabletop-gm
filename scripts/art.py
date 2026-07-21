"""Small, network-free helpers for campaign-owned art searches."""

from html.parser import HTMLParser
import ipaddress
import re
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit, urlunsplit


ART_KINDS = {"place", "npc", "creature"}
SEARCH_SOURCES = {"deviantart", "web"}
MAX_RESULTS = 5
_NUMERIC_IP_HOST = re.compile(r"^(?:0[xX][0-9a-fA-F]+|[0-9]+)(?:\.(?:0[xX][0-9a-fA-F]+|[0-9]+)){0,3}$")


class ArtValidationError(ValueError):
    """Raised when art-search data is not safe or well formed."""


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
