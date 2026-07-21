# Campaign Art Library and Display Image

## Purpose

Give the GM LLM a small, deterministic workflow for finding reference art, presenting it
to players through the existing web display, and retaining selected artwork for recurring
campaign entities. This covers places, NPCs, and generic creature archetypes. It does not
include generative AI or a human-operated image-search console.

## Scope

Art is campaign-owned. A campaign is one persistent game world and its associated state,
NPCs, characters, session logs, and imported one-shot material. An imported one-shot
therefore creates its own campaign and its own art library.

The initial implementation persists an `art.json` file in the campaign directory. Each
record contains a stable ID, title, aliases, kind (`place`, `npc`, or `creature`), tags,
selected image URL, optional thumbnail URL, canonical source URL, available creator or
attribution text, source host, saved timestamp, optional linked campaign-entity ID, and
notes/status.

The system stores metadata and remote URLs, not copied artwork. A global shared library is
deferred; later work may add an explicit opt-in library/import mechanism without silently
moving assets between campaigns.

## GM LLM Workflow

The GM uses narrow tool commands rather than operating a browser UI:

1. `art search --query <text> [--source deviantart|web]` returns a capped, normalized list
   of candidates from DuckDuckGo Lite. The default source is `deviantart`.
2. The default `--source deviantart` adds `site:deviantart.com` to the DuckDuckGo Lite
   query. The GM selects `--source web` only when wider web results are wanted. DeviantArt
   is not directly scraped and does not have a separate result view.
3. The GM selects a candidate and either shows it once with `art show --url <url>` or saves
   it using `art save --candidate <n> --as <id> --kind <place|npc|creature>`.
4. Saved art is recalled with `art find`, `art list`, and `art show --id <id>`; metadata is
   corrected through `art update` and removed with `art delete`.
5. `art hide` clears the currently displayed artwork.

Search results retain the candidate's source URL and any available creator information so
the GM can choose art with provenance. There is no GenAI fallback.

## Display

`art show` publishes a single active-art SSE event. The display shows a non-obstructive
image panel or overlay with alt text plus a caption and source link. The active-art state
is replayed to clients that reconnect. A blocked or broken remote image has a clear
failure state; it must not disrupt player input or the responsive phone layout.

## Safety and Operational Constraints

DuckDuckGo Lite scraping is best-effort: cap results, bound requests, debounce/cache
queries, and return a useful no-results result. Do not automatically download, proxy, or
rehost third-party art in v1. Preserve attribution/source links and let the operator
replace or remove a selected record.

If a future version fetches or caches remote images, it must first block private/local
addresses and enforce safe redirect handling, HTTPS validation, content-type and size
limits, timeouts, and rate limits. It must never let arbitrary remote URLs become
server-side requests without those controls.

## Verification

Automated tests cover DeviantArt domain-restricted query construction, candidate parser
normalization, art-record persistence and recall, authenticated art-display events and SSE
replay, and rejection of malicious/private URLs where URL validation applies.
