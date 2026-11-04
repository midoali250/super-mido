"""Repository self-checks: the content policy is enforced by the test suite too.

The rules live in ``tools/check_policy.py`` so CI and the tests cannot drift
apart. These fail if anyone commits a cartridge image, a prebuilt binary,
generated analysis output, or a third-party product name used as branding.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import check_policy  # noqa: E402


@pytest.fixture(scope="module")
def files() -> list[str]:
    return check_policy.tracked_files()


def test_checker_finds_something_to_check(files):
    assert len(files) > 10, "policy checker saw almost no files; is it wired up?"


def test_no_cartridge_images_or_binaries_are_present(files):
    offenders = check_policy.check_binaries(files)
    assert not offenders, (
        "these must not be committed (see docs/LEGAL.md): " + ", ".join(offenders)
    )


def test_no_committed_disassembly_output(files):
    offenders = check_policy.check_generated_output(files)
    assert not offenders, "generated output must not be committed: " + str(offenders)


def test_branding_surfaces_are_free_of_third_party_product_names(files):
    hits = check_policy.check_branding(files)
    assert not hits, "third-party product names must not appear as branding:\n" + "\n".join(hits)


def test_policy_checker_exits_zero():
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "check_policy.py")],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_checker_actually_detects_violations(tmp_path, monkeypatch):
    """Guard the guard: a rule that never fires is not a rule."""
    assert check_policy.check_binaries(["game.nes", "src/x.py"]) == ["game.nes"]
    assert check_policy.check_binaries(["build/app.apk"]) == ["build/app.apk"]
    assert check_policy.check_generated_output(["out/listing.asm"]) == ["out/listing.asm"]
    assert check_policy.check_generated_output(["x.dis"]) == ["x.dis"]

    fake = tmp_path / "README.md"
    fake.write_text("# Super Mario Engine\n", encoding="utf-8")
    monkeypatch.setattr(check_policy, "ROOT", tmp_path)
    assert check_policy.check_branding(["README.md"]) != []


def test_legal_policy_document_exists_and_states_the_rule():
    doc = (ROOT / "docs" / "LEGAL.md").read_text(encoding="utf-8")
    assert "contains no games" in doc
    assert "cartridge images" in doc


def test_gitignore_blocks_cartridge_images():
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for ext in ("*.nes", "*.apk", "*.sfc", "*.z64", "*.exe"):
        assert ext in ignore, f"{ext} is not ignored"
