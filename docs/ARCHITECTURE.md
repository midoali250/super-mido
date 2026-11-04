# Architecture

Five modules, one direction of dependency. Nothing imports the CLI.

```
        cli.py
          |
   +------+------+----------------+
   |             |                |
disasm.py    chrrom.py        symbols.py
   |                             ^
   +--------+--------------------+
            |
        ines.py       tables.py
            |
        cpu6502.py
            ^
            |
        asm6502.py
```

## `cpu6502.py` — the instruction set

The only module that knows what a 6502 is. A 256-entry table of
`(mnemonic, addressing_mode, length, official)`, plus the operand formatting
rules. Undocumented NMOS opcodes are first-class entries rather than an
afterthought, and `UNSTABLE` flags the ones whose behaviour depends on analog
properties of the silicon.

Everything above this module treats the CPU as data, not as hardcoded
behaviour. Adding a CPU variant means adding a table, not a branch.

## `ines.py` — the container

Parses the 16-byte header and slices PRG / CHR / trainer. Knows the four
header generations and implements the recommended detection procedure rather
than guessing from the magic bytes.

Also does **dump forensics**: old ROM managers scribbled signatures across
bytes 7-15, which silently inflates the mapper number by 64. Rather than
report mapper 68 for mapper 4, this detects the ASCII in the padding and masks
the high nybble back off, recording what it did as a warning.

Exposes `entry_points`, which is what makes vector-driven disassembly possible.

## `asm6502.py` — the assembler

Exists primarily to make the disassembler falsifiable. A listing that cannot be
re-encoded to its original bytes is decoration.

The interesting part is `_layout`. A zero-page operand widens to absolute when
its label resolves above `$FF`, which shifts every address after it — so a
single forward pass cannot know the instruction lengths. The layout pass
therefore repeats until sizes reach a fixed point (capped at 16 iterations).

## `disasm.py` — the analysis

Two strategies, because neither alone is honest:

| Strategy | Starts at | Strength | Failure mode |
|---|---|---|---|
| `linear` | first byte | complete coverage | renders data as instructions |
| `recursive` | interrupt vectors | real code, data separated | misses indirect dispatch |

`recursive` closes its failure mode by combining with `tables.py`: every
pointer in a detected table becomes an entry point, so handlers reached only
by an indexed load are still walked.

Output is a list of `Line` values, each tagged `code` / `data` / `word` /
`vector`. Rendering and JSON serialisation are separate from analysis, so a
new output format is a new function rather than a change to the walker.

## `tables.py` — indirect dispatch

Finds runs of consecutive little-endian words that all land inside PRG ROM.
Runs shorter than the threshold are dropped: two adjacent valid pointers occur
by chance constantly, four almost never do.

## `symbols.py` — memory between sessions

Reads FCEUX `.sym` (`C013:main`) and Mesen `.mlb` (`C013#main`), emits `.sym`.
User symbols override auto-generated labels, so an analysis improves
monotonically instead of restarting as `LC013` every time.

## `chrrom.py` — graphics

Two-bitplane tile decoding. Emits text or PGM deliberately: no imaging
dependency, so the package stays standard-library-only and installable
anywhere Python is.

---

## Design rules

1. **No runtime dependencies.** Standard library only. A tool people install
   into odd environments to look at one file must not drag in a dependency tree.
2. **No game data, ever.** Not in the package, not in the tests, not in CI.
   The test suite builds its own images. See `LEGAL.md`.
3. **The disassembler must be falsifiable.** `round_trip` is not an optional
   extra; it is how the tool earns trust.
4. **Analysis returns data, not text.** Rendering is a separate step so output
   formats can be added without touching the walker.
5. **Warnings, not exceptions, for malformed input.** Real dumps are messy. A
   truncated or mis-tagged image should still produce a usable result with the
   problems listed, not a stack trace.
