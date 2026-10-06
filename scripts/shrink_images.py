"""Shrink the README pictures (2160 px wide golden images -> 1600 px, optimised PNG). Run after regenerating them:

    SCREENSHOTS=1 flutter test --update-goldens test/screenshots_test.dart   (in app/)
    python3 scripts/shrink_images.py
"""
from pathlib import Path

from PIL import Image

for p in sorted((Path(__file__).resolve().parent.parent / "docs" / "images").glob("*.png")):
    im = Image.open(p)
    if im.width > 1600:
        im = im.resize((1600, round(im.height * 1600 / im.width)), Image.LANCZOS)
    im.save(p, optimize=True)
    print(f"{p.name}: {im.width}x{im.height}, {p.stat().st_size // 1024} kB")
