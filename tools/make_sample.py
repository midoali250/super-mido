#!/usr/bin/env python3
"""Build a synthetic cartridge image for manual testing and CI smoke tests.

The generated image is *this project's own work*: a tiny 6502 program the
script assembles itself, wrapped in a valid iNES header. It is written to a
path outside the repository by default, and ``.gitignore`` would refuse it
anyway.

Usage:
    python tools/make_sample.py --out /tmp/sample.nes
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from fixtures import RomSpec, build_rom  # noqa: E402

SAMPLE = """
    ; A tiny frame loop: waits for vblank, bumps a counter, forever.
    reset: sei
           cld
           ldx #$FF
           txs
           lda #$00
           sta $2000          ; disable NMI
           sta $2001          ; disable rendering
           sta frame_lo
           sta frame_hi

    main:  jsr wait_vblank
           inc frame_lo
           bne nowrap
           inc frame_hi
    nowrap:lda frame_lo
           and #$3F
           sta $2006
           jmp main

    wait_vblank:
           bit $2002
           bvc wait_vblank
           rts

    frame_lo: .byte $00
    frame_hi: .byte $00

    nmi:   rti
    irq:   rti
"""


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", required=True, help="where to write the synthetic image")
    p.add_argument("--mapper", type=int, default=0)
    p.add_argument("--prg-banks", type=int, default=1)
    p.add_argument("--chr-banks", type=int, default=1)
    args = p.parse_args()

    out = Path(args.out).expanduser()
    if args.out.startswith(".") or ROOT in out.resolve().parents:
        print("refusing to write inside the repository; choose a path outside it",
              file=sys.stderr)
        return 2

    spec = RomSpec(mapper=args.mapper, prg_banks=args.prg_banks,
                   chr_banks=args.chr_banks, mirroring="vertical")
    built = build_rom(SAMPLE, spec)
    out.write_bytes(built.data)
    print(f"wrote {out} ({len(built.data)} bytes)")
    print(f"  symbols: {', '.join(f'{k}=${v:04X}' for k, v in sorted(built.symbols.items()))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
