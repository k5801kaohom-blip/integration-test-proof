#!/usr/bin/env python3
"""Prove a composed pipeline actually holds, by running a negative control.

A clean run proves nothing. A detector that never fires is indistinguishable from a
detector that is not wired up at all. This harness injects a realistic fault into a
copy of your deliverable and asserts the full chain behaves:

    baseline passes -> fault injected -> detection fires -> recovery runs
                    -> detection passes again -> content preserved

Exit codes
    0   the pipeline caught the fault and recovered without losing content
    1   the pipeline missed the fault, or recovery changed the content
    2   usage or environment error
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

_ZIP_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"
OUTCOME_EXIT = {
    "PROVEN": 0,
    "DETECTED": 0,
    "MISSED": 1,
    "DAMAGED": 1,
    "BASELINE_BROKEN": 1,
    "INCONCLUSIVE": 2,
}


# ------------------------------------------------------------ helper discovery

def _helper_candidates() -> list[Path]:
    import os

    out = []
    env = os.environ.get("OOXML_SKILL_DIR")
    if env:
        out.append(Path(env))
    out += [
        Path("/home/ubuntu/skills/ooxml-integrity-check/scripts"),
        Path(__file__).resolve().parent.parent.parent / "ooxml-integrity-check" / "scripts",
    ]
    return out


def find_helper(name: str) -> Path | None:
    for base in _helper_candidates():
        candidate = base / name
        if candidate.is_file():
            return candidate
    return None


# ------------------------------------------------------------- fault recipes

A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"


def _seed_text_runs(pptx_path: Path, label: str) -> int:
    """Add a correctly-formed text box to each slide.

    Gives the injection something realistic to corrupt, and mirrors how headings are
    actually added to an image-mode deck.
    """
    from pptx import Presentation
    from pptx.util import Inches, Pt

    prs = Presentation(str(pptx_path))
    touched = 0
    for index, slide in enumerate(prs.slides, start=1):
        box = slide.shapes.add_textbox(Inches(0.3), Inches(0.2), Inches(3.5), Inches(0.4))
        frame = box.text_frame
        frame.text = f"{label} {index}"
        run = frame.paragraphs[0].runs[0]
        run.font.size = Pt(12)
        run.font.name = "Microsoft JhengHei"          # creates <a:latin>
        rpr = run._r.get_or_add_rPr()
        for tag in ("ea", "cs"):                       # add the remaining faces, once each
            if rpr.find(f"{{{A_NS}}}{tag}") is None:
                rpr.append(rpr.makeelement(f"{{{A_NS}}}{tag}", {"typeface": "Microsoft JhengHei"}))
        touched += 1
    prs.save(str(pptx_path))
    return touched


def fault_ooxml_duplicate_latin(src: Path, dst: Path) -> dict:
    """Reproduce the bug that produced unopenable decks.

    `run.font.name = "..."` already creates <a:latin>. Appending a second one for the
    East Asian face yields <a:latin/><a:latin/><a:ea/><a:cs/>, which PowerPoint reports
    as corrupt while LibreOffice still renders it perfectly.
    """
    shutil.copy(src, dst)
    from pptx import Presentation

    touched = _seed_text_runs(dst, "injected")
    prs = Presentation(str(dst))
    duplicated = 0
    for slide in prs.slides:
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            for para in shape.text_frame.paragraphs:
                for run in para.runs:
                    rpr = run._r.find(f"{{{A_NS}}}rPr")
                    if rpr is None:
                        continue
                    latin = rpr.find(f"{{{A_NS}}}latin")
                    if latin is None:
                        continue
                    rpr.insert(list(rpr).index(latin) + 1,
                               rpr.makeelement(f"{{{A_NS}}}latin",
                                               {"typeface": latin.get("typeface", "")}))
                    duplicated += 1
    prs.save(str(dst))
    return {"recipe": "ooxml_duplicate_latin", "text_runs_seeded": touched,
            "duplicates_injected": duplicated}


def fault_ooxml_child_order(src: Path, dst: Path) -> dict:
    """Mis-order the font children: <a:cs/> before <a:latin/>.

    Schema requires a:latin, then a:ea, then a:cs. Reordering is a realistic bug from
    naive XML surgery and is caught by a different check than duplication.
    """
    shutil.copy(src, dst)
    from pptx import Presentation

    touched = _seed_text_runs(dst, "misordered")
    prs = Presentation(str(dst))
    swapped = 0
    for slide in prs.slides:
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            for para in shape.text_frame.paragraphs:
                for run in para.runs:
                    rpr = run._r.find(f"{{{A_NS}}}rPr")
                    if rpr is None:
                        continue
                    cs = rpr.find(f"{{{A_NS}}}cs")
                    latin = rpr.find(f"{{{A_NS}}}latin")
                    if cs is None or latin is None:
                        continue
                    rpr.remove(cs)
                    rpr.insert(list(rpr).index(latin), cs)
                    swapped += 1
    prs.save(str(dst))
    return {"recipe": "ooxml_child_order", "text_runs_seeded": touched,
            "elements_misordered": swapped}


RECIPES = {
    "ooxml_duplicate_latin": fault_ooxml_duplicate_latin,
    "ooxml_child_order": fault_ooxml_child_order,
}


# ------------------------------------------------------------------- helpers

def run_stage(template: str, **fields: str) -> tuple[int, str]:
    cmd = template.format(**fields)
    proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


def fingerprint(path: Path) -> dict:
    """Describe the document's content so a recovery cannot silently drop any."""
    fp: dict = {"readable": False}
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            fp["readable"] = True
            fp["parts"] = len(names)
            fp["slides"] = len([n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)])
            fp["sheets"] = len([n for n in names if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)])
            fp["media"] = len([n for n in names
                               if n.startswith(("ppt/media/", "word/media/", "xl/media/"))])
            text_runs = 0
            for name in names:
                if re.fullmatch(r"ppt/slides/slide\d+\.xml", name) or name in (
                    "word/document.xml", "xl/sharedStrings.xml"
                ):
                    blob = z.read(name).decode("utf-8", "ignore")
                    text_runs += len(re.findall(r"<(?:a|w):t\b[^>]*>.*?</(?:a|w):t>", blob, flags=re.S))
            fp["text_runs"] = text_runs
    except (zipfile.BadZipFile, OSError):
        pass
    return fp


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Prove a pipeline holds by injecting a real fault (negative control).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "The detector command must exit NON-ZERO on a faulted file and ZERO on a sound one.\n"
            "Use {file} for the input path and {out} for the recovery output path.\n\n"
            f"built-in fault recipes: {', '.join(sorted(RECIPES))}"
        ),
    )
    ap.add_argument("deliverable", help="the artifact to prove (e.g. a .pptx)")
    ap.add_argument("--fault", default="ooxml_duplicate_latin", choices=sorted(RECIPES),
                    help="built-in fault recipe to inject (default: %(default)s)")
    ap.add_argument("--fault-cmd", default=None,
                    help="custom injection command with {file} and {out}; overrides --fault")
    ap.add_argument("--detect", default=None,
                    help="detector command with {file}; defaults to the ooxml validator")
    ap.add_argument("--repair", default=None,
                    help="recovery command with {file} and {out}; omit to test detection only")
    ap.add_argument("--workdir", default="proof_evidence", help="where to keep evidence")
    ap.add_argument("--json", dest="json_out", default=None, help="write the evidence pack here")
    ap.add_argument("--discard-intermediates", action="store_true",
                    help="delete the faulted and recovered copies after the run "
                         "(they are kept by default, since they are the evidence)")
    args = ap.parse_args()

    deliverable = Path(args.deliverable)
    if not deliverable.is_file():
        print(f"[proof] deliverable not found: {deliverable}", file=sys.stderr)
        return 2

    detect = args.detect
    if detect is None:
        validator = find_helper("validate_ooxml.py")
        if validator is None:
            print("[proof] no --detect given and the ooxml validator was not found.\n"
                  "        Pass --detect, or install the ooxml-integrity-check skill.",
                  file=sys.stderr)
            return 2
        detect = f"{sys.executable} {validator} {{file}} --quiet"

    repair = args.repair
    if repair is None and args.fault in RECIPES:
        repairer = find_helper("repair_ooxml.py")
        if repairer is not None:
            repair = f"{sys.executable} {repairer} {{file}} -o {{out}}"
    if repair is not None and not repair.strip():
        repair = None  # an explicitly empty command means "detection only"

    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    evidence: dict = {
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "deliverable": str(deliverable),
        "fault": args.fault if not args.fault_cmd else "custom",
        "stages": [],
    }

    def record(stage: str, ok: bool | None, detail: str = "") -> None:
        evidence["stages"].append({"stage": stage, "ok": ok, "detail": detail})

    # 1. baseline -----------------------------------------------------------
    print("[proof] 1/6 baseline: the deliverable must be sound to start with")
    rc, out = run_stage(detect, file=str(deliverable))
    baseline_ok = rc == 0
    record("baseline", baseline_ok, f"detector exit={rc}" + (f" | {out}" if out else ""))
    if not baseline_ok:
        print(f"        FAIL  the deliverable already fails detection (exit={rc})")
        print(out)
        evidence["outcome"] = "BASELINE_BROKEN"
        evidence["content_original"] = fingerprint(deliverable)
    else:
        print("        PASS  deliverable is sound")
        evidence["content_original"] = fingerprint(deliverable)

    # 2. inject -------------------------------------------------------------
    faulted = workdir / f"{deliverable.stem}.faulted{deliverable.suffix}"
    if baseline_ok:
        print(f"[proof] 2/6 inject fault: {evidence['fault']}")
        if args.fault_cmd:
            rc_f, out_f = run_stage(args.fault_cmd, file=str(deliverable), out=str(faulted))
            injected = {"custom_cmd": args.fault_cmd, "exit": rc_f}
        else:
            try:
                injected = RECIPES[args.fault](deliverable, faulted)
            except Exception as exc:  # noqa: BLE001 - surface injection problems plainly
                print(f"[proof] injection failed: {exc}", file=sys.stderr)
                return 2
            injected["exit"] = 0
        evidence["injection"] = injected
        ok_inj = faulted.is_file() and injected.get("exit", 0) == 0
        record("inject", ok_inj, json.dumps(injected, ensure_ascii=False))
        print(f"        {'PASS' if ok_inj else 'FAIL'}  {json.dumps(injected, ensure_ascii=False)}")
        if not ok_inj:
            evidence["outcome"] = "INCONCLUSIVE"
            print("[proof] could not produce a faulted copy; nothing was proven.", file=sys.stderr)
            return 2

        # The injection rewrites the package (libraries normalise unused media on save), so the
        # faulted copy - not the pristine deliverable - is the baseline that recovery must
        # preserve. Comparing against the original would blame the repair for the injector's
        # own normalisation.
        evidence["content_faulted"] = fingerprint(faulted)

        # 3. detection must fire -------------------------------------------
        print("[proof] 3/6 negative control: detection must FAIL on the faulted copy")
        rc_d, out_d = run_stage(detect, file=str(faulted))
        caught = rc_d != 0
        record("detect_faulted", caught, f"detector exit={rc_d}" + (f" | {out_d}" if out_d else ""))
        print(f"        {'PASS' if caught else 'FAIL'}  detector exit={rc_d}")
        if not caught:
            print("        The pipeline did not catch the fault. This is a real finding:")
            print("        the detector is not exercising the fault you injected.")
            evidence["outcome"] = "MISSED"
        else:
            evidence["detector_output"] = out_d

    if evidence.get("outcome") == "BASELINE_BROKEN":
        outcome = "BASELINE_BROKEN"
    elif evidence.get("outcome") == "MISSED":
        outcome = "MISSED"
    else:
        outcome = None

    if outcome is None:
        # 4. recovery ------------------------------------------------------
        if repair is None:
            print("[proof] 4/6 recovery: skipped (no --repair given)")
            record("recover", None, "skipped")
            outcome = "DETECTED"
        else:
            print("[proof] 4/6 recover: run the repair stage")
            recovered = workdir / f"{deliverable.stem}.recovered{deliverable.suffix}"
            rc_r, out_r = run_stage(repair, file=str(faulted), out=str(recovered))
            ok_r = recovered.is_file() and rc_r == 0
            record("recover", ok_r, f"repair exit={rc_r}" + (f" | {out_r}" if out_r else ""))
            print(f"        {'PASS' if ok_r else 'FAIL'}  repair exit={rc_r}")
            evidence["recovered_path"] = str(recovered)

            if not ok_r:
                outcome = "DAMAGED"
            else:
                # 5. re-detection ------------------------------------------
                print("[proof] 5/6 re-detect: the recovered copy must pass")
                rc_v, out_v = run_stage(detect, file=str(recovered))
                passed = rc_v == 0
                record("detect_recovered", passed,
                       f"detector exit={rc_v}" + (f" | {out_v}" if out_v else ""))
                print(f"        {'PASS' if passed else 'FAIL'}  detector exit={rc_v}")

                # 6. content preservation ---------------------------------
                print("[proof] 6/6 content: recovery must not silently drop anything")
                before = evidence["content_faulted"]
                after = fingerprint(recovered)
                evidence["content_recovered"] = after
                drift = {k: (before.get(k, 0), after.get(k, 0))
                         for k in ("slides", "sheets", "media", "text_runs")
                         if before.get(k, 0) != after.get(k, 0)}
                ok_c = passed and after.get("readable") and not drift
                record("content_preserved", ok_c, json.dumps(drift) if drift else "no drift")
                print(f"        {'PASS' if ok_c else 'FAIL'}  "
                      + (f"content changed: {drift}" if drift else "no content lost"))

                if not passed:
                    outcome = "DAMAGED"
                elif not ok_c:
                    outcome = "DAMAGED"
                else:
                    outcome = "PROVEN"

    evidence["outcome"] = outcome

    # The faulted and recovered copies ARE the evidence. A report that points at a path it
    # deleted is worse than no report, so they are retained by default.
    retained = []
    for temp in (workdir / f"{deliverable.stem}.faulted{deliverable.suffix}",
                 workdir / f"{deliverable.stem}.recovered{deliverable.suffix}"):
        if not temp.exists():
            continue
        if args.discard_intermediates:
            temp.unlink()
        else:
            retained.append(str(temp))
    evidence["retained_evidence"] = retained

    wording = {
        "PROVEN": "The pipeline caught the injected fault and recovered it without losing content.",
        "DETECTED": "The detector caught the injected fault. No recovery stage was tested.",
        "MISSED": "The pipeline did not catch the injected fault. Do not claim it works.",
        "DAMAGED": "Recovery ran but the result is invalid or lost content.",
        "BASELINE_BROKEN": "The deliverable itself fails detection before any fault was injected.",
        "INCONCLUSIVE": "The fault could not be injected, so nothing was proven.",
    }[outcome]

    print(f"\n[proof] outcome: {outcome}\n        {wording}")

    if args.json_out:
        evidence["summary"] = wording
        Path(args.json_out).write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[proof] evidence pack written to {args.json_out}")

    return OUTCOME_EXIT[outcome]


if __name__ == "__main__":
    raise SystemExit(main())
