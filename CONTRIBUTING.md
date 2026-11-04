# Contributing

Thanks for looking. Two things to read before you open a PR.

## 1. The content policy — read this first

[`docs/LEGAL.md`](docs/LEGAL.md) explains it in full. The short version:

**This repository contains a tool and no game data.** Not "we try to avoid
it" — it is enforced three separate ways, and a PR that breaks any of them
fails CI before a human looks at it.

| Enforcement | What it catches |
|---|---|
| `.gitignore` | Cartridge images, prebuilt binaries, generated listings |
| `tools/check_policy.py` in CI | Anything tracked that should not be, plus third-party product names used as branding |
| `tests/test_policy.py` | The same rules locally, including a test that the checker itself actually fires |

Concretely, a PR will be closed without review if it adds:

- a cartridge image (`.nes`, `.sfc`, `.z64`, …) or any console dump
- a prebuilt binary (`.apk`, `.exe`, `.AppImage`, `.so`, …)
- a disassembly listing, extracted graphics, audio, or asset dump of a
  commercial title
- a third-party product name in the README, package metadata, source, CI or
  tooling

If your change genuinely needs a test image, **build one**. `tests/fixtures.py`
assembles 6502 source into a valid cartridge at runtime; `tools/make_sample.py`
does the same for manual testing. Synthetic input with known expected output is
better testing than a binary blob anyway.

## 2. How the code is organised

[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) covers the module layout and the
design rules. The ones that come up most in review:

- **No runtime dependencies.** Standard library only. If you need Pillow,
  numpy or a parser generator, that is a conversation before the PR, not in it.
- **Analysis returns data, not text.** `disassemble()` produces `Line` values;
  rendering happens in `Line.render()` and `Disassembly.as_dict()`. New output
  formats should not touch the walker.
- **Malformed input produces warnings, not exceptions.** Real dumps are
  truncated, mis-tagged and scribbled on. Add a `HeaderWarning` and keep going.
- **The round trip must hold.** If you add an opcode or change operand
  formatting, `tests/test_disasm.py::test_round_trip_is_byte_exact` is the
  thing that will catch you. That is its job.

## Development

```bash
make install     # pip install -e ".[dev]"
make check       # lint + test + policy, exactly what CI runs
make demo        # build a synthetic cartridge and walk it through the CLI
```

Or directly:

```bash
pytest -v
ruff check src tests tools
python tools/check_policy.py
```

Python 3.10+ is required. CI tests 3.10 through 3.13.

## Commit and PR conventions

- Imperative mood, first line under 72 characters: `add MMC1 bank tracking`
- Explain *why* in the body, not *what* — the diff shows what
- One logical change per PR; a PR that adds a feature and reformats the module
  it lives in is two PRs
- New behaviour needs a test. New opcode or addressing-mode support needs a
  round-trip test.

## Good first issues

The roadmap in the README is the honest list. Roughly in order of how much
they teach you about the codebase:

1. **HTML output** — a new renderer over the existing `Line` values. No
   analysis changes, so it is self-contained.
2. **ca65/ld65 export dialect** — same shape, different syntax. Teaches you
   where the current renderer's assumptions live.
3. **NES 2.0 large-ROM sizes** — the exponent/multiplier encoding. Small,
   well-specified, and `ines.py` has tests to hang it on.
4. **Mapper bank tracking** — the big one. Per-mapper bank models so
   `recursive` can follow code across bank boundaries. Start with UxROM
   (simplest) before MMC1.

## Licence

The project is MIT. By contributing you agree your contribution is licensed
the same way. See `LICENSE` — note that it covers the software only and grants
no rights over any file you analyse with it.
