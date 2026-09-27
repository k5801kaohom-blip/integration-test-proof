# Fault Recipes

Read this when choosing what fault to inject, when the built-in recipes do not fit your
deliverable's format, or when a custom injector is needed.

## Contents

1. Choosing a fault
2. Built-in recipes
3. Writing a custom injector
4. Faults worth injecting per format
5. Keeping the injection realistic

## 1. Choosing a fault

Inject the fault the mechanism **exists to catch**, not one that is convenient to write. A gate
proven against a trivial fault is proven against that fault only.

Ask: what has actually gone wrong before, or what is most likely to go wrong given how this
artifact is produced? If the artifact is produced by scripted XML assembly, the likely faults
are structural: duplicated elements, wrong child order, missing parts, broken references.

State which fault class you tested when reporting. "The gate caught a duplicated singleton
element" is an honest, bounded claim. "The gate works" is not.

## 2. Built-in recipes

Both are real-world generator bugs, not synthetic corruption.

| Recipe | What it does | Caught by |
| --- | --- | --- |
| `ooxml_duplicate_latin` | Adds a correctly-formed heading to each slide, then inserts a second `<a:latin>` inside its `<a:rPr>` | Duplicate singleton children |
| `ooxml_child_order` | Adds a heading, then moves `<a:cs>` before `<a:latin>` | Child element order |

Both first seed a proper text run, because a pure image-mode deck has no runs to corrupt. This
mirrors how headings are really added to generated slides.

```bash
python scripts/negative_control.py deck.pptx --fault ooxml_duplicate_latin
python scripts/negative_control.py deck.pptx --fault ooxml_child_order
```

The duplicate `a:latin` recipe reproduces the defect that produced an unopenable deck:

```python
run.font.name = "Microsoft JhengHei"   # already creates <a:latin> inside <a:rPr>
rPr = run._r.get_or_add_rPr()
rPr.append(rPr.makeelement(f"{{{A_NS}}}latin", {"typeface": FONT}))   # BUG: second one
```

Result: `<a:latin/><a:latin/><a:ea/><a:cs/>`. Each of `a:latin`, `a:ea`, and `a:cs` may appear
at most once, in that order. PowerPoint calls the file corrupt; LibreOffice renders it fine.

## 3. Writing a custom injector

Pass a shell command with `{file}` and `{out}` placeholders. It must write the faulted copy to
`{out}` and exit non-zero if it could not:

```bash
python scripts/negative_control.py report.docx \
  --fault-cmd "python inject_missing_relationship.py {file} {out}" \
  --detect "python /path/to/validate_ooxml.py {file} --quiet" \
  --repair "python /path/to/repair_ooxml.py {file} -o {out}"
```

The detector must exit non-zero on a faulted file and zero on a sound one. If it uses the
opposite convention, wrap it so the contract holds.

To test detection only, pass an empty `--repair ""` — this is treated as "no recovery stage",
and the outcome is reported as `DETECTED` rather than being silently repaired.

## 3b. Non-Office pipelines

The same harness proves any chain, not just Office files. Define the contract in terms of exit
codes, and the recipes become irrelevant:

| Pipeline | Injectable fault | Detector |
| --- | --- | --- |
| Data export | Drop a required column | Schema validator |
| API client | Return a malformed payload | Response validator |
| Archive builder | Remove a file still listed in a manifest | Manifest checker |
| Image pipeline | Corrupt one frame's header | Decoder or dimension check |
| Content generator | Delete one entry from an index | Index reconciliation |

Write the injector to take `{file}` and `{out}`, then pass your own `--detect` and `--repair`.
The baseline, detection, recovery, re-detection, and content stages all still apply — and the
content fingerprint falls back to part and file counts when the format is not OOXML.

## 4. Faults worth injecting per format

| Format | Fault | Mechanism it exercises |
| --- | --- | --- |
| PPTX / DOCX / XLSX | Duplicate singleton child | Schema conformance check |
| PPTX / DOCX / XLSX | Wrong child order | Ordering check |
| Any OOXML | Remove a part still referenced by a relationship | Relationship resolution |
| Any OOXML | Point `r:embed` at a non-existent image | Main document references |
| PPTX | Change `sldSz` to disagree with the layout | Geometry consistency |
| XLSX | Break a sheet's content-type override | Content-type check |
| Generated deck | Delete a slide part but keep it in the presentation list | Part-count reconciliation |
| Any | Truncate a media file | Media decodability |

Prefer faults that a generator could plausibly produce. Corrupting bytes at random tests the
zip reader, not the schema logic, and proves far less.

## 5. Keeping the injection realistic

- **Reproduce a real bug when one exists.** The strongest fault is the one that actually
  caused damage, because no one can argue it does not happen.
- **Do not inject into the original.** Always copy; the deliverable must survive the test.
- **Keep the fault minimal.** One defect, so the detector's response is attributable.
- **Assert the fault landed.** If the injector silently no-ops, the test proves nothing — the
  harness reports this as `INCONCLUSIVE` rather than letting it pass.
- **Record what you injected.** The evidence pack should name the recipe and the count of
  elements touched, so a reader can judge how strong the proof is.
