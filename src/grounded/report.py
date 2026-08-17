"""Rendering. Text for humans, JSON for machines, SARIF-ish nothing fancy."""

from __future__ import annotations

import json

from .verify import Finding, Result, Verdict

RESET = "\033[0m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
DIM = "\033[2m"
BOLD = "\033[1m"


def _c(text: str, colour: str, enabled: bool) -> str:
    return f"{colour}{text}{RESET}" if enabled else text


def to_json(result: Result, *, indent: int = 2) -> str:
    def f(x: Finding) -> dict:
        d = {
            "kind": x.claim.kind.value,
            "text": x.claim.text,
            "verdict": x.verdict.value,
            "tier": x.tier,
        }
        if x.found_in:
            d["found_in"] = x.found_in
        if x.found_line:
            d["found_line"] = x.found_line
        if x.score is not None:
            d["score"] = x.score
        if x.note:
            d["note"] = x.note
        return d

    return json.dumps({
        "sources": result.sources,
        "claims_extracted": result.claim_count,
        "exact": {
            "checked": len(result.exact),
            "grounded": result.grounded_count,
            "not_found": len(result.failures),
            "rate": round(result.rate, 4),
        },
        "heuristic": {
            "checked": len(result.heuristic),
            "weak": sum(1 for x in result.heuristic if x.verdict is Verdict.WEAK),
        },
        "passed": result.passed,
        "findings": [f(x) for x in result.findings],
    }, ensure_ascii=False, indent=indent)


def to_text(result: Result, *, colour: bool = True, show_grounded: bool = False,
            width: int = 88) -> str:
    lines: list[str] = []
    add = lines.append

    add(_c("grounded — source verification report", BOLD, colour))
    add("")
    add(f"sources : {len(result.sources)} file(s)")
    for s in result.sources:
        add(f"          {s}")
    add("")

    fails = result.failures
    total = len(result.exact)

    add(_c("EXACT CHECKS", BOLD, colour) +
        _c("   (present in source, or fabricated)", DIM, colour))
    add(f"  checked   {total}")
    add("  grounded  " + _c(str(result.grounded_count), GREEN, colour))
    add("  NOT FOUND " + _c(str(len(fails)), RED if fails else GREEN, colour))
    if total:
        add(f"  rate      {result.rate:.1%}")
    add("")

    if fails:
        add(_c("NOT FOUND IN ANY SOURCE", RED + BOLD, colour))
        for x in fails:
            text = x.claim.text.replace("\n", " ")
            if len(text) > width:
                text = text[: width - 1] + "…"
            add(f"  {_c('✗', RED, colour)} [{x.claim.kind.value}] {text}")
        add("")

    if show_grounded:
        ok = [x for x in result.exact if x.verdict is Verdict.GROUNDED]
        if ok:
            add(_c("GROUNDED", GREEN, colour))
            for x in ok:
                text = x.claim.text.replace("\n", " ")
                if len(text) > width - 20:
                    text = text[: width - 21] + "…"
                loc = f" {x.found_in}" if x.found_in else ""
                loc += f":{x.found_line}" if x.found_line else ""
                add(f"  {_c('✓', GREEN, colour)} [{x.claim.kind.value}] {text}"
                    + _c(loc, DIM, colour))
            add("")

    weak = [x for x in result.heuristic if x.verdict is Verdict.WEAK]
    if result.heuristic:
        add(_c("HEURISTIC", BOLD, colour) +
            _c("   (advisory only — low overlap may be paraphrase)", DIM, colour))
        add(f"  checked   {len(result.heuristic)}")
        add(f"  weak      {len(weak)}")
        for x in weak[:20]:
            text = x.claim.text.replace("\n", " ")
            if len(text) > width - 12:
                text = text[: width - 13] + "…"
            add(f"  {_c('?', YELLOW, colour)} ({x.score:.2f}) {text}")
        if len(weak) > 20:
            add(_c(f"  … and {len(weak) - 20} more", DIM, colour))
        add("")

    if result.passed:
        add(_c("PASS", GREEN + BOLD, colour) +
            "  every exact claim was found in the sources.")
    else:
        add(_c("FAIL", RED + BOLD, colour) +
            f"  {len(fails)} claim(s) are not in any source.")
    return "\n".join(lines)
