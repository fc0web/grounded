"""MCP server: let a model check its own draft before it answers.

The point is that the checker is *not* a model. A model grading its own
output can be wrong in the same direction twice. String matching against
the source cannot.

Run:
    grounded-mcp                 # stdio
Register with Claude Desktop / Claude Code:
    {"mcpServers": {"grounded": {"command": "grounded-mcp"}}}
"""

from __future__ import annotations

import json
import sys

from .audit import AuditLog
from .claims import Kind, extract
from .sources import SourceError, load
from .verify import verify

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:  # pragma: no cover
    print(
        "grounded-mcp needs the MCP SDK.\n"
        "    pip install 'grounded[mcp]'",
        file=sys.stderr,
    )
    raise SystemExit(1)

mcp = FastMCP("grounded")

_KINDS = {Kind.QUOTE, Kind.NUMBER, Kind.CITATION, Kind.ENTITY}


def _run(text: str, source_paths: list[str], *, sentences: bool) -> dict:
    kinds = set(_KINDS)
    if sentences:
        kinds.add(Kind.SENTENCE)
    sources = load(list(source_paths))
    result = verify(extract(text, kinds=kinds), sources)
    return {
        "passed": result.passed,
        "checked": len(result.exact),
        "grounded": result.grounded_count,
        "rate": round(result.rate, 4),
        "sources": result.sources,
        "not_found": [
            {"kind": f.claim.kind.value, "text": f.claim.text}
            for f in result.failures
        ],
        "weak_sentences": [
            {"score": f.score, "text": f.claim.text}
            for f in result.heuristic if f.verdict.value == "weak"
        ],
    }


@mcp.tool()
def verify_against_sources(text: str, source_paths: list[str],
                           include_sentences: bool = False) -> str:
    """Check whether the claims in `text` actually appear in the given files.

    Use this on a draft answer BEFORE sending it, whenever the answer is
    supposed to be based on specific documents. Every quotation, figure,
    citation and proper noun is looked up literally in the sources.

    A claim listed under `not_found` does not appear anywhere in the
    sources. Either correct it, remove it, or say plainly that it is not
    supported by the provided material. Do not restate it as fact.

    `weak_sentences` is advisory only: low overlap can mean good paraphrase.

    Args:
        text: the draft answer to check.
        source_paths: files or directories the answer should be based on.
        include_sentences: also run the advisory sentence-overlap tier.
    """
    try:
        return json.dumps(_run(text, source_paths, sentences=include_sentences),
                          ensure_ascii=False, indent=2)
    except SourceError as exc:
        return json.dumps({"error": str(exc),
                           "hint": "sources unreadable; a missing source would "
                                   "make every claim look fabricated, so the "
                                   "check was not run"}, ensure_ascii=False)


@mcp.tool()
def check_quote(quote: str, source_paths: list[str]) -> str:
    """Check one specific quotation against the sources before using it.

    Returns whether the exact string is present, and where. Cheaper than
    verifying a whole draft when you only need to confirm a single
    quotation you are about to attribute to a document.
    """
    try:
        sources = load(list(source_paths))
    except SourceError as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
    from .sources import normalise, squeeze
    n, s = normalise(quote), squeeze(quote)
    for src in sources:
        if n and n in src.normalised:
            return json.dumps({"present": True, "source": str(src.path),
                               "match": "exact"}, ensure_ascii=False)
    for src in sources:
        if len(s) >= 4 and s in src.squeezed:
            return json.dumps({"present": True, "source": str(src.path),
                               "match": "whitespace-insensitive"},
                              ensure_ascii=False)
    return json.dumps({"present": False,
                       "advice": "this string is not in the sources; do not "
                                 "present it as a quotation from them"},
                      ensure_ascii=False)


@mcp.tool()
def verify_audit_log(log_path: str) -> str:
    """Check that a grounded audit log has not been altered since it was
    written. Returns whether the hash chain is intact and, if not, the first
    entry where it breaks."""
    log = AuditLog(log_path)
    intact, bad, message = log.verify()
    return json.dumps({"intact": intact, "first_bad_seq": bad,
                       "message": message, "entries": len(log.entries())},
                      ensure_ascii=False)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
