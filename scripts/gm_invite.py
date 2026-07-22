#!/usr/bin/env python3
"""
gm_invite.py — mint / revoke / list signed remote-play invite links (Slice 0).

Usage:
    python3 scripts/gm_invite.py -c <campaign> mint Kara Tom [--host game.example.com] [--ttl-hours 72]
    python3 scripts/gm_invite.py -c <campaign> --revoke Kara
    python3 scripts/gm_invite.py -c <campaign> list

Each mint prints one join URL per character. Join links are single-use and
expire (default 72h). The signing secret lives in display/.invite_secret
(created on first run, mode 0600, never printed).
"""
import argparse
import os
import pathlib
import sys

_REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "display"))
import tokens  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-c", "--campaign", required=True)
    ap.add_argument("--display-dir", default=str(_REPO / "display"),
                    help="where .invite_secret / .revoked.json live (tests override)")
    ap.add_argument("--host", default=os.environ.get("GM_PUBLIC_HOST", "localhost:5001"))
    ap.add_argument("--ttl-hours", type=float, default=72.0)
    ap.add_argument("--revoke", metavar="CHARACTER")
    ap.add_argument("command", nargs="?", choices=["mint", "list"])
    ap.add_argument("characters", nargs="*")
    args = ap.parse_args()

    display = pathlib.Path(args.display_dir)
    store = tokens.RevocationStore(display / ".revoked.json")

    if args.revoke:
        player_id = args.revoke.strip().lower()
        sid = store.active().get(player_id)
        if not sid:
            print(f"error: no active session for '{player_id}'", file=sys.stderr)
            return 1
        store.revoke_sid(sid)
        print(f"revoked: {player_id}")
        return 0

    if args.command == "list":
        active = store.active()
        if not active:
            print("no active players")
        for player_id, sid in sorted(active.items()):
            revoked = " (revoked)" if store.is_sid_revoked(sid) else ""
            print(f"{player_id}{revoked}")
        return 0

    if args.command == "mint":
        if not args.characters:
            print("error: mint needs at least one character name", file=sys.stderr)
            return 1
        secret = tokens.ensure_secret(display / ".invite_secret")
        scheme = "http" if args.host.startswith(("localhost", "127.0.0.1")) else "https"
        for character in args.characters:
            character = character.strip()
            token = tokens.mint_join(
                character.lower(), character, args.campaign,
                secret=secret, ttl_s=int(args.ttl_hours * 3600))
            print(f"{character}: {scheme}://{args.host}/j/{token}")
        return 0

    ap.print_help()
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, RuntimeError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
