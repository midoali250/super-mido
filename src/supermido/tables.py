"""Pointer and jump-table detection.

Cartridges store indirect dispatch as runs of 16-bit little-endian addresses
inside PRG ROM. A linear sweep renders those as nonsense instructions; a
vector-driven traversal never reaches them at all, because the only reference
to the table is an indexed load.

Detecting them does two useful things:

1. the bytes get emitted as ``.word`` entries instead of fake instructions
2. every target becomes a new entry point, so ``recursive`` mode can reach
   code that is only ever called indirectly
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PointerTable:
    offset: int          # byte offset into PRG ROM
    base: int            # CPU address the PRG is mapped at
    targets: list[int]   # decoded addresses, in table order

    @property
    def address(self) -> int:
        return self.base + self.offset

    @property
    def count(self) -> int:
        return len(self.targets)

    @property
    def byte_length(self) -> int:
        return self.count * 2


def find_pointer_tables(
    prg: bytes,
    base: int,
    *,
    min_length: int = 3,
    max_gap: int = 0,
) -> list[PointerTable]:
    """Find runs of consecutive words that all point inside PRG ROM.

    A word qualifies when, read as little-endian, it lands in
    ``[base, base+len(prg))``. Runs shorter than ``min_length`` are dropped --
    two adjacent valid pointers happen by chance, four almost never do.
    """
    lo, hi = base, base + len(prg)
    runs: list[PointerTable] = []
    off = 0
    last = len(prg) - 1
    while off < last:
        value = prg[off] | (prg[off + 1] << 8)
        if not (lo <= value < hi):
            off += 1
            continue
        # Walk forward two bytes at a time so the run is a sequence of whole
        # words, not overlapping byte pairs.
        targets: list[int] = []
        cur = off
        while cur < last:
            v = prg[cur] | (prg[cur + 1] << 8)
            if not (lo <= v < hi):
                break
            targets.append(v)
            cur += 2
        if len(targets) >= min_length:
            runs.append(PointerTable(offset=off, base=base, targets=targets))
            off = cur
        else:
            off += 1
    return runs


def table_spans(tables: list[PointerTable]) -> dict[int, int]:
    """Map offset -> 'table entry' for quick lookup during disassembly."""
    spans: dict[int, int] = {}
    for t in tables:
        for i in range(t.count):
            spans[t.offset + i * 2] = t.address
    return spans


def extra_entry_points(tables: list[PointerTable]) -> list[int]:
    """Every pointer target is reachable code the traversal would otherwise miss."""
    pts: list[int] = []
    seen: set[int] = set()
    for t in tables:
        for target in t.targets:
            if target not in seen:
                seen.add(target)
                pts.append(target)
    return sorted(pts)
