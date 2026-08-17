"""Source document loading and normalisation.

Zero required dependencies. PDF support is optional and degrades loudly
rather than silently: if a PDF cannot be read, the file is reported as
unreadable instead of being treated as empty (an empty source would make
every claim look fabricated).
"""

from __future__ import annotations

import re
import shutil
import subprocess
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".rst", ".csv", ".tsv",
                 ".json", ".yaml", ".yml", ".html", ".htm", ".xml",
                 ".py", ".js", ".ts", ".java", ".c", ".h", ".cpp", ".go",
                 ".rs", ".sql", ".sh", ".v", ".sv", ".vhd"}
PDF_SUFFIXES = {".pdf"}


class SourceError(Exception):
    pass


# ---------------------------------------------------------------- normalise

_WS = re.compile(r"[ \t　]+")
_NL = re.compile(r"\n{2,}")
# Typographic variants that documents and model output disagree about.
_FOLD = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "‐": "-", "‑": "-", "‒": "-", "–": "-",
    "—": "-", "―": "-", "−": "-", "－": "-",
    " ": " ", " ": " ", " ": " ", "​": "",
    "﻿": "", "­": "",
}


def normalise(text: str, *, fold_case: bool = True) -> str:
    """Fold the differences that do not change meaning.

    NFKC, unify quote/dash variants, collapse whitespace, optionally casefold.
    Deliberately does NOT stem, lemmatise or translate: this tool reports
    whether a string is present, not whether a paraphrase is faithful.
    """
    text = unicodedata.normalize("NFKC", text)
    for a, b in _FOLD.items():
        text = text.replace(a, b)
    text = _WS.sub(" ", text)
    text = _NL.sub("\n\n", text)
    if fold_case:
        text = text.casefold()
    return text.strip()


def squeeze(text: str) -> str:
    """Aggressive form used as a last-resort fallback: drop all whitespace
    and punctuation so that line-wrapped PDF text still matches."""
    return re.sub(r"[^\w]", "", normalise(text))


# ---------------------------------------------------------------- loading


@dataclass
class Source:
    path: Path
    raw: str
    normalised: str = ""
    squeezed: str = ""
    line_offsets: list[int] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.normalised = normalise(self.raw)
        self.squeezed = squeeze(self.raw)
        off, pos = [], 0
        for line in self.raw.splitlines(keepends=True):
            off.append(pos)
            pos += len(line)
        self.line_offsets = off

    def line_of(self, char_index: int) -> int:
        """1-based line number for a character offset into `raw`."""
        lo, hi = 0, len(self.line_offsets)
        while lo < hi:
            mid = (lo + hi) // 2
            if self.line_offsets[mid] <= char_index:
                lo = mid + 1
            else:
                hi = mid
        return max(1, lo)


def pdf_to_text(path: Path) -> str:
    """Try pdftotext first (fast, keeps layout), then pdfplumber."""
    exe = shutil.which("pdftotext")
    if exe:
        proc = subprocess.run([exe, "-layout", str(path), "-"],
                              capture_output=True, text=True)
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout
    try:
        import pdfplumber  # type: ignore
    except ImportError as exc:
        raise SourceError(
            f"{path.name}: cannot read PDF. Install poppler-utils "
            f"(provides pdftotext) or `pip install grounded[pdf]`."
        ) from exc
    out = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            out.append(page.extract_text() or "")
    text = "\n".join(out)
    if not text.strip():
        raise SourceError(
            f"{path.name}: no extractable text. It may be a scanned image; "
            f"OCR it first. Refusing to treat it as empty."
        )
    return text


def load_one(path: str | Path) -> Source:
    path = Path(path)
    if not path.exists():
        raise SourceError(f"{path}: not found")
    if path.is_dir():
        raise SourceError(f"{path}: is a directory")
    suffix = path.suffix.lower()
    if suffix in PDF_SUFFIXES:
        raw = pdf_to_text(path)
    else:
        if suffix and suffix not in TEXT_SUFFIXES:
            # Unknown extension: try as text, but say so if it looks binary.
            head = path.read_bytes()[:2048]
            if b"\x00" in head:
                raise SourceError(f"{path.name}: looks binary, not text")
        raw = path.read_text(encoding="utf-8", errors="replace")
    if not raw.strip():
        raise SourceError(f"{path.name}: file is empty")
    return Source(path=path, raw=raw)


def load(paths: list[str | Path], *, recursive: bool = True) -> list[Source]:
    """Load every given file; expand directories.

    Any file that cannot be read raises. Silently skipping an unreadable
    source would inflate the fabrication count, which is the one failure
    mode this tool must not have.
    """
    expanded: list[Path] = []
    for p in paths:
        p = Path(p)
        if p.is_dir():
            it = p.rglob("*") if recursive else p.glob("*")
            expanded.extend(sorted(f for f in it if f.is_file()
                                   and f.suffix.lower() in TEXT_SUFFIXES | PDF_SUFFIXES))
        else:
            expanded.append(p)
    if not expanded:
        raise SourceError("no source files found")
    return [load_one(p) for p in expanded]
