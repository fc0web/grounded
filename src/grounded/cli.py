"""Command line interface.

    grounded check ANSWER.md --source docs/ --source spec.pdf
    cat answer.txt | grounded check - -s manual.pdf --json
    grounded audit --log .grounded/audit.jsonl
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .audit import AuditLog
from .claims import Kind, extract
from .report import to_json, to_text
from .sources import SourceError, load
from .verify import verify

KIND_CHOICES = [k.value for k in Kind]


def _read_input(target: str) -> str:
    if target == "-":
        return sys.stdin.read()
    p = Path(target)
    if not p.exists():
        raise SourceError(f"{target}: not found")
    if p.suffix.lower() == ".pdf":
        from .sources import pdf_to_text
        return pdf_to_text(p)
    return p.read_text(encoding="utf-8", errors="replace")


def cmd_check(args: argparse.Namespace) -> int:
    text = _read_input(args.text)
    if not text.strip():
        print("grounded: input is empty", file=sys.stderr)
        return 2

    sources = load(list(args.source), recursive=not args.no_recursive)

    kinds = {Kind(k) for k in args.kind} if args.kind else {
        Kind.QUOTE, Kind.NUMBER, Kind.CITATION, Kind.ENTITY}
    if args.sentences:
        kinds.add(Kind.SENTENCE)

    claims = extract(text, kinds=kinds)
    result = verify(claims, sources, sentence_threshold=args.threshold)

    if args.json:
        print(to_json(result))
    else:
        print(to_text(result, colour=not args.no_colour,
                      show_grounded=args.verbose))

    if args.log:
        entry = AuditLog(Path(args.log)).append({
            "input": args.text,
            "sources": result.sources,
            "checked": len(result.exact),
            "grounded": result.grounded_count,
            "not_found": [f.claim.text for f in result.failures],
            "passed": result.passed,
        }, at=args.at or "unspecified")
        if not args.json:
            print(f"\naudit: seq {entry['seq']}  {entry['hash'][:16]}…")

    if result.passed:
        return 0
    return 0 if args.no_fail else 1


def cmd_audit(args: argparse.Namespace) -> int:
    log = AuditLog(Path(args.log))
    entries = log.entries()
    intact, bad, message = log.verify()
    print(f"entries : {len(entries)}")
    print(f"status  : {message}")
    if not intact:
        print(f"first bad entry: seq {bad}")
    if entries and args.verbose:
        print()
        for e in entries:
            p = e["payload"]
            mark = "PASS" if p.get("passed") else "FAIL"
            print(f"  #{e['seq']:<4} {e['at']:<26} {mark:<5} "
                  f"{p.get('grounded')}/{p.get('checked')}  {e['hash'][:12]}…")
    return 0 if intact else 1


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="grounded",
        description="Check whether the claims in a piece of generated text "
                    "actually appear in your source documents. "
                    "Deterministic, offline, no model.")
    ap.add_argument("--version", action="version", version=f"grounded {__version__}")
    sub = ap.add_subparsers(dest="command", required=True)

    c = sub.add_parser("check", help="verify text against sources")
    c.add_argument("text", help="file to check, or '-' for stdin")
    c.add_argument("-s", "--source", action="append", required=True,
                   metavar="PATH", help="source file or directory (repeatable)")
    c.add_argument("--kind", action="append", choices=KIND_CHOICES,
                   help="restrict to these claim kinds (repeatable)")
    c.add_argument("--sentences", action="store_true",
                   help="also run the advisory sentence-overlap tier")
    c.add_argument("--threshold", type=float, default=0.60,
                   help="sentence overlap threshold (default 0.60)")
    c.add_argument("--json", action="store_true", help="machine-readable output")
    c.add_argument("-v", "--verbose", action="store_true",
                   help="also list the claims that were found")
    c.add_argument("--no-colour", "--no-color", action="store_true")
    c.add_argument("--no-recursive", action="store_true",
                   help="do not descend into source directories")
    c.add_argument("--no-fail", action="store_true",
                   help="always exit 0, even when claims are unfounded")
    c.add_argument("--log", metavar="PATH",
                   help="append the result to a hash-chained audit log")
    c.add_argument("--at", metavar="TIMESTAMP",
                   help="timestamp recorded in the audit log")
    c.set_defaults(func=cmd_check)

    a = sub.add_parser("audit", help="verify the audit log has not been altered")
    a.add_argument("--log", required=True, metavar="PATH")
    a.add_argument("-v", "--verbose", action="store_true")
    a.set_defaults(func=cmd_audit)

    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except SourceError as exc:
        print(f"grounded: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
