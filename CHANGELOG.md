# Changelog

All notable changes to this project. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project uses
[semantic versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0]

### Added
- **Pointer and jump-table detection** (`tables.py`). Finds runs of
  consecutive little-endian words that land inside PRG ROM, emits them as
  `.word` entries instead of decoding them as instructions, and feeds every
  target back in as an entry point so `recursive` mode reaches handlers that
  are only ever called through an indexed load.
- **Symbol files** (`symbols.py`). Reads FCEUX `.sym` and Mesen `.mlb`
  dialects, emits `.sym`. User symbols override auto-generated labels, so
  repeated analysis sessions accumulate naming instead of restarting.
- CLI: `--detect-tables`, `--min-table`, `--symbols`, `--symbols-out`.
- `Makefile` with `install` / `test` / `lint` / `fmt` / `policy` / `demo` /
  `check` targets.
- `docs/ARCHITECTURE.md` — module dependency graph and the design rules that
  come up in review.
- `CONTRIBUTING.md` — including the content policy and what gets a PR closed.
- `CHANGELOG.md`, `.editorconfig`.

### Changed
- Renamed the project and package from the working name to **SuperMido** /
  `supermido`.
- `tools/rename_project.py` now also rewrites extensionless files such as
  `LICENSE`, which it previously skipped.
- Disassembly statistics now report `pointer_tables` and
  `pointer_table_entries`.
- Auto-labels go through `symbols.auto_name()` so the format has one
  definition.

### Fixed
- Table detection scanned every byte offset, which broke a run at its second
  byte. It now walks word-aligned from each candidate start.
- Policy checker scanned `__pycache__` bytecode when running outside a git
  repository, producing false positives from string constants.

## [0.1.0]

### Added
- **iNES header parsing** (`ines.py`): iNES, iNES 0.7, archaic iNES and
  NES 2.0, using the recommended detection procedure rather than trusting the
  magic bytes. Mapper numbers up to 4095, submappers, mirroring, trainer,
  battery, four-screen, Vs. Unisystem and PlayChoice flags.
- **Dump forensics**: detects ripper signatures in the padding bytes and masks
  the inflated mapper number back off, recording the correction as a warning
  instead of silently reporting the wrong board.
- **Full 256-entry 6502 opcode table** (`cpu6502.py`): 151 official NMOS
  instructions plus 105 undocumented ones (`SLO`, `RLA`, `SRE`, `RRA`, `DCP`,
  `ISB`, `SAX`, `LAX`, `ANC`, `ALR`, `ARR`, `AXS`, `AHX`, `TAS`, `SHX`, `SHY`,
  `LAS`). Opcodes whose effect depends on analog silicon behaviour are flagged
  as unstable rather than silently decoded.
- **Two-pass 6502 assembler** (`asm6502.py`) with a fixed-point sizing loop,
  forward references, and automatic zero-page-to-absolute widening.
- **Disassembler** (`disasm.py`) with `linear` and `recursive` strategies,
  code/data separation, cross-reference collection, auto-labelling of branch
  and jump targets, and inline interrupt-vector emission.
- **Round-trip verification**: re-encodes every instruction and diffs against
  the original bytes, reporting exact addresses on mismatch.
- **CHR-ROM decoding** (`chrrom.py`): two-bitplane tile decoding to text or
  PGM, with blank/solid/used statistics. No imaging dependency.
- **CLI** (`cli.py`): `inspect`, `disasm`, `chr`, `verify`.
- **Synthetic test fixtures** (`tests/fixtures.py`): assembles 6502 source and
  wraps it in a valid header at runtime, so the suite needs no external data.
- **Content-policy enforcement**: `.gitignore`, `tools/check_policy.py` in CI,
  and `tests/test_policy.py` including a test that the checker itself fires on
  a violation.
- `tools/make_sample.py`, `tools/rename_project.py`.
- MIT licence, `docs/LEGAL.md`.

[0.2.0]: https://github.com/midoali250/super-mido/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/midoali250/super-mido/releases/tag/v0.1.0
