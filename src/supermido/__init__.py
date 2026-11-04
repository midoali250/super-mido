"""Cartridge-image analysis toolkit.

A tool for inspecting and disassembling iNES / NES 2.0 cartridge images that
**you** supply from cartridges **you** own. The package contains no game data,
no cartridge images, and no copyrighted material of any kind.

See ``docs/LEGAL.md`` for the policy this repository operates under.
"""

from __future__ import annotations

from supermido.disasm import Disassembly, Kind, Line, Mode, disassemble, round_trip
from supermido.ines import HeaderFormat, HeaderWarning, RomImage

__version__ = "0.2.0"

__all__ = [
    "Disassembly",
    "HeaderFormat",
    "HeaderWarning",
    "Kind",
    "Line",
    "Mode",
    "RomImage",
    "__version__",
    "disassemble",
    "round_trip",
]
