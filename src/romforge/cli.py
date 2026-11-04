"""Command-line interface.

Every command takes a cartridge image **path supplied by the user**. Nothing
here downloads, caches, or bundles game data. See ``docs/LEGAL.md``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from romforge import __version__
from romforge.chrrom import stats as chr_stats, to_pgm, to_text
from romforge.disasm import Mode, disassemble, round_trip
from romforge.ines import RomImage


def _load(path: str) -> RomImage:
    p = Path(path)
    if not p.is_file():
        raise SystemExit(f"error: no such file: {path}")
    return RomImage.load(p)


def cmd_inspect(args: argparse.Namespace) -> int:
    img = _load(args.rom)
    if args.json:
        print(json.dumps(img.summary(), indent=2, ensure_ascii=False))
        return 0
    s = img.summary()
    print(f"=== {s['file']} ===")
    for key in ("total_bytes", "format", "mapper", "mapper_name", "submapper",
                "mirroring", "four_screen", "battery", "trainer", "tv_system",
                "vs_unisystem", "playchoice", "prg_rom_bytes", "chr_rom_bytes",
                "trailing_bytes"):
        print(f"  {key:>20}: {s[key]}")
    print(f"  {'entry_points':>20}: " +
          ", ".join(f"{k}={v}" for k, v in s["entry_points"].items()))
    if s["warnings"]:
        print("  warnings:")
        for w in s["warnings"]:
            print(f"    - {w}")
    return 0


def cmd_disasm(args: argparse.Namespace) -> int:
    img = _load(args.rom)
    dis = disassemble(
        img,
        mode=Mode(args.mode),
        base=args.base,
        start=args.start,
        end=args.end,
    )
    if args.json:
        payload = dis.as_dict()
        payload["round_trip"] = round_trip(dis)
        text = json.dumps(payload, indent=2, ensure_ascii=False)
    else:
        text = dis.text()
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"wrote {args.output} ({len(text)} bytes)", file=sys.stderr)
        if not args.json:
            report = round_trip(dis)
            verdict = "PASS" if report["ok"] else "FAIL"
            print(
                f"round trip: {verdict} "
                f"({report['instructions_checked']} instructions, "
                f"{report['mismatches']} mismatches)",
                file=sys.stderr,
            )
    else:
        print(text)
    return 0


def cmd_chr(args: argparse.Namespace) -> int:
    img = _load(args.rom)
    if not img.chr_rom:
        print("no CHR ROM in this image (CHR-RAM board)", file=sys.stderr)
        return 1
    if args.pgm:
        data = to_pgm(img.chr_rom, columns=args.columns)
        out = Path(args.pgm)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(data)
        print(f"wrote {out} ({len(data)} bytes)", file=sys.stderr)
        return 0
    print(json.dumps(chr_stats(img.chr_rom), indent=2))
    print()
    print(to_text(img.chr_rom, tile_count=args.tiles, columns=args.columns))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    img = _load(args.rom)
    report = round_trip(disassemble(img, mode=Mode.LINEAR))
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 2


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="romforge",
        description="Inspect and disassemble cartridge images you supply yourself.",
        epilog="This tool ships no game data. See docs/LEGAL.md.",
    )
    p.add_argument("--version", action="version", version=f"romforge {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    def hexint(v: str) -> int:
        return int(v, 0)

    i = sub.add_parser("inspect", help="decode and validate the cartridge header")
    i.add_argument("rom")
    i.add_argument("--json", action="store_true")
    i.set_defaults(func=cmd_inspect)

    d = sub.add_parser("disasm", help="disassemble PRG ROM to 6502 assembly")
    d.add_argument("rom")
    d.add_argument("-m", "--mode", choices=[m.value for m in Mode], default=Mode.RECURSIVE.value,
                   help="recursive separates code from data; linear decodes every byte")
    d.add_argument("-o", "--output", help="write to a file instead of stdout")
    d.add_argument("--json", action="store_true", help="emit structured JSON")
    d.add_argument("-b", "--base", type=hexint, default=None,
                   help="override the PRG base address (for banked images)")
    d.add_argument("-s", "--start", type=hexint, default=None, help="first address to decode")
    d.add_argument("-e", "--end", type=hexint, default=None, help="last address to decode")
    d.set_defaults(func=cmd_disasm)

    c = sub.add_parser("chr", help="decode CHR ROM tiles")
    c.add_argument("rom")
    c.add_argument("--pgm", metavar="PATH", help="write the whole bank as a PGM image")
    c.add_argument("--tiles", type=int, default=8, help="how many tiles to print as text")
    c.add_argument("--columns", type=int, default=2)
    c.set_defaults(func=cmd_chr)

    v = sub.add_parser("verify", help="round-trip check: disassemble then re-encode")
    v.add_argument("rom")
    v.set_defaults(func=cmd_verify)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:  # piped into `head` and friends
        try:
            sys.stdout.close()
        finally:
            import os
            os._exit(0)
