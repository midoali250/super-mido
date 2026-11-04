"""CHR tile decoding."""

import pytest
from fixtures import RomSpec, build_rom

from romforge.chrrom import decode_chr, decode_tile, stats, to_pgm, to_text
from romforge.ines import RomImage


def test_tile_decodes_two_bitplanes():
    # bit0 plane = row0, bit1 plane = row8. Values 0..3 per pixel.
    data = bytes([0b1010_0101, 0, 0, 0, 0, 0, 0, 0,
                  0b0000_1111, 0, 0, 0, 0, 0, 0, 0])
    tile = decode_tile(data)
    # lo plane byte = 0b1010_0101, hi plane byte = 0b0000_1111
    # value = hi*2 + lo per pixel, MSB first.
    assert tile.pixels[0] == (1, 0, 1, 0, 2, 3, 2, 3)


def test_tile_requires_16_bytes():
    with pytest.raises(ValueError):
        decode_tile(b"\x00" * 15)


def test_decode_chr_counts_tiles():
    tiles = decode_chr(bytes(8192))
    assert len(tiles) == 8192 // 16 == 512
    assert [t.index for t in tiles[:3]] == [0, 1, 2]


def test_blank_and_solid_detection():
    blank = bytes(8192)
    s = stats(blank)
    assert s["tiles"] == 512
    assert s["blank_tiles"] == 512
    assert s["used_tiles"] == 0

    solid = bytes([0xFF] * 8192)
    s2 = stats(solid)
    assert s2["blank_tiles"] == 0
    assert s2["solid_tiles"] == 512
    assert s2["distinct_values"] == [3]


def test_pgm_header_and_pixel_count():
    rom = RomImage.from_bytes(build_rom(spec=RomSpec(chr_pattern="gradient")).data)
    pgm = to_pgm(rom.chr_rom, columns=16)
    assert pgm.startswith(b"P5\n")
    header, _, body = pgm.partition(b"255\n")
    width, height = (int(x) for x in header.decode().split("\n")[1].split())
    assert width == 16 * 8
    assert height == (512 // 16) * 8
    assert len(body) == width * height


def test_pgm_rejects_empty_chr():
    rom = RomImage.from_bytes(build_rom(spec=RomSpec(chr_banks=0)).data)
    with pytest.raises(ValueError):
        to_pgm(rom.chr_rom)


def test_text_render_is_stable():
    rom = RomImage.from_bytes(build_rom(spec=RomSpec(chr_pattern="checker")).data)
    txt = to_text(rom.chr_rom, tile_count=4, columns=2)
    assert "tile 0" in txt
    assert "tile 3" in txt
    assert len(txt.splitlines()) > 8
