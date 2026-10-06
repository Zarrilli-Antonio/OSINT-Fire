"""Regenerate THIRD_PARTY_NOTICES.md from the installed Python packages.

    cd backend && uv run --extra mcp python ../scripts/third_party_notices.py > ../THIRD_PARTY_NOTICES.md
"""
import importlib.metadata as m

FIXES = {"ptyprocess": "ISC"}  # packages whose metadata carries no license field
HEAD = """# Third-party notices

OSINT-Fire is released under the MIT License (see `LICENSE`). The packaged app (`dist/OSINT-Fire.app`) bundles the Python
packages below, each under its own license, and the Flutter engine and packages listed at the end.

Notes
- **pycountry** (LGPL-2.1) is a dependency of Maigret. It is pure Python and is shipped unmodified as replaceable files, so the
  LGPL conditions are met; you can swap it by rebuilding the app with another version.
- **PyInstaller** (GPL-2.0 with a special exception) freezes the backend; the exception allows distributing the result under any license.
- **certifi** is MPL-2.0 and is used unmodified.
- OSINT-Fire does not bundle or import theHarvester (GPL); it is only run, if the user installed it, as a separate program.
- Data sources are queried through their public or documented APIs under their own terms; no data from them is redistributed with the app.

## Python packages (backend)

| Package | Version | License |
|---|---|---|
"""
TAIL = """
## Flutter / Dart (app)

Flutter and the Dart SDK are BSD-3-Clause (Google). Direct dependencies: `http` (BSD-3-Clause, Dart project authors),
`cupertino_icons` (MIT). Their transitive Dart dependencies are BSD-3-Clause or MIT; see `app/pubspec.lock`.
Fonts: the interface uses the system monospace font (Menlo) and bundles no font files.
"""


def lic(d) -> str:
    meta = d.metadata
    text = meta.get("License-Expression") or meta.get("License") or ""
    if text and len(text) < 80 and "\n" not in text:
        return text.strip()
    cls = [c.split("::")[-1].strip() for c in meta.get_all("Classifier") or [] if c.startswith("License ::") and "OSI Approved" not in c.split("::")[-1]]
    cls = cls or [c.split("::")[-1].strip() for c in meta.get_all("Classifier") or [] if c.startswith("License ::")]
    return "; ".join(cls) or FIXES.get(meta["Name"], "see package")


rows = sorted(((d.metadata["Name"], d.version, FIXES.get(d.metadata["Name"]) or lic(d)) for d in m.distributions()), key=lambda r: r[0].lower())
print(HEAD + "\n".join(f"| {n} | {v} | {l} |" for n, v, l in rows) + TAIL)
