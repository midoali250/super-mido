"""6502 instruction set: official NMOS opcodes plus the undocumented ones
that NES cartridges actually use.

Every entry is ``(mnemonic, addressing_mode, length, official)`` where
``length`` is the encoded instruction size in bytes including the opcode.

The undocumented ("illegal") opcodes are documented from public reference
tables; unstable ones are flagged so a caller can warn instead of guessing.
"""

from __future__ import annotations

# Addressing mode -> (operand byte count, human template)
ADDRESSING_MODES: dict[str, tuple[int, str]] = {
    "IMP": (0, ""),
    "ACC": (0, "A"),
    "IMM": (1, "#${o:02X}"),
    "ZPG": (1, "${o:02X}"),
    "ZPX": (1, "${o:02X},X"),
    "ZPY": (1, "${o:02X},Y"),
    "ABS": (2, "${o:04X}"),
    "ABX": (2, "${o:04X},X"),
    "ABY": (2, "${o:04X},Y"),
    "IND": (2, "(${o:04X})"),
    "IZX": (1, "(${o:02X},X)"),
    "IZY": (1, "(${o:02X}),Y"),
    "REL": (1, "${o:04X}"),
    "ABSX_IND": (2, "(${o:04X},X)"),  # 65C02 only; on NMOS it is a JMP bug
}

# Instruction classes, used for control-flow analysis.
BRANCHES = frozenset({"BPL", "BMI", "BVC", "BVS", "BCC", "BCS", "BNE", "BEQ"})
JUMPS = frozenset({"JMP", "JSR"})
RETURNS = frozenset({"RTS", "RTI"})
HALTS = frozenset({"JAM"})
STORES = frozenset({"STA", "STX", "STY", "STZ", "SAX", "SHX", "SHY", "AHX", "TAS"})
LOADS = frozenset({"LDA", "LDX", "LDY", "LAX", "LAS"})


def _table() -> dict[int, tuple[str, str, int, bool]]:
    """Build the 256-entry opcode table."""
    t: dict[int, tuple[str, str, int, bool]] = {}

    def op(code: int, mnem: str, mode: str, official: bool = True) -> None:
        length = 1 + ADDRESSING_MODES[mode][0]
        t[code] = (mnem, mode, length, official)

    # --- official NMOS 6502 -------------------------------------------------
    official = {
        0x00: ("BRK", "IMP"), 0x01: ("ORA", "IZX"), 0x05: ("ORA", "ZPG"),
        0x06: ("ASL", "ZPG"), 0x08: ("PHP", "IMP"), 0x09: ("ORA", "IMM"),
        0x0A: ("ASL", "ACC"), 0x0D: ("ORA", "ABS"), 0x0E: ("ASL", "ABS"),
        0x10: ("BPL", "REL"), 0x11: ("ORA", "IZY"), 0x15: ("ORA", "ZPX"),
        0x16: ("ASL", "ZPX"), 0x18: ("CLC", "IMP"), 0x19: ("ORA", "ABY"),
        0x1D: ("ORA", "ABX"), 0x1E: ("ASL", "ABX"),
        0x20: ("JSR", "ABS"), 0x21: ("AND", "IZX"), 0x24: ("BIT", "ZPG"),
        0x25: ("AND", "ZPG"), 0x26: ("ROL", "ZPG"), 0x28: ("PLP", "IMP"),
        0x29: ("AND", "IMM"), 0x2A: ("ROL", "ACC"), 0x2C: ("BIT", "ABS"),
        0x2D: ("AND", "ABS"), 0x2E: ("ROL", "ABS"),
        0x30: ("BMI", "REL"), 0x31: ("AND", "IZY"), 0x35: ("AND", "ZPX"),
        0x36: ("ROL", "ZPX"), 0x38: ("SEC", "IMP"), 0x39: ("AND", "ABY"),
        0x3D: ("AND", "ABX"), 0x3E: ("ROL", "ABX"),
        0x40: ("RTI", "IMP"), 0x41: ("EOR", "IZX"), 0x45: ("EOR", "ZPG"),
        0x46: ("LSR", "ZPG"), 0x48: ("PHA", "IMP"), 0x49: ("EOR", "IMM"),
        0x4A: ("LSR", "ACC"), 0x4C: ("JMP", "ABS"), 0x4D: ("EOR", "ABS"),
        0x4E: ("LSR", "ABS"), 0x50: ("BVC", "REL"), 0x51: ("EOR", "IZY"),
        0x55: ("EOR", "ZPX"), 0x56: ("LSR", "ZPX"), 0x58: ("CLI", "IMP"),
        0x59: ("EOR", "ABY"), 0x5D: ("EOR", "ABX"), 0x5E: ("LSR", "ABX"),
        0x60: ("RTS", "IMP"), 0x61: ("ADC", "IZX"), 0x65: ("ADC", "ZPG"),
        0x66: ("ROR", "ZPG"), 0x68: ("PLA", "IMP"), 0x69: ("ADC", "IMM"),
        0x6A: ("ROR", "ACC"), 0x6C: ("JMP", "IND"), 0x6D: ("ADC", "ABS"),
        0x6E: ("ROR", "ABS"), 0x70: ("BVS", "REL"), 0x71: ("ADC", "IZY"),
        0x75: ("ADC", "ZPX"), 0x76: ("ROR", "ZPX"), 0x78: ("SEI", "IMP"),
        0x79: ("ADC", "ABY"), 0x7D: ("ADC", "ABX"), 0x7E: ("ROR", "ABX"),
        0x81: ("STA", "IZX"), 0x84: ("STY", "ZPG"), 0x85: ("STA", "ZPG"),
        0x86: ("STX", "ZPG"), 0x88: ("DEY", "IMP"), 0x8A: ("TXA", "IMP"),
        0x8C: ("STY", "ABS"), 0x8D: ("STA", "ABS"), 0x8E: ("STX", "ABS"),
        0x90: ("BCC", "REL"), 0x91: ("STA", "IZY"), 0x94: ("STY", "ZPX"),
        0x95: ("STA", "ZPX"), 0x96: ("STX", "ZPY"), 0x98: ("TYA", "IMP"),
        0x99: ("STA", "ABY"), 0x9A: ("TXS", "IMP"), 0x9D: ("STA", "ABX"),
        0xA0: ("LDY", "IMM"), 0xA1: ("LDA", "IZX"), 0xA2: ("LDX", "IMM"),
        0xA4: ("LDY", "ZPG"), 0xA5: ("LDA", "ZPG"), 0xA6: ("LDX", "ZPG"),
        0xA8: ("TAY", "IMP"), 0xA9: ("LDA", "IMM"), 0xAA: ("TAX", "IMP"),
        0xAC: ("LDY", "ABS"), 0xAD: ("LDA", "ABS"), 0xAE: ("LDX", "ABS"),
        0xB0: ("BCS", "REL"), 0xB1: ("LDA", "IZY"), 0xB4: ("LDY", "ZPX"),
        0xB5: ("LDA", "ZPX"), 0xB6: ("LDX", "ZPY"), 0xB8: ("CLV", "IMP"),
        0xB9: ("LDA", "ABY"), 0xBA: ("TSX", "IMP"), 0xBC: ("LDY", "ABX"),
        0xBD: ("LDA", "ABX"), 0xBE: ("LDX", "ABY"),
        0xC0: ("CPY", "IMM"), 0xC1: ("CMP", "IZX"), 0xC4: ("CPY", "ZPG"),
        0xC9: ("CMP", "IMM"),
        0xC5: ("CMP", "ZPG"), 0xC6: ("DEC", "ZPG"), 0xC8: ("INY", "IMP"),
        0xCA: ("DEX", "IMP"), 0xCC: ("CPY", "ABS"), 0xCD: ("CMP", "ABS"),
        0xCE: ("DEC", "ABS"), 0xD0: ("BNE", "REL"), 0xD1: ("CMP", "IZY"),
        0xD5: ("CMP", "ZPX"), 0xD6: ("DEC", "ZPX"), 0xD8: ("CLD", "IMP"),
        0xD9: ("CMP", "ABY"), 0xDD: ("CMP", "ABX"), 0xDE: ("DEC", "ABX"),
        0xE0: ("CPX", "IMM"), 0xE1: ("SBC", "IZX"), 0xE4: ("CPX", "ZPG"),
        0xE5: ("SBC", "ZPG"), 0xE6: ("INC", "ZPG"), 0xE8: ("INX", "IMP"),
        0xE9: ("SBC", "IMM"), 0xEA: ("NOP", "IMP"), 0xEC: ("CPX", "ABS"),
        0xED: ("SBC", "ABS"), 0xEE: ("INC", "ABS"), 0xF0: ("BEQ", "REL"),
        0xF1: ("SBC", "IZY"), 0xF5: ("SBC", "ZPX"), 0xF6: ("INC", "ZPX"),
        0xF8: ("SED", "IMP"), 0xF9: ("SBC", "ABY"), 0xFD: ("SBC", "ABX"),
        0xFE: ("INC", "ABX"),
    }
    for code, (mnem, mode) in official.items():
        op(code, mnem, mode, True)

    # --- undocumented NMOS opcodes -----------------------------------------
    # (mnemonic, mode). Behaviour notes live in UNSTABLE below.
    illegal = {
        0x02: ("NOP", "IMM"), 0x03: ("SLO", "IZX"), 0x04: ("NOP", "ZPG"),
        0x07: ("SLO", "ZPG"), 0x0B: ("ANC", "IMM"), 0x0C: ("NOP", "ABS"),
        0x0F: ("SLO", "ABS"), 0x12: ("NOP", "IMM"), 0x13: ("SLO", "IZY"),
        0x14: ("NOP", "ZPX"), 0x17: ("SLO", "ZPX"), 0x1A: ("NOP", "IMP"),
        0x1B: ("SLO", "ABY"), 0x1C: ("NOP", "ABX"), 0x1F: ("SLO", "ABX"),
        0x22: ("NOP", "IMM"), 0x23: ("RLA", "IZX"), 0x27: ("RLA", "ZPG"),
        0x2B: ("ANC", "IMM"), 0x2F: ("RLA", "ABS"), 0x32: ("NOP", "IMM"),
        0x33: ("RLA", "IZY"), 0x34: ("NOP", "ZPX"), 0x37: ("RLA", "ZPX"),
        0x3A: ("NOP", "IMP"), 0x3B: ("RLA", "ABY"), 0x3C: ("NOP", "ABX"),
        0x3F: ("RLA", "ABX"), 0x42: ("NOP", "IMM"), 0x43: ("SRE", "IZX"),
        0x44: ("NOP", "ZPG"), 0x47: ("SRE", "ZPG"), 0x4B: ("ALR", "IMM"),
        0x4F: ("SRE", "ABS"), 0x52: ("NOP", "IMM"), 0x53: ("SRE", "IZY"),
        0x54: ("NOP", "ZPX"), 0x57: ("SRE", "ZPX"), 0x5A: ("NOP", "IMP"),
        0x5B: ("SRE", "ABY"), 0x5C: ("NOP", "ABX"), 0x5F: ("SRE", "ABX"),
        0x62: ("NOP", "IMM"), 0x63: ("RRA", "IZX"), 0x64: ("NOP", "ZPG"),
        0x67: ("RRA", "ZPG"), 0x6B: ("ARR", "IMM"), 0x6F: ("RRA", "ABS"),
        0x72: ("NOP", "IMM"), 0x73: ("RRA", "IZY"), 0x74: ("NOP", "ZPX"),
        0x77: ("RRA", "ZPX"), 0x7A: ("NOP", "IMP"), 0x7B: ("RRA", "ABY"),
        0x7C: ("NOP", "ABX"), 0x7F: ("RRA", "ABX"), 0x80: ("NOP", "IMM"),
        0x82: ("NOP", "IMM"), 0x83: ("SAX", "IZX"), 0x87: ("SAX", "ZPG"),
        0x89: ("NOP", "IMM"), 0x8B: ("XAA", "IMM"), 0x8F: ("SAX", "ABS"),
        0x92: ("NOP", "IMM"), 0x93: ("AHX", "IZY"), 0x97: ("SAX", "ZPY"),
        0x9B: ("TAS", "ABY"), 0x9C: ("SHY", "ABX"), 0x9E: ("SHX", "ABY"),
        0x9F: ("AHX", "ABY"), 0xA3: ("LAX", "IZX"), 0xA7: ("LAX", "ZPG"),
        0xAB: ("LAX", "IMM"), 0xAF: ("LAX", "ABS"), 0xB2: ("NOP", "IMM"),
        0xB3: ("LAS", "ABY"), 0xB7: ("LAX", "ZPY"), 0xBB: ("LAS", "ABY"),
        0xBF: ("LAX", "ABY"), 0xC2: ("NOP", "IMM"), 0xC3: ("DCP", "IZX"),
        0xC6: ("DCP", "ZPG") if False else ("DEC", "ZPG"), 0xC7: ("DCP", "ZPG"),
        0xCB: ("AXS", "IMM"), 0xCF: ("DCP", "ABS"), 0xD2: ("NOP", "IMM"),
        0xD4: ("NOP", "ZPX"), 0xDA: ("NOP", "IMP"), 0xDC: ("NOP", "ABX"),
        0xF4: ("NOP", "ZPX"), 0xFA: ("NOP", "IMP"), 0xFC: ("NOP", "ABX"),
        0xD3: ("DCP", "IZY"), 0xD7: ("DCP", "ZPX"), 0xDB: ("DCP", "ABY"),
        0xDF: ("DCP", "ABX"), 0xE2: ("NOP", "IMM"), 0xE3: ("ISB", "IZX"),
        0xE7: ("ISB", "ZPG"), 0xEB: ("SBC", "IMM"), 0xEF: ("ISB", "ABS"),
        0xF2: ("NOP", "IMM"), 0xF3: ("ISB", "IZY"), 0xF7: ("ISB", "ZPX"),
        0xFB: ("ISB", "ABY"), 0xFF: ("ISB", "ABX"),
    }
    # 0xC6 is the official DEC ZPG; do not let the illegal map clobber it.
    illegal.pop(0xC6, None)
    for code, (mnem, mode) in illegal.items():
        if code in t:
            continue
        op(code, mnem, mode, False)

    # Opcode 0x02 family: some references treat these as a CPU lockup (JAM/KIL)
    # rather than a 2-byte NOP. Expose both readings via a dialect flag.
    return t


OPCODES: dict[int, tuple[str, str, int, bool]] = _table()

#: Opcodes whose effect depends on analog behaviour of the NMOS die and is
#: therefore not reliably reproducible. Disassembly still decodes them, but
#: callers should not treat a round-trip of these as proof of equivalence.
UNSTABLE = frozenset({0x8B, 0x93, 0x9B, 0x9C, 0x9E, 0x9F, 0xAB, 0xB3, 0xBB, 0xBF})

#: The seven JAM/KIL opcodes (lock the CPU until reset).
JAM_OPCODES = frozenset({0x02, 0x12, 0x22, 0x32, 0x42, 0x52, 0x62, 0x72, 0x92, 0xB2, 0xD2, 0xF2})


def decode(code: int) -> tuple[str, str, int, bool] | None:
    """Return ``(mnemonic, mode, length, official)`` or ``None`` if unknown."""
    return OPCODES.get(code)


def official_count() -> int:
    return sum(1 for v in OPCODES.values() if v[3])


def undocumented_count() -> int:
    return sum(1 for v in OPCODES.values() if not v[3])


def operand_bytes(mode: str, raw: bytes) -> int | None:
    """Decode the numeric operand for an addressing mode.

    ``raw`` must start at the opcode byte. Returns ``None`` when the operand
    is truncated, so callers can degrade gracefully instead of raising.
    """
    need = ADDRESSING_MODES[mode][0]
    if len(raw) < 1 + need:
        return None
    if need == 0:
        return 0
    if need == 1:
        return raw[1]
    return raw[1] | (raw[2] << 8)


def format_operand(mode: str, value: int, pc: int) -> str:
    """Render an operand. ``pc`` is the address of the opcode (for REL)."""
    if mode == "REL":
        disp = value - 256 if value >= 128 else value
        return "${0:04X}".format((pc + 2 + disp) & 0xFFFF)
    return ADDRESSING_MODES[mode][1].format(o=value)
