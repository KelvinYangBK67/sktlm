#!/usr/bin/env python3
"""Build or verify a frozen local independent-review packet."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sktlm.review.packet import (
    ReviewPacketError,
    build_packet,
    verify_packet,
    verify_raw_review_metadata,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Local-only review packet provenance helper")
    commands = parser.add_subparsers(dest="command", required=True)
    build = commands.add_parser("build", help="build a content-addressed packet")
    build.add_argument("--spec", required=True, type=Path)
    build.add_argument("--output-dir", required=True, type=Path)
    build.add_argument("--repo-root", type=Path, default=Path("."))
    verify = commands.add_parser("verify", help="verify packet and optional raw review metadata")
    verify.add_argument("--packet-dir", required=True, type=Path)
    verify.add_argument("--repo-root", type=Path)
    verify.add_argument("--review-metadata", action="append", type=Path, default=[])
    args = parser.parse_args()
    try:
        if args.command == "build":
            manifest = build_packet(args.spec, args.output_dir, repo_root=args.repo_root)
            result = {"valid": True, "packet_sha256": manifest["packet_sha256"], "output_dir": str(args.output_dir)}
        else:
            result = verify_packet(args.packet_dir, repo_root=args.repo_root)
            reviews = [
                verify_raw_review_metadata(path, args.packet_dir)
                for path in args.review_metadata
            ]
            if reviews:
                result["raw_reviews"] = reviews
                result["valid"] = result["valid"] and all(row["valid"] for row in reviews)
                result["errors"].extend(
                    error for row in reviews for error in row["errors"]
                )
    except (ReviewPacketError, FileExistsError) as exc:
        errors = list(exc.errors) if isinstance(exc, ReviewPacketError) else [str(exc)]
        result = {"valid": False, "errors": errors}
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if not result["valid"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()