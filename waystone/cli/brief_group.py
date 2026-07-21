"""Focused ``waystone brief`` commands; main CLI wiring belongs to the cut-over task."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from waystone.project import find_project_root
from waystone.project import brief


def _root(value: str | None) -> Path:
    root = Path(value).resolve() if value else find_project_root(Path.cwd())
    if root is None:
        raise brief.BriefReadError("no initialized project; pass the project root")
    return root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="waystone brief")
    sub = parser.add_subparsers(dest="command", required=True)
    check_parser = sub.add_parser("check")
    check_parser.add_argument("root", nargs="?")
    show_parser = sub.add_parser("show")
    show_parser.add_argument("root", nargs="?")
    show_parser.add_argument("--fact")
    adopt_parser = sub.add_parser("adopt")
    adopt_parser.add_argument("root", nargs="?")
    adopt_parser.add_argument("--evidence", type=Path, required=True)
    adopt_parser.add_argument("--evidence-digest")
    args = parser.parse_args(argv)
    try:
        root = _root(args.root)
        if args.command == "check":
            frame = brief.check_project_brief(root)
            print(f"brief check: {len(frame.facts)} facts, status {frame.status}")
        elif args.command == "show":
            print(json.dumps(
                brief.show_project_brief(root, args.fact),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ))
        else:
            result = brief.adopt_project_brief_from_file(
                root,
                args.evidence,
                declared_evidence_digest=args.evidence_digest,
            )
            print(
                "brief adopt: committed; "
                f"owner_evidence={result.owner_evidence.digest}; "
                f"adoption_record={result.adoption_record.digest}"
            )
        return 0
    except brief.ProjectBriefError as error:
        print(f"waystone brief: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
