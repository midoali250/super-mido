"""Symbol files and pointer-table detection."""

import pytest
from fixtures import RomSpec, build_rom

from supermido.disasm import Kind, Mode, disassemble
from supermido.ines import RomImage
from supermido.symbols import SymbolTable, auto_name
from supermido.tables import extra_entry_points, find_pointer_tables, table_spans


def parse(text):
    return SymbolTable.parse(text, source="<test>")


def test_sym_dialect():
    t = parse("C000:reset\nC013:main\n; a comment\n\nC0FF:loop\n")
    assert t.labels == {0xC000: "reset", 0xC013: "main", 0xC0FF: "loop"}


def test_mlb_dialect():
    t = parse("C000#reset\nC013#main\n")
    assert t.labels[0xC000] == "reset"
    assert t.labels[0xC013] == "main"


def test_invalid_lines_are_rejected():
    with pytest.raises(ValueError):
        parse("not a symbol line")
    with pytest.raises(ValueError):
        parse("C000:1bad label")


def test_round_trip_render():
    t = parse("C000:reset\nC013:main")
    again = parse(t.render())
    assert again.labels == t.labels


def test_merge_later_wins():
    a = parse("C000:old")
    b = parse("C000:new\nC001:extra")
    merged = SymbolTable.merge(a, b)
    assert merged.labels[0xC000] == "new"
    assert merged.labels[0xC001] == "extra"


def test_save_and_load(tmp_path):
    p = tmp_path / "game.sym"
    parse("C000:reset").save(p)
    assert SymbolTable.load(p).labels == {0xC000: "reset"}
    assert p.read_text().startswith(";")


def test_auto_name_format():
    assert auto_name(0xC013) == "LC013"
    assert auto_name(0x12, kind="T") == "T0012"


# --- pointer tables -------------------------------------------------------

def test_finds_a_run_of_valid_pointers():
    base = 0xC000
    prg = bytearray(16384)
    table = 0x100
    for i, target in enumerate([0xC000, 0xC010, 0xC020, 0xC030, 0xC040]):
        prg[table + i * 2] = target & 0xFF
        prg[table + i * 2 + 1] = target >> 8
    tables = find_pointer_tables(bytes(prg), base, min_length=4)
    assert len(tables) == 1
    t = tables[0]
    assert t.offset == table
    assert t.address == base + table
    assert t.count == 5
    assert t.targets[0] == 0xC000 and t.targets[-1] == 0xC040
    assert t.byte_length == 10


def test_short_runs_are_rejected():
    base = 0xC000
    prg = bytearray(16384)
    for i, target in enumerate([0xC000, 0xC010]):
        prg[0x100 + i * 2] = target & 0xFF
        prg[0x100 + i * 2 + 1] = target >> 8
    assert find_pointer_tables(bytes(prg), base, min_length=4) == []


def test_pointers_outside_prg_break_the_run():
    """$0200 is RAM, not PRG -- it must split the run in two."""
    base = 0xC000
    prg = bytearray(16384)
    words = [0xC000, 0xC010, 0x0200, 0xC020, 0xC030, 0xC040]
    for i, w in enumerate(words):
        prg[0x100 + i * 2] = w & 0xFF
        prg[0x100 + i * 2 + 1] = w >> 8
    tables = find_pointer_tables(bytes(prg), base, min_length=3)
    assert len(tables) == 1
    assert tables[0].offset == 0x106          # the run restarts after the bad word
    assert tables[0].targets == [0xC020, 0xC030, 0xC040]


def test_spans_and_entry_points():
    base = 0xC000
    prg = bytearray(16384)
    for i, target in enumerate([0xC000, 0xC010, 0xC020, 0xC030]):
        prg[0x100 + i * 2] = target & 0xFF
        prg[0x100 + i * 2 + 1] = target >> 8
    tables = find_pointer_tables(bytes(prg), base, min_length=4)
    spans = table_spans(tables)
    assert spans[0x100] == base + 0x100
    assert 0x106 in spans and 0x107 not in spans
    assert extra_entry_points(tables) == [0xC000, 0xC010, 0xC020, 0xC030]


def test_disasm_emits_word_entries_and_follows_the_table():
    """A table target is unreachable from the vectors until detection runs."""
    base = 0xC000
    src = "reset: jmp reset\n    nmi: rti\n    irq: rti"
    built = build_rom(src)
    prg = bytearray(built.data[16 : 16 + 16384])

    # Hidden handler, never referenced by a branch or jump.
    handler = 0x200
    prg[handler : handler + 3] = bytes([0xA9, 0x42, 0x60])   # lda #$42 / rts
    # The table that dispatches to it.
    tbl = 0x100
    for i, off in enumerate([0x000, handler, 0x003, 0x005]):
        target = base + off
        prg[tbl + i * 2] = target & 0xFF
        prg[tbl + i * 2 + 1] = target >> 8
    data = built.data[:16] + bytes(prg) + built.data[16 + 16384 :]
    img = RomImage.from_bytes(data)

    plain = disassemble(img, mode=Mode.RECURSIVE, detect_tables=False)
    assert not any(ln.kind is Kind.WORD for ln in plain.lines)

    found = disassemble(img, mode=Mode.RECURSIVE, detect_tables=True)
    assert found.stats["pointer_tables"] >= 1
    words = [ln for ln in found.lines if ln.kind is Kind.WORD]
    assert words, "table entries were not emitted as .word"
    assert any(ln.operand == base + handler for ln in words)


def test_symbols_override_auto_labels():
    src = "reset: nop\n    loop: jmp loop\n    nmi: rti\n    irq: rti"
    built = build_rom(src)
    img = RomImage.from_bytes(built.data)

    bare = disassemble(img, mode=Mode.RECURSIVE)
    assert any(ln.label.startswith("L") for ln in bare.lines)

    named = disassemble(
        img, mode=Mode.RECURSIVE,
        symbols=SymbolTable.parse(f"{built.symbols['loop']:04X}:main_loop"),
    )
    assert any(ln.label == "main_loop" for ln in named.lines)
    assert not any(ln.label == f"L{built.symbols['loop']:04X}" for ln in named.lines)
