"""6502 disassembly with code/data separation.

Two strategies, because a linear sweep alone lies to you: real cartridges
interleave graphics tables, pointer tables and jump tables with code, and a
pure linear sweep happily renders a sprite as ``ORA ($41,X)``.

``linear``    decode every byte in order (fast, complete, sometimes wrong)
``recursive`` start at the interrupt vectors and follow every reachable
              branch/jump; anything not reached is emitted as data

The output is re-assemblable and is verified against the input by
:func:`round_trip`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from romforge.cpu6502 import (
    ADDRESSING_MODES,
    BRANCHES,
    JAM_OPCODES,
    OPCODES,
    RETURNS,
    UNSTABLE,
    decode,
    format_operand,
    operand_bytes,
)
from romforge.ines import RomImage


class Mode(str, Enum):
    LINEAR = "linear"
    RECURSIVE = "recursive"


class Kind(str, Enum):
    CODE = "code"
    DATA = "data"
    VECTOR = "vector"


@dataclass
class Line:
    address: int
    kind: Kind
    raw: bytes = b""
    mnemonic: str = ""
    mode: str = ""
    operand: int | None = None
    target: int | None = None
    label: str = ""
    official: bool = True
    unstable: bool = False
    comment: str = ""

    @property
    def size(self) -> int:
        return len(self.raw)

    def render(self) -> str:
        hexs = " ".join(f"{b:02X}" for b in self.raw)
        head = f"{self.label}:" if self.label else ""
        if self.kind is Kind.DATA:
            body = f".byte {' ,'.join(f'${b:02X}' for b in self.raw)}".replace(" ,", ", ")
        elif self.kind is Kind.VECTOR:
            val = self.operand or 0
            body = f".word ${val:04X}   ; {self.comment}"
        else:
            operand = format_operand(self.mode, self.operand or 0, self.address)
            body = f"{self.mnemonic:<4} {operand}".rstrip()
            notes = []
            if not self.official:
                notes.append("undocumented opcode")
            if self.unstable:
                notes.append("unstable on NMOS")
            if self.target is not None and self.mode in ("ABS", "ABX", "ABY", "IND", "REL", "IZX", "IZY"):
                notes.append(f"-> ${self.target:04X}")
            if notes:
                body += "   ; " + ", ".join(notes)
        left = f"{head:<24}" if head else " " * 24
        return f"${self.address:04X}:  {hexs:<9} {left}{body}"


@dataclass
class Disassembly:
    rom: RomImage
    mode: Mode
    base: int
    lines: list[Line] = field(default_factory=list)
    xrefs: dict[int, list[int]] = field(default_factory=dict)
    stats: dict[str, int] = field(default_factory=dict)

    def text(self) -> str:
        out = [
            f"; Disassembly of {self.rom.source_name}",
            f"; format={self.rom.fmt.value} mapper={self.rom.mapper} ({self.rom.mapper_name})",
            f"; prg={self.rom.prg_size} bytes chr={self.rom.chr_size} bytes mirroring={self.rom.mirroring}",
            f"; strategy={self.mode.value} base=${self.base:04X}",
            f"; code={self.stats.get('code', 0)} bytes data={self.stats.get('data', 0)} bytes",
            ";" + "=" * 66,
            f".org ${self.base:04X}",
            "",
        ]
        out += [ln.render() for ln in self.lines]
        return "\n".join(out) + "\n"

    def as_dict(self) -> dict[str, object]:
        return {
            "source": self.rom.source_name,
            "format": self.rom.fmt.value,
            "mapper": self.rom.mapper,
            "mode": self.mode.value,
            "base": self.base,
            "stats": self.stats,
            "lines": [
                {
                    "address": ln.address,
                    "kind": ln.kind.value,
                    "bytes": ln.raw.hex().upper(),
                    "mnemonic": ln.mnemonic or None,
                    "mode": ln.mode or None,
                    "operand": ln.operand,
                    "target": ln.target,
                    "label": ln.label or None,
                    "official": ln.official,
                }
                for ln in self.lines
            ],
        }


VECTOR_LABELS = {0xFFFA: "vec_nmi", 0xFFFC: "vec_reset", 0xFFFE: "vec_irq"}


def _reachable(prg: bytes, base: int, entries: list[int], limit: int | None = None) -> set[int]:
    """Offsets reachable by following branches, jumps and calls."""
    seen: set[int] = set()
    stack = [e - base for e in entries if base <= e < base + len(prg)]
    guard = limit if limit is not None else len(prg) * 8
    while stack and guard > 0:
        guard -= 1
        off = stack.pop()
        if off < 0 or off >= len(prg) or off in seen:
            continue
        info = decode(prg[off])
        if info is None:
            seen.add(off)
            continue
        mnem, mode, size, _official = info
        seen.add(off)
        if mnem in RETURNS or mnem in JAM_OPCODES and mode == "IMP":
            continue
        raw = prg[off:off + size]
        val = operand_bytes(mode, raw)
        if val is None:
            continue
        nxt = off + size
        if mnem in BRANCHES:
            disp = val - 256 if val >= 128 else val
            stack.append(nxt)
            stack.append(nxt + disp)
        elif mnem == "JMP":
            if mode == "IND":
                if base <= val < base + len(prg) - 1:
                    lo = prg[val - base]
                    hi = prg[val + 1 - base]
                    stack.append((lo | (hi << 8)) - base)
            else:
                stack.append(val - base)
        elif mnem == "JSR":
            stack.append(val - base)
            stack.append(nxt)
        else:
            stack.append(nxt)
    return seen


def disassemble(
    rom: RomImage,
    *,
    mode: Mode | str = Mode.RECURSIVE,
    base: int | None = None,
    start: int | None = None,
    end: int | None = None,
    entry_points: list[int] | None = None,
) -> Disassembly:
    """Disassemble ``rom.prg_rom``.

    ``base`` defaults to the address the PRG would occupy without bank
    switching. ``start``/``end`` restrict the range (useful for MMC-style
    images where only the last bank is fixed).
    """
    mode = Mode(mode)
    prg = rom.prg_rom
    if not prg:
        raise ValueError("image has no PRG ROM to disassemble")
    base = rom.base_address if base is None else base & 0xFFFF
    lo = (start - base) if start is not None else 0
    hi = (end - base) if end is not None else len(prg)
    lo = max(0, lo)
    hi = min(len(prg), hi)
    if hi <= lo:
        raise ValueError(f"empty range ${base + lo:04X}..${base + hi:04X}")

    entries = entry_points or [v for v in rom.entry_points.values()]
    code_offsets: set[int] | None = None
    if mode is Mode.RECURSIVE:
        code_offsets = _reachable(prg, base, entries or [base + hi - 1])
        code_offsets = {o for o in code_offsets if lo <= o < hi}

    lines: list[Line] = []
    xrefs: dict[int, list[int]] = {}
    code_bytes = data_bytes = illegal_bytes = 0
    off = lo
    data_run: list[int] = []

    def flush_data(until: int) -> None:
        nonlocal data_bytes, data_run
        while data_run and data_run[0] < until:
            chunk = data_run[:16]
            data_run = data_run[len(chunk):]
            addr = base + chunk[0]
            raw = bytes(prg[i] for i in chunk)
            data_bytes += len(raw)
            lines.append(Line(address=addr, kind=Kind.DATA, raw=raw))

    while off < hi:
        addr = base + off

        # The last six bytes of the final PRG bank are the interrupt vectors.
        # Emitting them inline keeps byte coverage exact in both strategies.
        if hi == len(prg) and addr in VECTOR_LABELS:
            o = len(prg) - (0x10000 - addr)
            value = prg[o] | (prg[o + 1] << 8)
            flush_data(off)
            lines.append(Line(
                address=addr, kind=Kind.VECTOR, raw=bytes(prg[o:o + 2]),
                operand=value, label=VECTOR_LABELS[addr],
                comment=f"-> ${value:04X}",
            ))
            data_bytes += 2
            off += 2
            continue

        is_code = True if code_offsets is None else (off in code_offsets)
        if not is_code:
            data_run.append(off)
            off += 1
            continue
        flush_data(off)
        info = decode(prg[off])
        if info is None:
            lines.append(Line(
                address=addr, kind=Kind.DATA, raw=bytes([prg[off]]),
                comment="undefined opcode",
            ))
            data_bytes += 1
            illegal_bytes += 1
            off += 1
            continue

        mnem, mmode, size, official = info
        raw = prg[off:off + size]
        if len(raw) < size:
            lines.append(Line(address=addr, kind=Kind.DATA, raw=raw, comment="truncated"))
            data_bytes += len(raw)
            off += len(raw)
            continue

        val = operand_bytes(mmode, raw) or 0
        target: int | None = None
        if mmode == "REL":
            disp = val - 256 if val >= 128 else val
            target = (addr + 2 + disp) & 0xFFFF
        elif mmode in ("ABS", "ABX", "ABY", "IND"):
            target = val
        if target is not None and base <= target < base + len(prg):
            xrefs.setdefault(target, []).append(addr)

        lines.append(Line(
            address=addr, kind=Kind.CODE, raw=raw, mnemonic=mnem, mode=mmode,
            operand=val, target=target, official=official,
            unstable=prg[off] in UNSTABLE,
        ))
        code_bytes += size
        off += size

    flush_data(hi)

    # Labels for anything that is a branch/jump target or has an xref.
    taken = set(xrefs)
    for ln in lines:
        if ln.kind is not Kind.CODE:
            continue
        if ln.address in VECTOR_LABELS:
            continue
        if ln.address in taken:
            ln.label = f"L{ln.address:04X}"

    stats = {
        "code": code_bytes,
        "data": data_bytes,
        "undefined_opcodes": illegal_bytes,
        "lines": len(lines),
        "entry_points": len(entries),
        "xref_targets": len(xrefs),
    }
    return Disassembly(rom=rom, mode=mode, base=base, lines=lines, xrefs=xrefs, stats=stats)


def round_trip(dis: Disassembly) -> dict[str, object]:
    """Re-encode the CODE lines and compare with the original bytes.

    Only code lines are checked: data is emitted verbatim, so including it
    would make the test vacuous. Returns a report with a boolean verdict.
    """
    from romforge.asm6502 import Assembler

    prg = dis.rom.prg_rom
    mismatches: list[dict[str, object]] = []
    checked = 0
    for ln in dis.lines:
        if ln.kind is not Kind.CODE or not ln.mnemonic:
            continue
        checked += 1
        offset = ln.address - dis.base
        if offset < 0 or offset >= len(prg):
            continue
        mode = ln.mode
        operand = ln.operand or 0
        if mode == "REL":
            target = ln.target or 0
            operand = (target - (ln.address + 2)) & 0xFF
        opcode = None
        for code, (mnem, m, _l, official) in OPCODES.items():
            if mnem == ln.mnemonic and m == mode and official == ln.official:
                opcode = code
                break
        if opcode is None:
            mismatches.append({"address": f"${ln.address:04X}", "reason": "no encoding"})
            continue
        rebuilt = bytes([opcode])
        need = ADDRESSING_MODES[mode][0]
        if need == 1:
            rebuilt += bytes([operand & 0xFF])
        elif need == 2:
            rebuilt += bytes([operand & 0xFF, (operand >> 8) & 0xFF])
        if rebuilt != ln.raw:
            mismatches.append({
                "address": f"${ln.address:04X}",
                "expected": ln.raw.hex().upper(),
                "rebuilt": rebuilt.hex().upper(),
            })
    return {
        "instructions_checked": checked,
        "mismatches": len(mismatches),
        "ok": not mismatches,
        "samples": mismatches[:10],
    }
