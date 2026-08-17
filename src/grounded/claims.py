"""Extract the checkable units from a piece of generated text.

Design rule: only extract things whose absence from the source is
*evidence of fabrication*, not merely evidence of paraphrase. A model that
rewords a sentence is doing its job; a model that invents a quotation, a
figure or a citation is not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class Kind(str, Enum):
    QUOTE = "quote"
    NUMBER = "number"
    CITATION = "citation"
    ENTITY = "entity"
    SENTENCE = "sentence"


@dataclass(frozen=True)
class Claim:
    kind: Kind
    text: str
    start: int
    end: int
    context: str = ""

    @property
    def line(self) -> int:
        return self.context.count("\n", 0, self.start) + 1 if self.context else 0


# ------------------------------------------------------------------ patterns

# Prose wraps. A quotation broken across lines is still a quotation, and
# missing it would let the highest-value fabrication through — so these
# span single newlines, but stop at a blank line (paragraph boundary).
_NO_BLANK = r'(?:[^"“”\n]|\n(?!\s*\n))'
QUOTE_PATTERNS = [
    re.compile(rf'"({_NO_BLANK}{{8,400}}?)"'),
    re.compile(rf'“({_NO_BLANK}{{8,400}}?)”'),
    re.compile(r'「((?:[^」\n]|\n(?!\s*\n)){4,400}?)」'),
    re.compile(r'『((?:[^』\n]|\n(?!\s*\n)){4,400}?)』'),
    re.compile(r'^>\s?([^\n]{12,400})', re.M),   # markdown blockquote
]

CITATION_PATTERNS = [
    re.compile(r'\[\d{1,3}(?:\s*[,–-]\s*\d{1,3})*\]'),          # [12] [3-5]
    re.compile(r'\((?:[A-Z][A-Za-z\'’\-]+(?:\s+(?:et\s+al\.?|and|&)\s*'
               r'[A-Za-z\'’\-]*)*),?\s*\d{4}[a-z]?\)'),          # (Smith, 2020)
    re.compile(r'\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+\b'),        # DOI
    re.compile(r'\barXiv:\s?\d{4}\.\d{4,5}(?:v\d+)?\b', re.I),
    re.compile(r'https?://[^\s<>"\')]+'),
    re.compile(r'\b(?:ISO|IEC|IEEE|RFC|ANSI|JIS|EN)\s?[-/]?\s?\d{2,6}'
               r'(?:[-:]\d{1,4})*\b'),
    re.compile(r'\b\d{1,3}\s*(?:CFR|U\.?S\.?C\.?)\s*§?\s*\d+(?:\.\d+)*\b'),
    re.compile(r'\bNo\.\s?\d{2,}[-\d]*\b'),
]

# A number is worth checking when it carries a unit, a symbol, a decimal
# point, a thousands separator, or is simply long. Bare "3" is not.
NUMBER_PATTERN = re.compile(
    r'(?<![\w.])'
    r'(?:[$€£¥￥]\s?\d[\d,]*(?:\.\d+)?'                     # currency-leading
    r'|\d[\d,]*\.\d+'                                       # decimal
    r'|\d{1,3}(?:,\d{3})+'                                  # grouped
    r'|\d{3,}'                                              # long integer
    r'|\d+(?:\.\d+)?\s?%'                                   # percentage
    r'|\d+(?:\.\d+)?\s?(?:[kKmMgGtT]?(?:B|Hz|W|V|A|Ω|F|s|m|g|bps|LUT|px)'
    r'|hours?|days?|weeks?|months?|years?|minutes?|seconds?'
    r'|million|billion|thousand'
    r'|万|億|兆|円|ドル|件|人|年|ヶ月|か月|時間|分|秒)'      # unit-bearing
    r')'
    r'(?![\w])'
)

# Proper nouns: capitalised runs (Latin), katakana runs, ALLCAPS acronyms.
ENTITY_PATTERNS = [
    re.compile(r'\b(?:[A-Z][a-z\'’\-]{2,}\s+){0,3}[A-Z][a-z\'’\-]{2,}\b'),
    re.compile(r'\b[A-Z]{3,8}\b'),
    re.compile(r'[ァ-ヴー]{3,}'),
]

SENTENCE_SPLIT = re.compile(r'(?<=[.!?。！？])\s+|\n{2,}')

# Words that look like entities but carry no factual weight.
ENTITY_STOP = {
    "the", "this", "that", "these", "those", "there", "then", "thus",
    "however", "therefore", "note", "warning", "caution", "example",
    "summary", "conclusion", "introduction", "overview", "figure", "table",
    "section", "chapter", "appendix", "abstract", "references",
    "and", "but", "for", "with", "from", "into", "about",
    "ai", "llm", "api", "pdf", "csv", "url", "http", "https", "id", "ok",
}


_LATIN_WORD = re.compile(r"^[A-Za-z][A-Za-z'’\-]*$")
_SENT_END = re.compile(r'[.!?:;）)\]】。！？]\s*$')


def _is_latin_word(tok: str) -> bool:
    return bool(_LATIN_WORD.match(tok))


def _sentence_initial(text: str, start: int) -> bool:
    """True when the token sits at the start of the text, a line, a list item
    or a sentence — i.e. where capitalisation carries no information."""
    before = text[:start]
    if not before.strip():
        return True
    tail = before.rstrip(" \t")
    if tail.endswith("\n") or not tail:
        return True
    if re.search(r'(?:^|\n)\s*(?:[-*+•]|\d+[.)])\s*$', tail):
        return True
    return bool(_SENT_END.search(before))


def _dedupe(claims: list[Claim]) -> list[Claim]:
    seen: set[tuple[str, str]] = set()
    out: list[Claim] = []
    for c in claims:
        key = (c.kind.value, c.text.strip().casefold())
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def _covered(span: tuple[int, int], spans: list[tuple[int, int]]) -> bool:
    s, e = span
    return any(a <= s and e <= b for a, b in spans)


def extract(text: str, *, kinds: set[Kind] | None = None,
            min_sentence_words: int = 6) -> list[Claim]:
    """Pull checkable units out of `text`, longest-first, without overlap
    between a quotation and the tokens inside it."""
    kinds = kinds or {Kind.QUOTE, Kind.NUMBER, Kind.CITATION, Kind.ENTITY}
    claims: list[Claim] = []
    quote_spans: list[tuple[int, int]] = []

    if Kind.QUOTE in kinds:
        for pat in QUOTE_PATTERNS:
            for m in pat.finditer(text):
                inner = m.group(1).strip()
                if len(inner) < 4:
                    continue
                claims.append(Claim(Kind.QUOTE, inner, m.start(1), m.end(1), text))
                quote_spans.append((m.start(), m.end()))

    if Kind.CITATION in kinds:
        for pat in CITATION_PATTERNS:
            for m in pat.finditer(text):
                claims.append(Claim(Kind.CITATION, m.group(0).strip(),
                                    m.start(), m.end(), text))

    if Kind.NUMBER in kinds:
        for m in NUMBER_PATTERN.finditer(text):
            if _covered((m.start(), m.end()), quote_spans):
                continue
            claims.append(Claim(Kind.NUMBER, m.group(0).strip(),
                                m.start(), m.end(), text))

    if Kind.ENTITY in kinds:
        for pat in ENTITY_PATTERNS:
            for m in pat.finditer(text):
                tok, start = m.group(0).strip(), m.start()
                # "The Ranbaxy settlement" — the article is not part of the name.
                art = re.match(r'^(The|A|An)\s+', tok)
                if art:
                    start += art.end()
                    tok = tok[art.end():]
                if tok.casefold() in ENTITY_STOP or len(tok) < 3:
                    continue
                if _covered((start, m.end()), quote_spans):
                    continue
                # A lone capitalised word at the start of a sentence may be
                # capitalised by position, not because it is a name. Skipping
                # it costs a little recall and removes most false alarms.
                if (_is_latin_word(tok) and " " not in tok
                        and not tok.isupper() and _sentence_initial(text, start)):
                    continue
                claims.append(Claim(Kind.ENTITY, tok, start, m.end(), text))

    if Kind.SENTENCE in kinds:
        pos = 0
        for part in SENTENCE_SPLIT.split(text):
            if not part:
                continue
            start = text.find(part, pos)
            pos = start + len(part) if start >= 0 else pos
            if len(part.split()) >= min_sentence_words or len(part) >= 24:
                claims.append(Claim(Kind.SENTENCE, part.strip(),
                                    max(start, 0), max(start, 0) + len(part), text))

    return _dedupe(claims)
