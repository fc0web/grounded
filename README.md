# grounded

**Check that generated text is actually supported by its sources.**

Deterministic. Offline. No model involved in the checking.

```bash
grounded check answer.md --source contract.pdf --source notes/
```

```
EXACT CHECKS   (present in source, or fabricated)
  checked   31
  grounded  21
  NOT FOUND 10
  rate      67.7%

NOT FOUND IN ANY SOURCE
  ✗ [quote] audit trail review shall be completed within 24 hours of batch manufacture
  ✗ [citation] (Whitfield & Osei, 2024)
  ✗ [citation] arXiv:2401.99887
  ✗ [number] 2.3
  ✗ [entity] Whitfield

FAIL  10 claim(s) are not in any source.
```

Exit code 1. Usable in CI, in a pre-commit hook, or by a model checking
its own draft before answering.

---

## Why this and not an AI fact-checker

A model grading its own output can be wrong in the same direction twice.

`grounded` does not reason about your text. It takes the things whose
absence is *evidence of fabrication* — quotations, figures, citations,
proper nouns — and looks each one up literally in the documents you point
it at. Present, or not present. Nothing to hallucinate.

That is a narrower promise than "detects hallucinations", and it is a
promise the tool can actually keep.

---

## Install

```bash
pip install grounded                 # core, zero dependencies
pip install "grounded[pdf]"          # + PDF sources
pip install "grounded[mcp]"          # + MCP server
```

Python 3.10+. No network access, no API key, no model download, no GPU.
Your documents never leave the machine.

---

## Use

### Command line

```bash
# check a file against one source
grounded check answer.md -s manual.pdf

# several sources, including a whole directory
grounded check answer.md -s spec.pdf -s docs/ -s notes.md

# from a pipe
cat draft.txt | grounded check - -s reference.pdf

# machine-readable
grounded check answer.md -s manual.pdf --json

# only check quotations and citations
grounded check answer.md -s manual.pdf --kind quote --kind citation

# also run the advisory sentence tier
grounded check answer.md -s manual.pdf --sentences
```

### Python

```python
from grounded import check

result = check(answer_text, ["manual.pdf", "notes/"])

if not result.passed:
    for f in result.failures:
        print(f"{f.claim.kind.value}: {f.claim.text}")
```

### As an MCP server

So a model can verify its own draft *before* it answers.

```json
{
  "mcpServers": {
    "grounded": { "command": "grounded-mcp" }
  }
}
```

Tools exposed:

| tool | what it does |
|---|---|
| `verify_against_sources` | check a whole draft; returns everything not found |
| `check_quote` | confirm one quotation before attributing it |
| `verify_audit_log` | check a run log has not been altered |

---

## What is checked

Five kinds of claim, in two tiers that are kept strictly apart.

### Exact tier — this is the product

| kind | example | rule |
|---|---|---|
| `quote` | `"shall not obscure previously recorded information"` | must appear verbatim |
| `number` | `$2.3 million`, `24 hours`, `15%`, `2,048` | must appear |
| `citation` | `[12]`, `(Smith, 2020)`, `arXiv:2401.99887`, DOIs, URLs, `21 CFR 11.10` | must appear |
| `entity` | `Ranbaxy`, `MHRA`, `ISO/IEC 17025` | must appear |

Matching folds case, Unicode width, curly quotes, dash variants and
whitespace — a quotation broken across two lines by wrapping still matches.
Trivial numbers (`3 items`) are ignored; a number is only checked when it
carries a unit, a decimal point, a separator, or is long enough to be a
figure someone could get wrong.

### Heuristic tier — advisory only, off by default

`sentence` claims are scored by distinctive-token overlap with the sources.
A low score **may** mean fabrication, or **may** mean a good paraphrase.
These never cause a failure unless you ask for them, and they are reported
in a separate section so they cannot be mistaken for the exact results.

---

## What this does NOT do

Stated plainly, because a verification tool that overstates itself is worse
than none.

- **It does not judge whether a paraphrase is faithful.** "Sales rose" when
  the source says "sales fell" will pass if the words are present elsewhere.
- **It does not check reasoning or arithmetic.** A correctly-quoted figure
  used in a wrong conclusion passes.
- **It does not know if your sources are true.** It checks agreement with
  the documents you supply, nothing more.
- **It is not a plagiarism detector.** The direction is the opposite: here,
  matching the source is the *good* outcome.
- **It cannot read scanned PDFs.** OCR them first. A page with no
  extractable text raises an error rather than being treated as empty —
  an empty source would make every claim look fabricated, and that is the
  one failure this tool must not have.

---

## Audit log

Optional. Each run can append one entry to a hash-chained, append-only file.
Altering any past entry breaks the chain at a detectable position.

```bash
grounded check answer.md -s manual.pdf --log .grounded/audit.jsonl \
  --at "2026-08-17T14:03:00+09:00"

grounded audit --log .grounded/audit.jsonl -v
```

```
entries : 3
status  : chain intact
```

Timestamps are supplied by the caller rather than read from the clock, so
runs are reproducible and testable.

This is tamper **evidence**, not tamper **resistance**. Someone who can
rewrite the whole file can rebuild a consistent chain. It answers "was this
record altered afterwards" for an ordinary reviewer, not "can a determined
attacker forge it".

---

## Exit codes

| code | meaning |
|---|---|
| `0` | every exact claim was found (or `--no-fail` was given) |
| `1` | at least one claim is not in any source |
| `2` | a source could not be read — the check did **not** run |

Code `2` is deliberately distinct. A missing source must never be reported
as "everything is fabricated".

---

## Try it

The repository ships a worked example: one source document, one honest
summary of it, one summary with fabrications inserted.

```bash
grounded check examples/answer_grounded.md   -s examples/source.md   # PASS, 40/40
grounded check examples/answer_fabricated.md -s examples/source.md   # FAIL, 10 found
```

Every one of the ten is a genuine fabrication, and the honest summary
produces no false alarms. Those two properties are what the test suite
exists to protect.

---

## Development

```bash
git clone https://github.com/fc0web/grounded
cd grounded
pip install -e ".[dev]"
pytest
```

Contributions welcome, especially:

- more citation formats (legal, medical, non-English academic)
- language coverage beyond English and Japanese
- false-positive reports — a claim wrongly reported as fabricated is the
  most serious bug this tool can have

---

## License

MIT.

日本語の説明は [README.ja.md](README.ja.md) にあります。
