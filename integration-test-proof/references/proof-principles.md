# Proof Principles

Read this before running an integration test, building a demo that must prove a mechanism,
or writing any claim that a pipeline "works".

## Contents

1. A clean run proves nothing
2. The negative control
3. What counts as evidence
4. The evidence pack
5. Reporting honestly
6. Common self-deceptions

## 1. A clean run proves nothing

Running a mechanism once on a healthy input produces one bit of information: the mechanism
did not crash. It does not show the mechanism can detect anything, because nothing was there
to detect.

> A detector that never fires is indistinguishable from a detector that is not wired up.

This is not theoretical. A deck was generated, inspected page by page, rendered correctly, and
handed over — and the recipient's PowerPoint refused it. Every check performed had been a
clean run over a file whose only defect lived at the XML level, where no clean run could
possibly have surfaced it.

The consequence: **when someone asks you to demonstrate that a mechanism works, a clean run is
not the demonstration.** You must introduce the fault the mechanism exists to catch.

## 2. The negative control

A negative control is the one input the test is *supposed* to reject. For a delivery gate, that
is a file carrying the exact defect the gate exists to catch.

The chain to assert, in order:

| Stage | Assertion | If it fails |
| --- | --- | --- |
| Baseline | The deliverable passes before anything is touched | The deliverable is already broken — report that first |
| Inject | A realistic fault can be introduced | Nothing was proven; fix the injector |
| Detect | The mechanism **rejects** the faulted input | The mechanism is not exercising the fault — the headline finding |
| Recover | The repair stage produces a new artifact | The repair path is broken |
| Re-detect | The recovered artifact **passes** | The repair produced something still invalid |
| Content | Page, media, and text counts are unchanged | Valid but lossy is still a failed delivery |

The fourth and fifth stages matter as much as the third. A repair that outputs an invalid file,
or a valid file with half the slides, is worse than no repair, because it looks like success.

## 3. What counts as evidence

| Artifact | Proves | Does not prove |
| --- | --- | --- |
| Detector exit code on a faulted copy | The detector fires | That the deliverable is sound |
| Detector exit code on a clean copy | Nothing on its own | Anything about detection |
| A rendered image or contact sheet | Pages exist and look right | Structural validity |
| Before/after content counts | Content survived the operation | Structural validity |
| Tolerance of a lenient viewer | Nothing | Anything |

Rendering and structural validity are independent claims. Capture both, and keep them labelled
as different things. Never let a rendered image stand in for a validity claim.

## 4. The evidence pack

Persist the proof as a machine-readable artifact, not a paragraph of prose. One JSON file
recording, per stage, the command semantics, the exit code, and the observed output:

- the deliverable and how the fault was injected
- baseline detector exit code
- detector exit code on the faulted copy, with its error output
- repair exit code and the path of the recovered artifact
- detector exit code on the recovered artifact
- content fingerprint before and after

See `templates/proof_report.example.json` for the shape. A reader must be able to tell, from
the file alone, which stages passed and what the verdict was.

## 5. Reporting honestly

State the outcome, then the evidence, then any limitation.

- **Proven:** name the fault, state it was caught, and state that content was preserved.
- **Detected only:** say explicitly that recovery was not tested, so the claim is narrower.
- **Missed:** this is a finding about the pipeline, not a script error. Report it plainly and
  do not claim the mechanism works.
- **Baseline broken:** the deliverable was already invalid. Lead with that.

Never describe a stage you did not run as if you had. Never present a clean run as proof.
Never report a repair you did not re-validate.

## 6. Common self-deceptions

| Reasoning | Why it is wrong |
| --- | --- |
| "It ran without errors, so the pipeline works." | A no-op also runs without errors. |
| "The output looks correct." | Rendering says nothing about structural validity. |
| "I tested the happy path thoroughly." | The mechanism exists for the unhappy path. |
| "The tool has a self-test, so I do not need to run one." | Run it. Its own author may have shipped it untested. |
| "I injected a fault and it was caught, so we are done." | Confirm recovery *and* that content survived. |
| "The fault I injected was caught, so any fault would be." | True only for faults of that kind. Say which kind you tested. |