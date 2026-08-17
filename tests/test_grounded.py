"""Tests. The two that matter most:

  * a fabricated quotation must be caught   (false negatives are the danger)
  * an honest summary must pass cleanly     (false positives destroy trust)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from grounded import Kind, check, extract                      # noqa: E402
from grounded.audit import AuditLog                            # noqa: E402
from grounded.sources import SourceError, normalise, squeeze   # noqa: E402

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
SOURCE = EXAMPLES / "source.md"


# ------------------------------------------------------------- end to end

def test_honest_answer_passes_with_no_false_positives():
    result = check((EXAMPLES / "answer_grounded.md").read_text(encoding="utf-8"),
                   [str(SOURCE)])
    assert result.passed, [f.claim.text for f in result.failures]
    assert result.rate == 1.0
    assert len(result.exact) > 20          # it really did check things


def test_fabricated_answer_is_caught():
    result = check((EXAMPLES / "answer_fabricated.md").read_text(encoding="utf-8"),
                   [str(SOURCE)])
    assert not result.passed
    found = {f.claim.text for f in result.failures}
    # the invented quotation is the highest-value catch
    assert any("24 hours of batch" in t for t in found)
    # invented citations
    assert any("Whitfield" in t for t in found)
    assert any("arXiv:2401.99887" in t for t in found)


def test_every_failure_is_a_real_fabrication():
    """No false positives in the fabricated example either: each reported
    claim must genuinely be absent from the source."""
    src = normalise(SOURCE.read_text(encoding="utf-8"))
    src_sq = squeeze(SOURCE.read_text(encoding="utf-8"))
    result = check((EXAMPLES / "answer_fabricated.md").read_text(encoding="utf-8"),
                   [str(SOURCE)])
    for f in result.failures:
        assert normalise(f.claim.text) not in src, f.claim.text
        assert squeeze(f.claim.text) not in src_sq, f.claim.text


# --------------------------------------------------------------- extraction

def test_quote_spanning_a_line_break_is_extracted():
    text = 'The report says "the audit trail shall be enabled\nand locked at all times".'
    quotes = [c.text for c in extract(text, kinds={Kind.QUOTE})]
    assert any("locked at all times" in q for q in quotes)


def test_quote_does_not_span_a_paragraph_break():
    text = 'He said "one thing\n\nand later " something else'
    quotes = [c.text for c in extract(text, kinds={Kind.QUOTE})]
    assert not any("something else" in q for q in quotes)


def test_sentence_initial_word_is_not_treated_as_a_name():
    ents = {c.text for c in extract("Regulators agree. Notably, this holds.",
                                    kinds={Kind.ENTITY})}
    assert "Regulators" not in ents
    assert "Notably" not in ents


def test_midsentence_name_is_treated_as_a_name():
    ents = {c.text for c in extract("a study by Whitfield and Osei found",
                                    kinds={Kind.ENTITY})}
    assert "Whitfield" in ents


def test_leading_article_is_stripped():
    ents = {c.text for c in extract("The Ranbaxy settlement was large.",
                                    kinds={Kind.ENTITY})}
    assert "The Ranbaxy" not in ents


def test_trivial_numbers_are_ignored():
    nums = {c.text for c in extract("There are 3 items and 4 boxes.",
                                    kinds={Kind.NUMBER})}
    assert nums == set()


def test_significant_numbers_are_checked():
    nums = {c.text for c in extract("It cost $2.3 million over 24 hours in 2024.",
                                    kinds={Kind.NUMBER})}
    assert any("2.3" in n for n in nums)
    assert any("2024" in n for n in nums)


# ------------------------------------------------------------- source safety

def test_missing_source_raises_rather_than_reporting_everything_fabricated():
    with pytest.raises(SourceError):
        check("anything at all", ["/nonexistent/path.md"])


def test_empty_source_raises(tmp_path):
    empty = tmp_path / "empty.md"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(SourceError):
        check("anything at all", [str(empty)])


def test_matching_is_case_and_whitespace_insensitive(tmp_path):
    src = tmp_path / "s.md"
    src.write_text("The Audit   Trail must be enabled.", encoding="utf-8")
    result = check('Rule: "the audit trail must be enabled"', [str(src)])
    assert result.passed


# ------------------------------------------------------------------- audit

def test_audit_chain_detects_tampering(tmp_path):
    log = AuditLog(tmp_path / "audit.jsonl")
    for i in range(3):
        log.append({"run": i, "passed": True}, at="2026-08-17T00:00:00+09:00")
    intact, bad, _ = log.verify()
    assert intact and bad is None

    lines = log.path.read_text(encoding="utf-8").splitlines()
    lines[1] = lines[1].replace('"run": 1', '"run": 999')
    log.path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    intact, bad, message = log.verify()
    assert not intact
    assert bad == 1
    assert "seq 1" in message


def test_audit_appends_do_not_rewrite_history(tmp_path):
    log = AuditLog(tmp_path / "a.jsonl")
    first = log.append({"n": 1}, at="t0")
    log.append({"n": 2}, at="t1")
    assert log.entries()[0] == first


# --------------------------------------------------------------------- cli

def _cli(*args: str) -> subprocess.CompletedProcess:
    root = Path(__file__).resolve().parents[1]
    env = {"PYTHONPATH": str(root / "src"), "PATH": "/usr/bin:/bin"}
    return subprocess.run([sys.executable, "-m", "grounded.cli", *args],
                          capture_output=True, text=True, cwd=root, env=env)


def test_cli_exit_code_is_one_on_fabrication():
    p = _cli("check", "examples/answer_fabricated.md", "-s", "examples/source.md",
             "--no-colour")
    assert p.returncode == 1


def test_cli_exit_code_is_zero_when_grounded():
    p = _cli("check", "examples/answer_grounded.md", "-s", "examples/source.md",
             "--no-colour")
    assert p.returncode == 0


def test_cli_json_is_parseable():
    import json
    p = _cli("check", "examples/answer_grounded.md", "-s", "examples/source.md",
             "--json")
    data = json.loads(p.stdout)
    assert data["passed"] is True
    assert data["exact"]["not_found"] == 0
