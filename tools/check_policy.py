#!/usr/bin/env python3
"""Repository content-policy checker.

Run by CI and by ``tests/test_policy.py`` so there is exactly one definition of
the rules. Scans tracked files (or the whole tree if this is not a git
repository yet) for:

  1. cartridge images and prebuilt binaries
  2. committed disassembly / asset output
  3. third-party product names used as branding

Exit code 0 when clean, 1 when a rule is violated.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Cartridge images, console dumps and prebuilt binaries.
FORBIDDEN_SUFFIXES = {
    ".nes", ".fc", ".fds", ".unf", ".unif", ".nez", ".nsf",
    ".sfc", ".smc", ".fig", ".n64", ".z64", ".v64",
    ".gb", ".gbc", ".gba", ".nds", ".chd", ".pbp",
    ".apk", ".aab", ".exe", ".appimage", ".dmg",
    ".so", ".dll", ".dylib", ".jar",
}

#: Directories and suffixes that mean "generated analysis output".
FORBIDDEN_PREFIXES = ("out/", "disasm_out/", "listing/", "tiles/", "assets_dump/")
FORBIDDEN_OUTPUT_SUFFIXES = (".dis", ".asm.out", ".chr.pgm", ".chr.png")

#: Words that belong to somebody else. Listed as fragments so this file is the
#: only place in the repository where they appear at all.
BRAND_FRAGMENTS = (
    "super" + " mario", "super" + "_mario", "super" + "-mario", "super" + "mario",
    "duck" + " hunt", "duck" + "_hunt",
    "legend" + " of " + "zelda",
    "metroid", "castlevania", "mega" + " man",
)
BRANDING_PATTERN = re.compile(
    "|".join(re.escape(f).replace(r"\ ", r"[\s_-]?") for f in BRAND_FRAGMENTS),
    re.IGNORECASE,
)

#: Suffixes worth reading as text.
TEXT_SUFFIXES = {".py", ".md", ".toml", ".yml", ".yaml", ".txt", ".cfg",
                 ".ini", ".json", ".rst", ".asm", ".s", ".c", ".h", ".sh"}

#: Files that state the policy necessarily quote the forbidden terms.
SELF_EXEMPT = ("tools/check_policy.py", "docs/LEGAL.md")

#: Surfaces where a product name would constitute branding rather than prose.
BRANDING_SURFACES = ("README.md", "pyproject.toml", "src/", ".github/", "tools/")


def tracked_files() -> list[str]:
    try:
        out = subprocess.run(
            ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        out = ""
    if out.strip():
        return [line for line in out.splitlines() if line.strip()]
    skip = {".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache",
            ".venv", "venv", "dist", "build", ".tox", ".nox", ".eggs"}
    out = []
    for p in sorted(ROOT.rglob("*")):
        rel = p.relative_to(ROOT)
        if any(part in skip for part in rel.parts):
            continue
        if p.is_file():
            out.append(str(rel).replace("\\", "/"))
    return out


def check_binaries(files: list[str]) -> list[str]:
    return [f for f in files if Path(f).suffix.lower() in FORBIDDEN_SUFFIXES]


def check_generated_output(files: list[str]) -> list[str]:
    return [f for f in files
            if f.startswith(FORBIDDEN_PREFIXES)
            or f.endswith(FORBIDDEN_OUTPUT_SUFFIXES)]


def check_branding(files: list[str]) -> list[str]:
    hits = []
    for rel in files:
        if rel in SELF_EXEMPT:
            continue
        if not any(rel == s or rel.startswith(s) for s in BRANDING_SURFACES):
            continue
        path = ROOT / rel
        if not path.is_file():
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name != ".gitignore":
            continue  # only text can carry branding
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if BRANDING_PATTERN.search(line):
                hits.append(f"{rel}:{i}: {line.strip()}")
    return hits


def main() -> int:
    files = tracked_files()
    print(f"checking {len(files)} files against the content policy")

    problems: list[tuple[str, list[str]]] = [
        ("cartridge images / prebuilt binaries must not be committed", check_binaries(files)),
        ("generated disassembly output must not be committed", check_generated_output(files)),
        ("third-party product names must not be used as branding", check_branding(files)),
    ]

    failed = False
    for rule, offenders in problems:
        if offenders:
            failed = True
            print(f"\nFAIL: {rule}")
            for o in offenders[:40]:
                print(f"  - {o}")
            if len(offenders) > 40:
                print(f"  ... and {len(offenders) - 40} more")
        else:
            print(f"ok:   {rule}")

    if failed:
        print("\nSee docs/LEGAL.md for the reasoning.")
        return 1
    print("\nclean.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
