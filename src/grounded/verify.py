"""The verifier.

Two tiers, deliberately kept apart:

  EXACT   quotes, numbers, citations, named entities.
          Present in the source or not. No judgement, no model, no scoring.
          An absent quotation is fabrication. This tier is the product.

  HEURISTIC  whole sentences, scored by distinctive-token overlap.
          Advisory only. A low score may mean fabrication or may mean good
          paraphrase. Reported separately and never counted as a failure
          unless the caller asks for it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from .claims import Claim, Kind
from .sources import Source, normalise, squeeze


class Verdict(str, Enum):
    GROUNDED = "grounded"
    NOT_FOUND = "not_found"
    WEAK = "weak"            # heuristic tier only
    SKIPPED = "skipped"


EXACT_KINDS = {Kind.QUOTE, Kind.NUMBER, Kind.CITATION, Kind.ENTITY}

_TOKEN = re.compile(r"[0-9A-Za-zÀ-ɏͰ-Ͽ一-鿿"
                    r"぀-ゟ゠-ヿ]+")
_STOP = {
    "the", "a", "an", "of", "to", "in", "is", "are", "was", "were", "be",
    "been", "and", "or", "but", "if", "then", "that", "this", "these",
    "those", "it", "its", "as", "at", "by", "for", "from", "on", "with",
    "not", "no", "can", "will", "would", "should", "may", "might", "must",
    "have", "has", "had", "do", "does", "did", "we", "you", "they",
    "する", "した", "して", "です", "ます", "ある", "いる", "こと", "もの",
    "これ", "それ", "この", "その", "ため", "よう", "から", "など", "また",
}


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(normalise(text))
            if len(t) >= 2 and t not in _STOP]


@dataclass
class Finding:
    claim: Claim
    verdict: Verdict
    tier: str                       # "exact" | "heuristic"
    found_in: str | None = None     # source path
    found_line: int | None = None
    score: float | None = None      # heuristic tier only
    note: str = ""

    @property
    def is_failure(self) -> bool:
        return self.verdict is Verdict.NOT_FOUND


@dataclass
class Result:
    findings: list[Finding] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    claim_count: int = 0

    @property
    def exact(self) -> list[Finding]:
        return [f for f in self.findings if f.tier == "exact"]

    @property
    def heuristic(self) -> list[Finding]:
        return [f for f in self.findings if f.tier == "heuristic"]

    @property
    def failures(self) -> list[Finding]:
        return [f for f in self.exact if f.is_failure]

    @property
    def grounded_count(self) -> int:
        return sum(1 for f in self.exact if f.verdict is Verdict.GROUNDED)

    @property
    def rate(self) -> float:
        total = len(self.exact)
        return (self.grounded_count / total) if total else 1.0

    @property
    def passed(self) -> bool:
        return not self.failures


# ------------------------------------------------------------------ matching


def _locate_exact(needle: str, sources: list[Source]) -> tuple[Source, int] | None:
    """Find `needle` in any source. Try normalised first, then the
    punctuation/whitespace-stripped form so that line-wrapped PDF text and
    reflowed quotations still match."""
    n_norm = normalise(needle)
    if len(n_norm) < 2:
        return None
    for src in sources:
        idx = src.normalised.find(n_norm)
        if idx >= 0:
            approx = src.raw.casefold().find(n_norm[:40])
            return src, src.line_of(approx if approx >= 0 else 0)
    n_sq = squeeze(needle)
    if len(n_sq) >= 4:
        for src in sources:
            idx = src.squeezed.find(n_sq)
            if idx >= 0:
                return src, 0
    return None


def _score_sentence(sentence: str, sources: list[Source]) -> tuple[float, Source | None]:
    toks = _tokens(sentence)
    if not toks:
        return 1.0, None
    best, best_src = 0.0, None
    for src in sources:
        hay = src.normalised
        hits = sum(1 for t in set(toks) if t in hay)
        ratio = hits / len(set(toks))
        if ratio > best:
            best, best_src = ratio, src
    return best, best_src


# ------------------------------------------------------------------ public


def verify(claims: list[Claim], sources: list[Source], *,
           sentence_threshold: float = 0.60) -> Result:
    result = Result(sources=[str(s.path) for s in sources],
                    claim_count=len(claims))

    for claim in claims:
        if claim.kind in EXACT_KINDS:
            hit = _locate_exact(claim.text, sources)
            if hit:
                src, line = hit
                result.findings.append(Finding(
                    claim=claim, verdict=Verdict.GROUNDED, tier="exact",
                    found_in=str(src.path), found_line=line or None))
            else:
                result.findings.append(Finding(
                    claim=claim, verdict=Verdict.NOT_FOUND, tier="exact",
                    note="not present in any source"))
        else:
            score, src = _score_sentence(claim.text, sources)
            verdict = Verdict.GROUNDED if score >= sentence_threshold else Verdict.WEAK
            result.findings.append(Finding(
                claim=claim, verdict=verdict, tier="heuristic",
                found_in=str(src.path) if src else None,
                score=round(score, 3),
                note="advisory: low overlap may be paraphrase, not fabrication"
                     if verdict is Verdict.WEAK else ""))
    return result
