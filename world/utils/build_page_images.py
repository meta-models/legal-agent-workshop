#!/usr/bin/env python3
"""Build page images (one-off utility).

Page images (100 dpi PNG) for every document, next to the documents in a
pages/ folder: the review platform's page renders. check_signatures sends
these to SAM, so participants need no PDF renderer.

Requires pdftoppm and pdfinfo.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

DPI = 100


def pages_of(pdf: Path) -> int:
    info = subprocess.run(
        ["pdfinfo", str(pdf)], capture_output=True, text=True, check=True
    ).stdout
    match = re.search(r"Pages:\s+(\d+)", info)
    if match is None:
        raise RuntimeError(f"pdfinfo reported no page count for {pdf}")
    return int(match.group(1))


def render(doc: Path, out_dir: Path) -> int:
    out_dir.mkdir(exist_ok=True)
    stem = doc.stem
    for old in out_dir.glob(f"{stem}-*.png"):
        old.unlink()
    if doc.suffix.lower() == ".pdf":
        subprocess.run(
            [
                "pdftoppm",
                "-r",
                str(DPI),
                "-gray",
                "-png",
                str(doc),
                str(out_dir / f"{stem}-render"),
            ],
            check=True,
        )
        # pdftoppm writes <prefix>-1.png or <prefix>-01.png; normalise to <ID>-p1.png.
        for png in out_dir.glob(f"{stem}-render-*.png"):
            n = int(png.stem.rsplit("-", 1)[1])
            png.rename(out_dir / f"{stem}-p{n}.png")
        return pages_of(doc)
    (out_dir / f"{stem}-p1.png").write_bytes(
        subprocess.run(
            [
                "python3",
                "-c",
                "import sys;from PIL import Image;im=Image.open(sys.argv[1]).convert('L');im.thumbnail((1100,1100));im.save(sys.stdout.buffer,'PNG')",
                str(doc),
            ],
            capture_output=True,
            check=True,
        ).stdout
    )
    return 1


def main() -> None:
    root = (
        Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]
    )
    releases = [
        ("initial", root / "cases/northbridge-v-caldera/documents"),
        ("follow_up", root / "world/follow_up"),
    ]
    for release, folder in releases:
        for doc in sorted(folder.iterdir()):
            if not doc.is_file() or doc.suffix.lower() not in {
                ".pdf",
                ".jpg",
                ".jpeg",
                ".png",
            }:
                continue
            pages = render(doc, folder / "pages")
            print(doc.stem, release, pages)


if __name__ == "__main__":
    main()
