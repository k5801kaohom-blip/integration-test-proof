---
name: integration-test-proof
description: 觸發詞：整合測試、端到端測試、證明有效、負向控制、注入缺陷、測試兩個技能、證明機制有效、證據報告、流程真的有效嗎。Prove that a composed pipeline actually holds, by running a negative control instead of a clean run. Use when asked to integration-test or end-to-end test two or more tools or skills together, when asked to demonstrate or provide evidence that a mechanism works, when building a demo that must prove a safeguard fires, or when a deliverable needs both structural and visual confirmation. Covers fault injection, before/after content fingerprinting, evidence packs, and honest reporting of MISSED and DAMAGED outcomes.
metadata:
  alias_zh-TW: 整合測試證明
  short_alias_zh-TW: 整合測試
  keywords_zh-TW: 整合測試、整合測試證明、端到端測試、證明有效、負向控制、注入缺陷、測試兩個技能、證明機制有效、證據報告、流程真的有效嗎
---

# Integration Test Proof

When you combine tools into a pipeline, a run that completes without errors proves almost
nothing. It shows the pipeline did not crash. It says nothing about whether the safeguard in
the middle can detect anything, because nothing was there to detect.

**A detector that never fires is indistinguishable from a detector that is not wired up.**

This skill exists because that distinction caused real damage. A deck was generated, inspected
page by page, rendered correctly, and delivered — and the recipient's PowerPoint refused it.
Every check that had been run was a clean run over a file whose only defect lived at the XML
level, where no clean run could have surfaced it.

## When to use

- Asked to integration-test, end-to-end test, or "run a full test of" two or more tools or
  skills together.
- Asked to demonstrate, prove, or show evidence that a mechanism, guard, or validation works.
- Building a demo whose point is that a safeguard catches something.
- A deliverable needs both structural confirmation and visual confirmation before release.
- Two skills interact and you need to know the handoff actually holds.

Do not use this to replace unit tests. It proves a *chain* behaves on a *realistic fault*; it is
not a substitute for testing each stage in isolation.

## The core move: inject the fault

Never present a clean run as proof. Introduce the fault the mechanism exists to catch, then
assert the whole chain responds.

| Stage | Assertion | Failure means |
| --- | --- | --- |
| Baseline | Deliverable passes before anything is touched | It was already broken — report that first |
| Inject | A realistic fault lands in a copy | Nothing was proven |
| Detect | The mechanism **rejects** the faulted copy | The headline finding: the guard is not exercising the fault |
| Recover | The repair stage produces a new artifact | The recovery path is broken |
| Re-detect | The recovered artifact **passes** | The repair produced something still invalid |
| Content | Page, media, and text counts unchanged | Valid but lossy is still a failed delivery |

Stages 4–6 matter as much as stage 3. A repair that emits an invalid file, or a valid file with
half the slides, is worse than no repair, because it looks like success.

The content check compares the **recovered** copy against the **faulted** copy, not against the
pristine deliverable — the injector's own save can normalise the package (unused media, part
ordering), and blaming the repair for that would produce false `DAMAGED` verdicts. The evidence
pack records `content_original`, `content_faulted`, and `content_recovered` separately so the
distinction is auditable.

## Running it

```bash
# built-in fault for Office deliverables
python scripts/negative_control.py deck.pptx --fault ooxml_duplicate_latin --json proof.json

# custom injector and detector for anything else
python scripts/negative_control.py artifact.bin \
  --fault-cmd "python inject.py {file} {out}" \
  --detect   "python check.py {file}" \
  --repair   "python fix.py {file} {out}" \
  --json proof.json
```

The detector must exit **non-zero on a faulted input** and **zero on a sound one**. Omit
`--repair` to test detection only — the outcome is then reported as `DETECTED`, a narrower
claim, and the report says so.

For an Office deliverable the harness finds the validator and repairer of the
`ooxml-integrity-check` skill on its own. For anything else, pass your own `--detect` and
`--repair` commands. The faulted and recovered copies are **kept by default**, because they are
the evidence; pass `--discard-intermediates` to clean them up after a successful run.

| Outcome | Meaning | Action |
| --- | --- | --- |
| `PROVEN` | Fault caught, recovered, content preserved | Safe to claim the chain works |
| `DETECTED` | Fault caught; recovery not tested | Claim detection only, explicitly |
| `MISSED` | The guard did not fire | Report as a real finding; do not claim it works |
| `DAMAGED` | Recovery produced an invalid or lossy result | The recovery path is the defect |
| `BASELINE_BROKEN` | Deliverable was already invalid | Lead with this |
| `INCONCLUSIVE` | Fault could not be injected | Nothing was proven |

Exit codes: `0` for `PROVEN`/`DETECTED`, `1` for `MISSED`/`DAMAGED`/`BASELINE_BROKEN`,
`2` for `INCONCLUSIVE` or usage errors. A non-zero exit is a finding about the pipeline, not a
script failure — read which stage failed before reacting.

## Built-in faults

Both reproduce real generator bugs rather than synthetic corruption.

| Recipe | Injects | Caught by |
| --- | --- | --- |
| `ooxml_duplicate_latin` | A second `<a:latin>` inside a heading's `<a:rPr>` | Duplicate singleton children |
| `ooxml_child_order` | `<a:cs>` moved before `<a:latin>` | Child element order |

Both seed a properly-formed text run first, because a pure image-mode deck has no runs to
corrupt — mirroring how headings are really added to generated slides.

Read `references/fault-recipes.md` for how to choose a fault, per-format candidates, and how to
write a custom injector.

## Confirm the visuals separately

Structural validity and visual correctness are independent claims. Capture both, and keep them
labelled apart:

```bash
python scripts/render_check.py deck.pptx -o proof/render_check.jpg --keep-pages proof/pages
```

Then inspect the contact sheet. Never let a rendered image stand in for a validity claim, and
never let a validity pass stand in for having looked at the output.

## Report honestly

Lead with the outcome, then the evidence, then the limitation. Name the fault you injected, so
the claim is bounded to that fault class.

> Injecting a duplicated singleton element proves the gate catches *that*. It does not prove
> the gate catches every possible defect.

Rules that are not negotiable:

- Never describe a stage you did not run as if you had.
- Never present a clean run as proof that a mechanism works.
- Never report a repair you did not re-validate.
- On `MISSED`, report it as a finding about the pipeline. Do not soften it into a pass.
- Keep the fault class explicit in any "it works" claim.

Read `references/proof-principles.md` for the full evidence hierarchy and the common
self-deceptions to avoid.

## Bundled resources

- `scripts/negative_control.py` — the negative-control harness: baseline, inject, detect,
  recover, re-detect, content check, with a JSON evidence pack.
- `scripts/render_check.py` — render an Office file or an image set into one ordered contact
  sheet for visual review.
- `references/proof-principles.md` — why a clean run proves nothing, what counts as evidence,
  the evidence pack, honest reporting, common self-deceptions.
- `references/fault-recipes.md` — choosing a fault, per-format candidates, custom injectors,
  keeping injections realistic.
- `templates/proof_report.example.json` — shape of the JSON evidence pack.

Pairs with `office-delivery-gate` (the guard being proven) and `ooxml-integrity-check` (the
validator and repairer). The harness locates those automatically when present, or takes
explicit `--detect` / `--repair` commands for any other pipeline.
