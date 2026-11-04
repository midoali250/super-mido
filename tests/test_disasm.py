"""Disassembly strategies, code/data separation, and round-trip verification."""

import pytest
from fixtures import RomSpec, build_rom

from supermido.disasm import Kind, Mode, disassemble, round_trip
from supermido.ines import RomImage

BOOT = """
    reset: sei
           ldx #$FF
           txs
           lda #$00
           sta $2000
    loop:  jsr frame
           jmp loop
    frame: lda $2002
           and #$80
           beq frame
           rts
    nmi:   rti
    irq:   rti
"""


def image(src=BOOT, **spec_kw):
    return RomImage.from_bytes(build_rom(src, RomSpec(**spec_kw)).data, "synthetic.nes")


def test_recursive_mode_starts_at_the_reset_vector():
    dis = disassemble(image(), mode=Mode.RECURSIVE)
    code = [ln for ln in dis.lines if ln.kind is Kind.CODE]
    assert code, "recursive traversal found no code"
    assert code[0].address == dis.rom.entry_points["reset"]
    assert dis.stats["code"] > 0


def test_recursive_separates_unreachable_data():
    dis = disassemble(image(), mode=Mode.RECURSIVE)
    kinds = {ln.kind for ln in dis.lines}
    assert Kind.CODE in kinds
    assert Kind.DATA in kinds  # the NOP-filled slack space is unreachable
    assert dis.stats["data"] > 0


def test_linear_mode_covers_every_byte():
    dis = disassemble(image(), mode=Mode.LINEAR)
    covered = sum(ln.size for ln in dis.lines)
    assert covered == dis.rom.prg_size


def test_labels_are_generated_for_branch_targets():
    dis = disassemble(image(), mode=Mode.RECURSIVE)
    labelled = [ln for ln in dis.lines if ln.label and ln.kind is Kind.CODE]
    assert any(ln.label.startswith("L") for ln in labelled)


def test_vector_lines_are_emitted_at_the_end_of_prg():
    dis = disassemble(image(), mode=Mode.LINEAR)
    vecs = {ln.address: ln for ln in dis.lines if ln.kind is Kind.VECTOR}
    assert set(vecs) == {0xFFFA, 0xFFFC, 0xFFFE}
    assert vecs[0xFFFC].label == "vec_reset"
    assert vecs[0xFFFC].operand == dis.rom.entry_points["reset"]


def test_xrefs_are_recorded_for_absolute_operands():
    dis = disassemble(image(), mode=Mode.LINEAR)
    assert dis.stats["xref_targets"] >= 1
    # every xref target points at an address inside PRG
    for target in dis.xrefs:
        assert dis.base <= target < dis.base + dis.rom.prg_size


def test_round_trip_is_byte_exact():
    for mode in (Mode.LINEAR, Mode.RECURSIVE):
        dis = disassemble(image(), mode=mode)
        report = round_trip(dis)
        assert report["ok"], report["samples"]
        assert report["instructions_checked"] > 0


def test_round_trip_survives_undocumented_opcodes():
    """Cartridges use illegal opcodes; decoding must not break the round trip."""
    src = "reset: nop\n"
    built = build_rom(src, RomSpec(prg_fill=0xEA))
    prg = bytearray(built.data[16 : 16 + 16384])
    prg[0:8] = bytes([0x03, 0x10, 0x07, 0x00, 0x0B, 0x55, 0x4B, 0x88])  # SLO/ANC/ALR
    data = built.data[:16] + bytes(prg) + built.data[16 + 16384 :]
    dis = disassemble(RomImage.from_bytes(data), mode=Mode.LINEAR)
    decoded = [ln.mnemonic for ln in dis.lines[:4] if ln.kind is Kind.CODE]
    assert "SLO" in decoded
    assert round_trip(dis)["ok"]


def test_range_restriction():
    dis = disassemble(image(), mode=Mode.LINEAR, start=0xFF00, end=0xFFFF)
    assert all(0xFF00 <= ln.address < 0xFFFF for ln in dis.lines)


def test_base_override_for_banked_images():
    img = image(src=BOOT, prg_banks=2)
    assert img.base_address == 0x8000
    dis = disassemble(img, mode=Mode.LINEAR, base=0xC000)
    assert dis.base == 0xC000


def test_empty_range_is_an_error():
    with pytest.raises(ValueError):
        disassemble(image(), mode=Mode.LINEAR, start=0xC100, end=0xC100)


def test_chr_ram_image_still_disassembles():
    dis = disassemble(image(src=BOOT, chr_banks=0), mode=Mode.RECURSIVE)
    assert dis.rom.chr_size == 0
    assert dis.stats["code"] > 0


def test_text_output_is_reassemblable_shape():
    txt = disassemble(image(), mode=Mode.LINEAR).text()
    assert txt.startswith("; Disassembly of synthetic.nes")
    assert ".org $C000" in txt
    assert "vec_reset" in txt


def test_dict_output_is_serialisable():
    import json

    payload = disassemble(image(), mode=Mode.RECURSIVE).as_dict()
    dumped = json.dumps(payload)
    assert dumped
    assert payload["mode"] == "recursive"
    assert payload["stats"]["code"] > 0
