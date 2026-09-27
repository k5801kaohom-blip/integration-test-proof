#!/usr/bin/env python3
"""Render a deliverable to a reviewable contact sheet.

Structural proof and visual proof are different claims and both are needed. This script
turns an Office file or a directory of images into one contact sheet so every page can be
inspected at once, in order.

Exit codes
    0   contact sheet produced
    1   rendering produced no pages
    2   usage or environment error
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_IMG_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
_OFFICE_SUFFIXES = {".pptx", ".docx", ".xlsx", ".pptm", ".docm", ".xlsm"}
_LABEL_FONT = 18


def solexists() -> str | None:
    return shutil.which("soffice") or shutil.which("libreoffice")


def render_office(path: Path, outdir: Path) -> list[Path]:
    """Convert an Office file to PDF, then to one image per page."""
    office = solexists()
    if office is None:
        raise RuntimeError("LibreOffice (soffice) not found; cannot render Office files")
    subprocess.run([office, "--headless", "--convert-to", "pdf", "--outdir", str(outdir), str(path)],
                   capture_output=True, text=True, timeout=900)
    pdfs = list(outdir.glob("*.pdf"))
    if not pdfs:
        return []
    if shutil.which("pdftoppm"):
        subprocess.run(["pdftoppm", "-jpeg", "-r", "90", "-scale-to-x", "1400",
                        "-scale-to-y", "-1", str(pdfs[0]), str(outdir / "page")],
                       capture_output=True, text=True, timeout=900)
        return sorted(outdir.glob("page-*.jpg"))
    raise RuntimeError("pdftoppm (poppler-utils) not found; cannot rasterise the PDF")


def collect_images(source: Path) -> list[Path]:
    if source.is_dir():
        files = [f for f in source.iterdir() if f.suffix.lower() in _IMG_SUFFIXES]
        return sorted(files, key=lambda p: _natural_key(p.name))
    if source.suffix.lower() in _IMG_SUFFIXES:
        return [source]
    return []


def _natural_key(name: str) -> tuple:
    import re
    return tuple(int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name))


def build_sheet(images: list[Path], out_path: Path, cols: int, cell_w: int) -> None:
    from PIL import Image, ImageDraw

    cell_h = int(cell_w * 9 / 16)
    pad, label_h = 10, 24
    rows = (len(images) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (cell_w + pad) + pad, rows * (cell_h + label_h + pad) + pad),
                      (18, 24, 34))
    draw = ImageDraw.Draw(sheet)
    for i, f in enumerate(images):
        with Image.open(f) as im:
            rgb = im.convert("RGB")
            scale = min(cell_w / rgb.width, cell_h / rgb.height)
            thumb = rgb.resize((max(1, int(rgb.width * scale)), max(1, int(rgb.height * scale))),
                               Image.LANCZOS)
        c, r = i % cols, i // cols
        x = pad + c * (cell_w + pad) + (cell_w - thumb.width) // 2
        y = pad + r * (cell_h + label_h + pad) + (cell_h - thumb.height) // 2
        sheet.paste(thumb, (x, y))
        draw.text((pad + c * (cell_w + pad) + 4, y + thumb.height + 5),
                  f"page {i + 1}  ({f.name})", fill=(210, 225, 240))
    sheet.save(out_path, quality=86)


def main() -> int:
    ap = argparse.ArgumentParser(description="Build a contact sheet for visual review.")
    ap.add_argument("source", help="an Office file, an image file, or a directory of images")
    ap.add_argument("-o", "--output", required=True, help="contact sheet path (.jpg or .png)")
    ap.add_argument("--cols", type=int, default=2, help="columns in the sheet (default: 2)")
    ap.add_argument("--cell-width", type=int, default=620, help="thumbnail width (default: 620)")
    ap.add_argument("--keep-pages", default=None,
                    help="also write the individual page images into this directory")
    args = ap.parse_args()

    source = Path(args.source)
    if not source.exists():
        print(f"[render] source not found: {source}", file=sys.stderr)
        return 2

    tmp = Path(tempfile.mkdtemp(prefix="render_check_"))
    try:
        if source.suffix.lower() in _OFFICE_SUFFIXES:
            print(f"[render] converting {source.name} to pages")
            try:
                images = render_office(source, tmp)
            except (RuntimeError, subprocess.TimeoutExpired) as exc:
                print(f"[render] {exc}", file=sys.stderr)
                return 2
        else:
            images = collect_images(source)

        if not images:
            print("[render] no pages were produced", file=sys.stderr)
            return 1

        print(f"[render] {len(images)} page(s) -> {args.output}")
        build_sheet(images, Path(args.output), max(1, args.cols), max(120, args.cell_width))

        if args.keep_pages:
            dest = Path(args.keep_pages)
            dest.mkdir(parents=True, exist_ok=True)
            for i, f in enumerate(images, start=1):
                shutil.copy(f, dest / f"page-{i:02d}{f.suffix}")
            print(f"[render] page images copied to {dest}")

        print(f"[render] contact sheet written to {args.output}")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())