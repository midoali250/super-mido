#!/usr/bin/env python3
"""Rename the project in one pass.

The working name in this repository is provisional. This rewrites the package
directory, imports, packaging metadata, CLI entry point, docs and CI in one
go, then re-runs the test suite so you can see immediately whether it held.

    python tools/rename_project.py BitVault
    python tools/rename_project.py BitVault --dry-run
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OLD_NAME = "SuperMido"
OLD_PKG = "supermido"

IDENT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*(?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")
TEXT_SUFFIXES = {".py", ".md", ".toml", ".yml", ".yaml", ".txt", ".cfg",
                 ".ini", ".rst", ".json", ".asm"}
# Extensionless files that still carry the project name.
NAMELESS_TEXT = {"LICENSE", "LICENCE", "COPYING", "Makefile", "README",
                 "CONTRIBUTING", "CHANGELOG", ".gitignore", ".editorconfig"}


def check_name(name: str) -> tuple[str, str]:
    """Validate and derive the package slug. Returns ``(display, slug)``."""
    if not IDENT_RE.match(name):
        raise SystemExit(f"error: {name!r} is not a valid package/project name")
    if len(name) > 40:
        raise SystemExit("error: keep the name under 40 characters")
    slug = re.sub(r"[^a-z0-9]+", "", name.lower()) or name.lower()
    if not slug.isidentifier():
        slug = "p" + slug
    blocked = {"nes", "rom", "emulator", "nintendo", "famicom", "mario"}
    if slug.lower() in blocked:
        raise SystemExit(f"error: {slug!r} is too generic or belongs to someone else")
    return name, slug


def files_to_edit(slug: str) -> list[Path]:
    skip = {".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".venv", "dist", "build"}
    out = []
    for p in sorted(ROOT.rglob("*")):
        if any(part in skip for part in p.relative_to(ROOT).parts):
            continue
        if p.is_file() and (p.suffix in TEXT_SUFFIXES or p.name in NAMELESS_TEXT):
            out.append(p)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("name", help="new display name, e.g. BitVault")
    ap.add_argument("--dry-run", action="store_true", help="show what would change")
    ap.add_argument("--no-test", action="store_true", help="skip the test run afterwards")
    args = ap.parse_args()

    display, slug = check_name(args.name)
    if slug == OLD_PKG:
        raise SystemExit(f"error: already named {display}")

    print(f"renaming {OLD_NAME} -> {display}  (package {OLD_PKG} -> {slug})")

    edits = 0
    for path in files_to_edit(slug):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        new = text.replace(OLD_NAME, display).replace(OLD_PKG, slug)
        if new != text:
            edits += 1
            print(f"  edit {path.relative_to(ROOT)}")
            if not args.dry_run:
                path.write_text(new, encoding="utf-8")

    src_old, src_new = ROOT / "src" / OLD_PKG, ROOT / "src" / slug
    if src_old.is_dir():
        print(f"  move src/{OLD_PKG}/ -> src/{slug}/")
        if not args.dry_run:
            shutil.move(str(src_old), str(src_new))

    if args.dry_run:
        print(f"\ndry run: {edits} file(s) would change")
        return 0

    print(f"\nrenamed across {edits} file(s).")
    if args.no_test:
        return 0

    print("re-running the test suite...\n")
    return subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main())
