"""Test fixtures built entirely from synthetic data.

This module is the reason the repository can stay free of third-party
copyrighted material: instead of shipping a cartridge image, the test suite
*manufactures* tiny, deterministic ones from 6502 source it assembles itself.

Nothing here reads, downloads, or embeds a commercial ROM.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from supermido.asm6502 import Assembler, assemble_program


@dataclass
class RomSpec:
    """Declarative description of a synthetic cartridge image."""

    prg_banks: int = 1            # 16 KiB each
    chr_banks: int = 1            # 8 KiB each; 0 => CHR-RAM board
    mapper: int = 0               # NROM
    submapper: int = 0
    mirroring: str = "horizontal"  # or "vertical"
    battery: bool = False
    trainer: bool = False
    four_screen: bool = False
    ines2: bool = False
    prg_fill: int = 0xEA          # NOP, so uninitialised space is valid code
    chr_pattern: str = "checker"
    label: str = "synthetic-test-cart"

    def prg_bytes(self) -> int:
        return self.prg_banks * 16384

    def chr_bytes(self) -> int:
        return self.chr_banks * 8192


@dataclass
class BuiltRom:
    data: bytes
    spec: RomSpec
    symbols: dict[str, int] = field(default_factory=dict)
    source: str = ""


def _chr_tiles(spec: RomSpec) -> bytes:
    """Generate deterministic tile graphics without any external asset."""
    total = spec.chr_bytes()
    if total == 0:
        return b""
    out = bytearray(total)
    if spec.chr_pattern == "checker":
        for i in range(total):
            out[i] = 0xAA if (i // 8) % 2 == 0 else 0x55
    elif spec.chr_pattern == "gradient":
        for i in range(total):
            out[i] = i & 0xFF
    elif spec.chr_pattern == "blank":
        pass
    else:  # "noise" - deterministic LCG so tests stay reproducible
        state = 0x12345678
        for i in range(total):
            state = (1103515245 * state + 12345) & 0xFFFFFFFF
            out[i] = (state >> 16) & 0xFF
    return bytes(out)


def build_header(spec: RomSpec) -> bytes:
    """Encode a 16-byte iNES / NES 2.0 header."""
    if spec.prg_bytes() % 16384:
        raise ValueError("PRG ROM must be a multiple of 16 KiB")
    if spec.chr_bytes() % 8192:
        raise ValueError("CHR ROM must be a multiple of 8 KiB")

    prg_units = spec.prg_bytes() // 16384
    chr_units = spec.chr_bytes() // 8192
    if prg_units > 0xFF or chr_units > 0xFF:
        raise ValueError("bank counts above 255 require the NES 2.0 large-size form")

    mapper_lo = spec.mapper & 0x0F
    mapper_hi = (spec.mapper >> 4) & 0x0F

    flags6 = mapper_lo << 4
    if spec.mirroring == "vertical":
        flags6 |= 0b0000_0001
    if spec.battery:
        flags6 |= 0b0000_0010
    if spec.trainer:
        flags6 |= 0b0000_0100
    if spec.four_screen:
        flags6 |= 0b0000_1000

    flags7 = mapper_hi << 4
    if spec.ines2:
        flags7 |= 0b0000_1000  # bits 3-2 == 0b10 selects NES 2.0

    flags8 = (spec.submapper << 4) if spec.ines2 else 0

    header = bytearray(16)
    header[0:4] = b"NES\x1a"
    header[4] = prg_units
    header[5] = chr_units
    header[6] = flags6
    header[7] = flags7
    header[8] = flags8
    # bytes 9..15 stay zero: the spec says padding must be zero, and a
    # non-zero tail is the classic sign of a tampered or mis-tagged dump.
    return bytes(header)


def build_rom(
    source: str = "",
    spec: RomSpec | None = None,
    *,
    reset_target: int | None = None,
    nmi_target: int | None = None,
    irq_target: int | None = None,
) -> BuiltRom:
    """Assemble ``source`` into a complete synthetic cartridge image.

    The 6502 interrupt vectors at $FFFA/$FFFC/$FFFE are filled in from the
    assembler's symbol table, exactly as a real cartridge would be.
    """
    spec = spec or RomSpec()
    prg_size = spec.prg_bytes()
    base = 0x10000 - prg_size if prg_size <= 0x8000 else 0x8000

    asm = Assembler(origin=base)
    symbols: dict[str, int] = {}
    code = b""
    if source.strip():
        code, symbols = asm.assemble(source)

    if len(code) > prg_size - 6:
        raise ValueError(
            f"assembled program is {len(code)} bytes; PRG ROM only holds {prg_size}"
        )

    prg = bytearray(bytes([spec.prg_fill]) * prg_size)
    prg[0:len(code)] = code

    # Interrupt vectors sit in the last six bytes of the final PRG bank:
    # NMI $FFFA, RESET $FFFC, IRQ $FFFE.
    tail = prg_size - 6

    def vec(addr: int, offset: int) -> None:
        prg[offset] = addr & 0xFF
        prg[offset + 1] = (addr >> 8) & 0xFF

    default = reset_target if reset_target is not None else symbols.get("reset", base)
    vec((nmi_target or symbols.get("nmi", default)) & 0xFFFF, tail + 0)  # NMI
    vec(default & 0xFFFF, tail + 2)                                     # RESET
    vec((irq_target or symbols.get("irq", default)) & 0xFFFF, tail + 4)  # IRQ

    trainer = bytes(512) if spec.trainer else b""
    data = build_header(spec) + trainer + bytes(prg) + _chr_tiles(spec)
    return BuiltRom(data=data, spec=spec, symbols=symbols, source=source)


def rom_from_bytes(
    prg: bytes,
    chr_rom: bytes = b"",
    *,
    mapper: int = 0,
    mirroring: str = "horizontal",
    ines2: bool = False,
    trainer: bool = False,
) -> bytes:
    """Wrap already-encoded PRG/CHR bytes in a valid header (no padding)."""
    if len(prg) % 16384:
        prg = prg + bytes(16384 - (len(prg) % 16384))
    if len(chr_rom) % 8192:
        chr_rom = chr_rom + bytes(8192 - (len(chr_rom) % 8192))
    spec = RomSpec(
        prg_banks=len(prg) // 16384,
        chr_banks=len(chr_rom) // 8192,
        mapper=mapper,
        mirroring=mirroring,
        ines2=ines2,
        trainer=trainer,
    )
    body = bytes(512) if trainer else b""
    return build_header(spec) + body + prg + chr_rom
