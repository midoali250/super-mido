"""CHR-ROM tile decoding.

The NES PPU stores tiles as two bitplanes per row: byte *n* holds bit 0 of
each of eight pixels, byte *n+8* holds bit 1. This module turns that into
something a human can look at, without pulling in an imaging dependency --
output is text or PGM (netpbm), which any viewer or ImageMagick can open.

Tile data is geometry, not expression: dumping it is how you identify which
bank holds which graphics while mapping a cartridge.
"""

from __future__ import annotations

from dataclasses import dataclass

TILE_BYTES = 16
TILE_PX = 8


@dataclass
class Tile:
    index: int
    pixels: tuple[tuple[int, ...], ...]  # 8 rows of 8 values, 0..3

    def ascii_art(self, glyphs: str = " .:+") -> list[str]:
        return ["".join(glyphs[min(p, len(glyphs) - 1)] for p in row) for row in self.pixels]


def decode_tile(data: bytes, index: int = 0) -> Tile:
    """Decode one 16-byte tile. ``data`` must be at least 16 bytes."""
    if len(data) < TILE_BYTES:
        raise ValueError(f"tile needs {TILE_BYTES} bytes, got {len(data)}")
    rows = []
    for y in range(TILE_PX):
        lo, hi = data[y], data[y + TILE_PX]
        rows.append(tuple(((hi >> (7 - x)) & 1) * 2 + ((lo >> (7 - x)) & 1) for x in range(TILE_PX)))
    return Tile(index=index, pixels=tuple(rows))


def decode_chr(chr_rom: bytes) -> list[Tile]:
    """Decode every 8x8 tile in a CHR bank."""
    return [decode_tile(chr_rom[i:i + TILE_BYTES], i // TILE_BYTES)
            for i in range(0, len(chr_rom) - TILE_BYTES + 1, TILE_BYTES)]


def to_pgm(chr_rom: bytes, columns: int = 16) -> bytes:
    """Render a CHR bank as a PGM (P5) image, ``columns`` tiles wide."""
    tiles = decode_chr(chr_rom)
    if not tiles:
        raise ValueError("CHR ROM is empty (this board probably uses CHR-RAM)")
    rows = (len(tiles) + columns - 1) // columns
    width, height = columns * TILE_PX, rows * TILE_PX
    canvas = bytearray(width * height)
    for t in tiles:
        tx = (t.index % columns) * TILE_PX
        ty = (t.index // columns) * TILE_PX
        for y, row in enumerate(t.pixels):
            for x, value in enumerate(row):
                canvas[(ty + y) * width + tx + x] = value * 85  # 0,85,170,255
    header = f"P5\n{width} {height}\n255\n".encode("ascii")
    return header + bytes(canvas)


def to_text(chr_rom: bytes, tile_count: int = 8, columns: int = 2) -> str:
    """Render the first ``tile_count`` tiles as text, for a terminal."""
    tiles = decode_chr(chr_rom)[:tile_count]
    if not tiles:
        return "(no CHR ROM)"
    blocks: list[list[str]] = [[] for _ in range(columns)]
    for i, t in enumerate(tiles):
        col = blocks[i % columns]
        col.append(f"-- tile {t.index} (${t.index * TILE_BYTES:04X})")
        col.extend(t.ascii_art())
        col.append("")
    height = max(len(b) for b in blocks)
    out = []
    for y in range(height):
        out.append("   ".join((b[y] if y < len(b) else "").ljust(28) for b in blocks))
    return "\n".join(out)


def stats(chr_rom: bytes) -> dict[str, object]:
    """Cheap heuristics that help spot which banks are graphics vs. padding."""
    tiles = decode_chr(chr_rom)
    blank = sum(1 for t in tiles if all(v == 0 for row in t.pixels for v in row))
    solid = sum(1 for t in tiles
                if len({v for row in t.pixels for v in row}) == 1 and not all(
                    v == 0 for row in t.pixels for v in row))
    return {
        "bytes": len(chr_rom),
        "tiles": len(tiles),
        "blank_tiles": blank,
        "solid_tiles": solid,
        "used_tiles": len(tiles) - blank,
        "distinct_values": sorted({v for t in tiles for row in t.pixels for v in row}),
    }
