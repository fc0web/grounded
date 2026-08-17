"""grounded — check that generated text is actually supported by its sources.

Deterministic. Offline. No model involved in the checking.

    from grounded import check
    result = check(answer_text, ["manual.pdf", "notes/"])
    if not result.passed:
        for f in result.failures:
            print("fabricated:", f.claim.text)
"""

from __future__ import annotations

__version__ = "0.1.0"

from .claims import Claim, Kind, extract
from .sources import Source, SourceError, load, load_one, normalise
from .verify import Finding, Result, Verdict, verify

__all__ = [
    "__version__",
    "check",
    "Claim", "Kind", "extract",
    "Source", "SourceError", "load", "load_one", "normalise",
    "Finding", "Result", "Verdict", "verify",
]


def check(text: str, sources: list[str], *, kinds: set[Kind] | None = None,
          sentences: bool = False, sentence_threshold: float = 0.60) -> Result:
    """One-call convenience wrapper.

    `text`    the generated text to check
    `sources` paths to the documents it is supposed to be based on
    """
    kind_set = set(kinds) if kinds else {
        Kind.QUOTE, Kind.NUMBER, Kind.CITATION, Kind.ENTITY}
    if sentences:
        kind_set.add(Kind.SENTENCE)
    loaded = load(list(sources))
    return verify(extract(text, kinds=kind_set), loaded,
                  sentence_threshold=sentence_threshold)
