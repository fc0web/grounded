"""Tamper-evident record of verification runs.

Every run appends one entry to an append-only file. Each entry carries the
SHA-256 of the previous entry, so altering any past record breaks the chain
at a detectable position.

This is tamper *evidence*, not tamper *resistance*: someone who can rewrite
the whole file can rebuild a consistent chain. It answers "was this record
altered after the fact" for an ordinary reviewer, not "can a determined
attacker forge it".
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

GENESIS = "0" * 64


def _digest(body: dict) -> str:
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


@dataclass
class AuditLog:
    path: Path

    def __post_init__(self) -> None:
        self.path = Path(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------- read
    def entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                out.append(json.loads(line))
        return out

    def head(self) -> str:
        entries = self.entries()
        return entries[-1]["hash"] if entries else GENESIS

    # ------------------------------------------------------------ write
    def append(self, payload: dict, *, at: str) -> dict:
        """`at` is supplied by the caller, never read from the clock here,
        so that runs are reproducible and testable."""
        body = {
            "seq": len(self.entries()),
            "at": at,
            "payload": payload,
            "prev": self.head(),
        }
        body["hash"] = _digest(body)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(body, ensure_ascii=False, sort_keys=True) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        return body

    # ----------------------------------------------------------- verify
    def verify(self) -> tuple[bool, int | None, str]:
        """Returns (intact, first_bad_seq, message)."""
        prev = GENESIS
        for i, entry in enumerate(self.entries()):
            if entry.get("seq") != i:
                return False, i, f"sequence number out of order at index {i}"
            if entry.get("prev") != prev:
                return False, i, f"broken link at seq {i}"
            body = {k: entry[k] for k in ("seq", "at", "payload", "prev")}
            if _digest(body) != entry.get("hash"):
                return False, i, f"content altered at seq {i}"
            prev = entry["hash"]
        return True, None, "chain intact"
