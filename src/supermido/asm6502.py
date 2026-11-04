"""A small two-pass 6502 assembler.

It exists for one reason: **round-trip verification**. A disassembler that
cannot prove its output re-assembles to the original bytes is just a pretty
printer. This module closes that loop, and it also lets the test suite build
synthetic cartridge images from readable source instead of shipping binaries.

Supports the official NMOS instruction set, labels, forward references, and
the ``.org`` / ``.byte`` / ``.word`` / ``.fill`` / ``.align`` directives.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from supermido.cpu6502 import ADDRESSING_MODES, OPCODES

_LINE_RE = re.compile(r"^\s*(?:(?P<label>[A-Za-z_.][A-Za-z0-9_.]*)\s*:\s*)?(?P<body>.*?)\s*$")
_COMMENT_RE = re.compile(r"(?<!\\);.*$")

# mnemonic -> {mode: opcode}
_BY_MNEMONIC: dict[str, dict[str, int]] = {}
for _code, (_mnem, _mode, _len, _official) in OPCODES.items():
    if _official:
        _BY_MNEMONIC.setdefault(_mnem, {})[_mode] = _code


class AssembleError(Exception):
    def __init__(self, message: str, lineno: int, text: str) -> None:
        super().__init__(f"line {lineno}: {message}: {text!r}")
        self.lineno = lineno
        self.text = text


@dataclass
class Instruction:
    mnemonic: str
    mode: str
    opcode: int
    operand: int | None      # numeric operand, if already resolved
    label_ref: str | None    # symbol name, if the operand was a label
    width: int               # operand width in bytes (1 or 2)
    is_branch: bool
    address: int


class Assembler:
    def __init__(self, origin: int = 0xC000) -> None:
        self.origin = origin & 0xFFFF

    # -- operand parsing ---------------------------------------------------
    _BRANCH_MNEMONICS = frozenset({"BPL", "BMI", "BVC", "BVS", "BCC", "BCS", "BNE", "BEQ"})

    @staticmethod
    def _parse_operand(mnemonic: str, text: str) -> tuple[str, int | None, str | None, int]:
        """Return ``(mode, value, label_ref, width)`` for an operand string.

        Two modes are *provisional* and get narrowed once the operand value is
        known: ``IZX_OR_ABSX_IND`` for ``($nn,X)`` and the zero-page family for
        bare operands, which widen to absolute when the target exceeds $FF.
        """
        s = text.strip()

        # Branches always encode a signed relative displacement.
        if mnemonic in Assembler._BRANCH_MNEMONICS:
            if not s:
                raise ValueError(f"{mnemonic} requires a target")
            return "REL", None, s, 1

        if not s:
            if "IMP" in _BY_MNEMONIC[mnemonic]:
                return "IMP", 0, None, 0
            if "ACC" in _BY_MNEMONIC[mnemonic]:
                return "ACC", 0, None, 0
            raise ValueError(f"{mnemonic} requires an operand")

        if s.upper() == "A" and "ACC" in _BY_MNEMONIC[mnemonic]:
            return "ACC", 0, None, 0

        m = re.fullmatch(r"\((.+?)\)\s*,\s*[Yy]", s)
        if m:
            return "IZY", None, m.group(1).strip(), 1

        # ($nn,X) is zero-page indexed indirect on the NMOS 6502; the 16-bit
        # ($nnnn,X) form only exists on the 65C02. Decide after evaluation.
        m = re.fullmatch(r"\((.+?)\s*,\s*[Xx]\)", s)
        if m:
            return "IZX_OR_ABSX_IND", None, m.group(1).strip(), 1

        m = re.fullmatch(r"\((.+?)\)", s)
        if m:
            return "IND", None, m.group(1).strip(), 2

        m = re.fullmatch(r"#(.+)", s)
        if m:
            return "IMM", None, m.group(1).strip(), 1

        m = re.fullmatch(r"(.+?)\s*,\s*[Xx]", s)
        if m:
            return "ZPX", None, m.group(1).strip(), 1

        m = re.fullmatch(r"(.+?)\s*,\s*[Yy]", s)
        if m:
            return "ZPY", None, m.group(1).strip(), 1

        return "ZPG", None, s, 1

    @staticmethod
    def _num(expr: str, symbols: dict[str, int], pc: int) -> int:
        e = expr.strip()
        for name in sorted(symbols, key=len, reverse=True):
            e = re.sub(rf"\b{re.escape(name)}\b", str(symbols[name]), e)
        e = e.replace("$", "0x").replace("%", "0b")
        e = re.sub(r"\b\*\b", str(pc), e)
        try:
            return int(eval(e, {"__builtins__": {}}, {})) & 0xFFFF  # noqa: S307
        except Exception as exc:  # pragma: no cover - surfaced with context
            raise ValueError(f"cannot evaluate {expr!r} ({exc})") from exc

    # -- passes ------------------------------------------------------------
    def assemble(self, source: str) -> tuple[bytes, dict[str, int]]:
        """Assemble ``source``, iterating until label addresses converge.

        Zero-page operands widen to absolute when a label resolves above $FF,
        which shifts every following address. A single forward pass cannot see
        that, so the sizing pass repeats until it reaches a fixed point.
        """
        parsed: list[tuple[str | None, str, int]] = []
        for lineno, raw in enumerate(source.splitlines(), start=1):
            body = _COMMENT_RE.sub("", raw)
            m = _LINE_RE.match(body)
            if not m:
                parsed.append((None, "", lineno))
                continue
            label = m.group("label")
            rest = m.group("body").strip()
            if label or rest:
                parsed.append((label, rest, lineno))

        # Tokenise into (kind, head, rest, lineno) once.
        items: list[tuple[str, str, str, int]] = []
        for _label, body, lineno in parsed:
            if not body:
                continue
            head, _, rest = body.partition(" ")
            head = head.strip()
            rest = rest.strip()
            kind = "dir" if head.startswith(".") else "ins"
            if kind == "ins" and head.upper() not in _BY_MNEMONIC:
                raise AssembleError(f"unknown mnemonic {head.upper()!r}", lineno, body)
            if kind == "dir" and head not in (".byte", ".word", ".fill", ".align"):
                raise AssembleError(f"unknown directive {head!r}", lineno, body)
            items.append((kind, head, rest, lineno))

        symbols: dict[str, int] = {}
        prev_sizes: list[int] | None = None
        for _attempt in range(16):
            symbols, sizes = self._layout(parsed, items, symbols)
            if sizes == prev_sizes:
                break
            prev_sizes = sizes
        else:  # pragma: no cover - pathological oscillation
            raise AssembleError("label addresses did not converge", 0, source)

        return self._encode(items, symbols, sizes), symbols

    def _layout(self, parsed, items, symbols: dict[str, int]):
        """Assign label addresses and per-item sizes."""
        syms = dict(symbols)
        pc = self.origin
        sizes: list[int] = []
        idx = 0
        for label, body, lineno in parsed:
            if label:
                if label in syms and syms[label] != pc:
                    raise AssembleError(f"duplicate label {label!r}", lineno, body)
                syms[label] = pc
            if not body:
                continue
            kind, head, rest, _ln = items[idx]
            idx += 1
            if kind == "dir":
                chunk = self._directive(head, rest, syms, pc)
                sizes.append(len(chunk))
                pc += len(chunk)
                continue
            mnem = head.upper()
            mode, _v, lbl, _w = self._parse_operand(mnem, rest)
            mode = self._resolve_mode(mnem, mode, lbl, syms, pc)
            size = 1 + ADDRESSING_MODES[mode][0]
            sizes.append(size)
            pc += size
        return syms, sizes

    def _encode(self, items, symbols: dict[str, int], sizes: list[int]) -> bytes:
        out = bytearray()
        pc = self.origin
        for (kind, head, rest, lineno), size in zip(items, sizes, strict=True):
            if kind == "dir":
                chunk = self._directive(head, rest, symbols, pc)
                if len(chunk) != size:  # pragma: no cover - layout must agree
                    raise AssembleError("directive size changed during encoding", lineno, rest)
                out += chunk
                pc += len(chunk)
                continue

            mnem = head.upper()
            mode, _v, lbl, _w = self._parse_operand(mnem, rest)
            mode = self._resolve_mode(mnem, mode, lbl, symbols, pc)
            need = ADDRESSING_MODES[mode][0]
            opcode = _BY_MNEMONIC[mnem][mode]

            if need == 0:
                operand = 0
            elif mode == "REL":
                target = self._num(lbl or rest, symbols, pc)
                disp = target - (pc + 2)
                if not -128 <= disp <= 127:
                    raise AssembleError(
                        f"branch target ${target:04X} is {disp} bytes away (max ±127)",
                        lineno, rest,
                    )
                operand = disp & 0xFF
            else:
                operand = self._num(lbl if lbl is not None else rest, symbols, pc)

            if need == 1 and not 0 <= operand <= 0xFF:
                raise AssembleError(f"operand ${operand:04X} does not fit one byte", lineno, rest)

            out.append(opcode)
            if need >= 1:
                out.append(operand & 0xFF)
            if need == 2:
                out.append((operand >> 8) & 0xFF)
            pc += 1 + need
        return bytes(out)

    def _directive(self, name: str, rest: str, symbols: dict[str, int], pc: int) -> bytes:
        parts = [p.strip() for p in rest.split(",")] if rest.strip() else []
        if name == ".byte":
            return bytes(self._num(p, symbols, pc) & 0xFF for p in parts)
        if name == ".word":
            out = bytearray()
            for p in parts:
                v = self._num(p, symbols, pc)
                out += bytes([v & 0xFF, (v >> 8) & 0xFF])
            return bytes(out)
        if name == ".fill":
            count = self._num(parts[0], symbols, pc)
            value = self._num(parts[1], symbols, pc) & 0xFF if len(parts) > 1 else 0
            return bytes([value]) * count
        if name == ".align":
            boundary = self._num(parts[0], symbols, pc) or 1
            value = self._num(parts[1], symbols, pc) & 0xFF if len(parts) > 1 else 0
            return bytes([value]) * ((-pc) % boundary)
        raise ValueError(f"unknown directive {name}")  # pragma: no cover

    @staticmethod
    def _resolve_mode(mnem: str, mode: str, label_ref: str | None,
                      symbols: dict[str, int], pc: int) -> str:
        """Narrow/widen provisional modes once the operand value is known."""
        table = _BY_MNEMONIC[mnem]

        if mode in ("IMP", "ACC", "IMM", "REL", "IND", "IZY", "ABS", "ABX", "ABY", "ABSX_IND"):
            if mode not in table:
                raise ValueError(f"{mnem} does not support {mode}")
            return mode

        expr = label_ref if label_ref is not None else ""
        try:
            value = Assembler._num(expr, symbols, pc)
        except ValueError:
            value = 0x100  # unresolved forward reference: assume absolute

        if mode == "IZX_OR_ABSX_IND":
            chosen = "IZX" if 0 <= value <= 0xFF else "ABSX_IND"
            if chosen in table:
                return chosen
            raise ValueError(f"{mnem} does not support indexed indirect")

        wide = {"ZPG": "ABS", "ZPX": "ABX", "ZPY": "ABY"}[mode]
        if 0 <= value <= 0xFF and mode in table:
            return mode
        if wide in table:
            return wide
        if mode in table:
            return mode
        raise ValueError(f"{mnem} supports neither {mode} nor {wide}")


def assemble_program(source: str, origin: int = 0xC000) -> tuple[bytes, dict[str, int]]:
    """Convenience wrapper around :class:`Assembler`."""
    return Assembler(origin=origin).assemble(source)
