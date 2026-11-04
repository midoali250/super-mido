"""iNES / NES 2.0 cartridge-header parsing and validation.

Header layout and the recommended format-detection procedure follow the
public NESdev iNES specification. This module reads cartridge *images*; it
never ships, downloads, or embeds one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

MAGIC = b"NES\x1a"
HEADER_SIZE = 16
PRG_BANK = 16384
CHR_BANK = 8192
TRAINER_SIZE = 512

#: Vector addresses in the final PRG bank.
VECTOR_NMI = 0xFFFA
VECTOR_RESET = 0xFFFC
VECTOR_IRQ = 0xFFFE

# A small, non-exhaustive map of the most common boards. Numbers are the
# public iNES mapper numbering scheme; names are hardware descriptors, not
# product branding.
MAPPER_NAMES: dict[int, str] = {
    0: "NROM",
    1: "MMC1",
    2: "UxROM",
    3: "CNROM",
    4: "MMC3",
    5: "MMC5",
    7: "AxROM",
    9: "MMC2",
    10: "MMC4",
    11: "Color Dreams",
    40: "Multicart (SMB2j pirate)",
    66: "GxROM",
    71: "Camerica/Codemasters",
    228: "Active Enterprises",
}


class HeaderFormat(str, Enum):
    ARCHAIC = "archaic-ines"
    INES_0_7 = "ines-0.7"
    INES = "ines"
    NES_2_0 = "nes-2.0"
    UNKNOWN = "unknown"


class HeaderWarning(str, Enum):
    BAD_MAGIC = "bad-magic"
    TOO_SMALL = "file-smaller-than-header"
    TRUNCATED_PRG = "prg-rom-truncated"
    TRUNCATED_CHR = "chr-rom-truncated"
    NONZERO_PADDING = "nonzero-padding-bytes"
    DISKDUDE = "ripper-signature-in-header"
    MAPPER_HIGH_NYBBLE_MASKED = "mapper-high-nybble-masked"
    CHR_ZERO_MEANS_RAM = "chr-rom-zero-uses-chr-ram"
    VECTORS_UNINITIALISED = "reset-vector-not-set"
    PAL_FLAG = "pal-tv-system-flag"
    VS_UNISYSTEM = "vs-unisystem-flag"
    PLAYCHOICE = "playchoice-10-flag"
    FOUR_SCREEN = "four-screen-vram"
    BATTERY = "battery-backed"
    TRAINER = "trainer-present"


@dataclass
class RomImage:
    """A parsed cartridge image."""

    data: bytes
    source_name: str = "<memory>"

    fmt: HeaderFormat = HeaderFormat.UNKNOWN
    mapper: int = 0
    mapper_raw: int = 0
    submapper: int = 0
    prg_rom: bytes = b""
    chr_rom: bytes = b""
    trainer: bytes = b""
    trailing: bytes = b""
    mirroring: str = "horizontal"
    four_screen: bool = False
    battery: bool = False
    has_trainer: bool = False
    vs_unisystem: bool = False
    playchoice: bool = False
    tv_system: str = "ntsc"
    padding: bytes = b""
    warnings: list[HeaderWarning] = field(default_factory=list)

    # -- construction ------------------------------------------------------
    @classmethod
    def from_bytes(cls, data: bytes, source_name: str = "<memory>") -> "RomImage":
        img = cls(data=data, source_name=source_name)
        img._parse()
        return img

    @classmethod
    def load(cls, path: str | Path) -> "RomImage":
        p = Path(path)
        return cls.from_bytes(p.read_bytes(), source_name=p.name)

    # -- parsing -----------------------------------------------------------
    def _parse(self) -> None:
        d = self.data
        if len(d) < HEADER_SIZE:
            self.warnings.append(HeaderWarning.TOO_SMALL)
            self.fmt = HeaderFormat.UNKNOWN
            return
        if d[0:4] != MAGIC:
            self.warnings.append(HeaderWarning.BAD_MAGIC)

        prg_units, chr_units = d[4], d[5]
        flags6, flags7, flags8, flags9 = d[6], d[7], d[8], d[9]
        self.padding = d[12:16]

        # Recommended detection procedure (NESdev iNES).
        sel = flags7 & 0x0C
        if sel == 0x08:
            self.fmt = HeaderFormat.NES_2_0
        elif sel == 0x04:
            self.fmt = HeaderFormat.ARCHAIC
        elif sel == 0x00 and self.padding == b"\x00\x00\x00\x00":
            self.fmt = HeaderFormat.INES
        else:
            self.fmt = HeaderFormat.INES_0_7

        self.mirroring = "vertical" if flags6 & 0x01 else "horizontal"
        self.battery = bool(flags6 & 0x02)
        self.has_trainer = bool(flags6 & 0x04)
        self.four_screen = bool(flags6 & 0x08)
        self.vs_unisystem = bool(flags7 & 0x01)
        self.playchoice = bool(flags7 & 0x02)

        # Mapper number.
        self.mapper_raw = (flags6 >> 4) | (flags7 & 0xF0)
        self.mapper = self.mapper_raw
        if self.fmt is HeaderFormat.NES_2_0:
            self.mapper |= (flags8 & 0x0F) << 8
            self.submapper = (flags8 >> 4) & 0x0F
        elif self.padding != b"\x00\x00\x00\x00":
            # "DiskDude!" and friends scribble over bytes 7-15, which inflates
            # the mapper by 64. Mask the high nybble back off.
            if any(32 <= b < 127 for b in d[7:16]):
                self.warnings.append(HeaderWarning.DISKDUDE)
            masked = self.mapper_raw & 0x0F
            if masked != self.mapper_raw:
                self.mapper = masked
                self.warnings.append(HeaderWarning.MAPPER_HIGH_NYBBLE_MASKED)
            else:
                self.mapper = masked
            self.warnings.append(HeaderWarning.NONZERO_PADDING)

        if self.vs_unisystem:
            self.warnings.append(HeaderWarning.VS_UNISYSTEM)
        if self.playchoice:
            self.warnings.append(HeaderWarning.PLAYCHOICE)
        if self.four_screen:
            self.warnings.append(HeaderWarning.FOUR_SCREEN)
        if self.battery:
            self.warnings.append(HeaderWarning.BATTERY)
        if self.has_trainer:
            self.warnings.append(HeaderWarning.TRAINER)
        if chr_units == 0:
            self.warnings.append(HeaderWarning.CHR_ZERO_MEANS_RAM)
        if flags9 & 0x01:
            self.tv_system = "pal"
            self.warnings.append(HeaderWarning.PAL_FLAG)

        # Slice the body.
        off = HEADER_SIZE
        if self.has_trainer:
            self.trainer = d[off:off + TRAINER_SIZE]
            off += TRAINER_SIZE
        prg_size = prg_units * PRG_BANK
        chr_size = chr_units * CHR_BANK
        self.prg_rom = d[off:off + prg_size]
        if len(self.prg_rom) < prg_size:
            self.warnings.append(HeaderWarning.TRUNCATED_PRG)
        off += len(self.prg_rom)
        self.chr_rom = d[off:off + chr_size]
        if len(self.chr_rom) < chr_size:
            self.warnings.append(HeaderWarning.TRUNCATED_CHR)
        off += len(self.chr_rom)
        self.trailing = d[off:]

    # -- accessors ---------------------------------------------------------
    @property
    def prg_size(self) -> int:
        return len(self.prg_rom)

    @property
    def chr_size(self) -> int:
        return len(self.chr_rom)

    @property
    def base_address(self) -> int:
        """CPU address where PRG ROM is mapped, assuming no bank switching."""
        return (0x10000 - self.prg_size) & 0xFFFF if self.prg_size else 0x8000

    def vector(self, which: str) -> int | None:
        """Read an interrupt vector from the last PRG bank."""
        addr = {"nmi": VECTOR_NMI, "reset": VECTOR_RESET, "irq": VECTOR_IRQ}[which]
        if not self.prg_rom:
            return None
        off = self.prg_size - (0x10000 - addr)
        if off < 0 or off + 1 >= self.prg_size:
            return None
        lo, hi = self.prg_rom[off], self.prg_rom[off + 1]
        return lo | (hi << 8)

    @property
    def entry_points(self) -> dict[str, int]:
        pts = {}
        for name in ("reset", "nmi", "irq"):
            v = self.vector(name)
            if v is not None:
                pts[name] = v
                if name == "reset" and v in (0x0000, 0xFFFF):
                    self.warnings.append(HeaderWarning.VECTORS_UNINITIALISED)
        return pts

    @property
    def mapper_name(self) -> str:
        return MAPPER_NAMES.get(self.mapper, f"mapper {self.mapper}")

    def summary(self) -> dict[str, object]:
        return {
            "file": self.source_name,
            "total_bytes": len(self.data),
            "format": self.fmt.value,
            "mapper": self.mapper,
            "mapper_name": self.mapper_name,
            "submapper": self.submapper,
            "mirroring": self.mirroring,
            "four_screen": self.four_screen,
            "battery": self.battery,
            "trainer": self.has_trainer,
            "tv_system": self.tv_system,
            "vs_unisystem": self.vs_unisystem,
            "playchoice": self.playchoice,
            "prg_rom_bytes": self.prg_size,
            "chr_rom_bytes": self.chr_size,
            "trailing_bytes": len(self.trailing),
            "entry_points": {k: f"${v:04X}" for k, v in self.entry_points.items()},
            "warnings": [w.value for w in self.warnings],
        }
