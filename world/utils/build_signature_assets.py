#!/usr/bin/env python3
"""Build the signature assets for the workshop case (one-off utility; run once).

1. NBI-00000151: Test Strategy approval page carrying Marcus Thibodeaux's genuine
   handwritten signature (the reference signature).
2. CALDERA-00000419: replaces the typed signature on the UAT Phase 2 exit
   certification with a handwritten one that does not match the reference.

Requires Pillow and pdftoppm. Output PDFs are 300 dpi 1-bit scans, like the rest
of the case. Deterministic: the same seeds always draw the same signatures.
"""

from __future__ import annotations

import math
import random
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

DPI = 300
PAGE = (2550, 3300)
SERIF = "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf"
SANS = "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf"
SANS_BOLD = "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf"


def font(path: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


def signature_path(
    seed: int, width: int, height: int, loops: int, slant: float, flourish: bool
) -> list:
    """A cursive-looking pen path: a rising initial, a run of loops, an underline flourish."""
    rng = random.Random(seed)
    points = []
    # Tall initial stroke.
    x0, base = 0.04 * width, 0.72 * height
    for t in range(0, 41):
        s = t / 40
        x = x0 + 0.06 * width * s + slant * (0.6 - s) * height * 0.3
        y = base - 0.62 * height * math.sin(math.pi * s)
        points.append((x, y))
    # Body loops with varying amplitude.
    x = points[-1][0]
    for _ in range(loops):
        amp = height * rng.uniform(0.18, 0.42)
        span = width * rng.uniform(0.045, 0.075)
        for t in range(0, 31):
            s = t / 30
            px = x + span * s - 0.35 * span * math.sin(2 * math.pi * s)
            py = (
                base
                - amp * (0.5 - 0.5 * math.cos(2 * math.pi * s))
                - slant * span * s * 0.2
            )
            points.append((px, py))
        x += span
        if rng.random() < 0.25:  # an ascender
            for t in range(0, 21):
                s = t / 20
                points.append(
                    (x + 0.02 * width * s, base - 0.55 * height * math.sin(math.pi * s))
                )
            x += 0.02 * width
    if flourish:
        end = points[-1]
        for t in range(0, 61):
            s = t / 60
            points.append(
                (
                    end[0] - 0.85 * (x - x0) * s,
                    end[1] + 0.12 * height + 0.05 * height * math.sin(3 * math.pi * s),
                )
            )
    return points


def angular_path(seed: int, width: int, height: int, peaks: int) -> list:
    """An upright, angular hand: sharp peaks, no loops, no flourish."""
    rng = random.Random(seed)
    base, x = 0.8 * height, 0.03 * width
    points = [(x, base), (x + 0.02 * width, 0.08 * height), (x + 0.05 * width, base)]
    x += 0.07 * width
    for _ in range(peaks):
        top = height * rng.uniform(0.25, 0.6)
        step = width * rng.uniform(0.04, 0.08)
        points += [(x + step * 0.5, top), (x + step, base)]
        x += step
    points += [(x + 0.03 * width, base - 0.1 * height)]
    return points


def draw_angular(img: Image.Image, box: tuple, seed: int, peaks: int, pen: int) -> None:
    x1, y1, x2, y2 = box
    pts = [(x1 + px, y1 + py) for px, py in angular_path(seed, x2 - x1, y2 - y1, peaks)]
    ImageDraw.Draw(img).line(pts, fill=0, width=pen, joint="curve")


def draw_signature(
    img: Image.Image,
    box: tuple,
    seed: int,
    loops: int,
    slant: float,
    flourish: bool,
    pen: int,
) -> None:
    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1
    pts = [
        (x1 + px, y1 + py)
        for px, py in signature_path(seed, w, h, loops, slant, flourish)
    ]
    d = ImageDraw.Draw(img)
    d.line(pts, fill=0, width=pen, joint="curve")


def to_pdf(img: Image.Image, out: Path) -> None:
    img.convert("1").save(out, "PDF", resolution=DPI)


def build_reference(out: Path) -> None:
    img = Image.new("L", PAGE, 255)
    d = ImageDraw.Draw(img)
    big, mid, small = font(SANS_BOLD, 50), font(SANS, 34), font(SANS, 28)
    serif = font(SERIF, 36)
    d.text((240, 220), "CALDERA", font=font(SANS_BOLD, 96), fill=0)
    d.text((240, 330), "CONSULTING GROUP", font=mid, fill=0)
    d.text(
        (240, 380),
        "233 West Kinzie Street, Suite 1900, Chicago, Illinois 60654",
        font=small,
        fill=0,
    )
    d.line((240, 450, 2310, 450), fill=0, width=4)
    d.text(
        (1450, 480), "CONFIDENTIAL — SUBJECT TO PROTECTIVE ORDER", font=small, fill=0
    )
    d.text(
        (520, 580), "PROJECT KEYSTONE — TEST STRATEGY AND APPROACH", font=big, fill=0
    )
    d.text((1000, 670), "Version 1.0 — Approval Page", font=mid, fill=0)
    d.line((240, 740, 2310, 740), fill=0, width=3)
    body = [
        "Document Ref: CCG-KEY-TST-001    Date: August 30, 2024",
        "",
        "This Test Strategy sets out the approach to System Integration Testing and User",
        "Acceptance Testing for Project Keystone under Statement of Work No. 001, including",
        "the entry and exit criteria at Appendix E and the defect severity definitions used",
        "throughout the programme.",
        "",
        "The Test Manager is responsible for certifying the exit of each test phase. Exit",
        "certification is a personal certification by the Test Manager and may not be",
        "delegated or signed on the Test Manager's behalf.",
        "",
        "APPROVALS",
    ]
    y = 820
    for line in body:
        d.text((240, y), line, font=serif, fill=0)
        y += 58
    y += 40
    approvers = [
        ("Marcus Thibodeaux", "Test Manager, Caldera Consulting Group", 101, 7, 0.55),
        (
            "Thomas Vasquez-Hill",
            "Director of Information Technology, Northbridge Industries, Inc.",
            202,
            5,
            -0.2,
        ),
    ]
    for name, title, seed, loops, slant in approvers:
        sig_box = (260, y, 1160, y + 230)
        draw_signature(img, sig_box, seed, loops, slant, name.startswith("Marcus"), 7)
        d.line((240, y + 250, 1200, y + 250), fill=0, width=3)
        d.text((1320, y + 190), "08/30/2024", font=serif, fill=0)
        d.line((1300, y + 250, 1900, y + 250), fill=0, width=3)
        d.text((240, y + 270), name, font=serif, fill=0)
        d.text((240, y + 322), title, font=small, fill=0)
        d.text((1300, y + 270), "Date", font=serif, fill=0)
        y += 520
    d.text(
        (120, 3150), "CONFIDENTIAL · SUBJECT TO PROTECTIVE ORDER", font=small, fill=0
    )
    d.text((2080, 3150), "NBI-00000151", font=font(SANS_BOLD, 28), fill=0)
    to_pdf(img, out)


def build_questioned(source: Path, out: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            ["pdftoppm", "-r", str(DPI), "-gray", "-png", str(source), f"{tmp}/p"],
            check=True,
        )
        page = Image.open(next(Path(tmp).glob("p*.png"))).convert("L")
    if page.size != PAGE:
        page = page.resize(PAGE)
    # The typed "M. Thibodeaux" sits on the signature line above the printed name (y ~ 2610-2700 at 300 dpi).
    d = ImageDraw.Draw(page)
    d.rectangle((300, 2632, 1230, 2728), fill=255)
    # A different hand: upright and angular, no loops, no flourish.
    draw_angular(page, (330, 2625, 1100, 2730), 977, 10, 7)
    to_pdf(page, out)


def main() -> None:
    root = (
        Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]
    )
    initial = root / "cases/northbridge-v-caldera/documents"
    follow_up = root / "world/follow_up"
    build_reference(initial / "NBI-00000151.pdf")
    original = follow_up / "CALDERA-00000419.pdf"
    backup = Path(tempfile.gettempdir()) / "CALDERA-00000419.original.pdf"
    if not backup.exists():
        backup.write_bytes(original.read_bytes())
    build_questioned(backup, original)
    print("built", initial / "NBI-00000151.pdf", "and", original)


if __name__ == "__main__":
    main()
