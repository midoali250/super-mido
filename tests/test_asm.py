"""Assembler correctness, including the round-trip property."""

import pytest
from fixtures import build_rom

from romforge.asm6502 import AssembleError, assemble_program
from romforge.cpu6502 import (ADDRESSING_MODES, OPCODES, official_count,
                              undocumented_count)


def test_opcode_table_covers_every_byte():
    """No byte in a PRG ROM should be undecodable."""
    assert len(OPCODES) == 256
    assert official_count() == 151
    assert undocumented_count() == 256 - 151
    for code in range(256):
        mnem, mode, length, official = OPCODES[code]
        assert length == 1 + ADDRESSING_MODES[mode][0], code
        assert length in (1, 2, 3), code


def test_basic_encoding():
    code, syms = assemble_program(
        """
        start: lda #$42
               sta $0200
               inx
               rts
        """,
        origin=0xC000,
    )
    assert code == bytes([0xA9, 0x42, 0x8D, 0x00, 0x02, 0xE8, 0x60])
    assert syms["start"] == 0xC000


def test_zero_page_stays_two_bytes_and_absolute_three():
    code, _ = assemble_program("lda $10\nlda $1234", origin=0xC000)
    assert code == bytes([0xA5, 0x10, 0xAD, 0x34, 0x12])


def test_forward_reference_widens_to_absolute():
    code, syms = assemble_program(
        """
             lda far
        far: rts
        """,
        origin=0xC000,
    )
    # 'far' resolves to $C003 which cannot fit in one byte -> LDA absolute
    assert code[0] == 0xAD
    assert syms["far"] == 0xC003


def test_relative_branch_computes_signed_displacement():
    code, syms = assemble_program(
        """
        loop: nop
              nop
              bne loop
        """,
        origin=0xC000,
    )
    # loop=$C000, the branch sits at $C002 and is 2 bytes wide, so the
    # displacement is $C000 - $C004 = -4.
    assert code == bytes([0xEA, 0xEA, 0xD0, 0xFC])
    assert syms["loop"] == 0xC000


def test_branch_out_of_range_is_an_error():
    with pytest.raises(AssembleError):
        assemble_program(
            """
                 beq far
                 .fill 300, $EA
            far: rts
            """,
            origin=0xC000,
        )


def test_indirect_and_indexed_modes():
    code, _ = assemble_program(
        """
             jmp ($FF00)
             lda ($20,X)
             lda ($20),Y
             lda $30,X
             lda $1000,Y
        """,
        origin=0xC000,
    )
    assert code == bytes([0x6C, 0x00, 0xFF, 0xA1, 0x20, 0xB1, 0x20,
                          0xB5, 0x30, 0xB9, 0x00, 0x10])


def test_directives():
    code, _ = assemble_program(
        """
             .byte $01, $02, $03
             .word $C000, $FFFA
             .fill 4, $EA
        """,
        origin=0xC000,
    )
    assert code == bytes([1, 2, 3, 0x00, 0xC0, 0xFA, 0xFF, 0xEA, 0xEA, 0xEA, 0xEA])


def test_duplicate_label_rejected():
    with pytest.raises(AssembleError):
        assemble_program("a: nop\na: nop")


def test_unknown_mnemonic_rejected():
    with pytest.raises(AssembleError):
        assemble_program("frobnicate $10")


def test_comments_and_blank_lines_ignored():
    code, _ = assemble_program(
        """
        ; a comment
             nop   ; trailing comment

             nop
        """,
        origin=0xC000,
    )
    assert code == bytes([0xEA, 0xEA])


def test_build_rom_places_vectors_correctly():
    src = """
        reset: sei
               ldx #$FF
               txs
               jmp reset
        nmi:   rti
        irq:   rti
    """
    built = build_rom(src)
    prg = built.data[16 : 16 + 16384]
    assert prg[-6:-4] == bytes([built.symbols["nmi"] & 0xFF, built.symbols["nmi"] >> 8])
    assert prg[-4:-2] == bytes([built.symbols["reset"] & 0xFF, built.symbols["reset"] >> 8])
    assert prg[-2:] == bytes([built.symbols["irq"] & 0xFF, built.symbols["irq"] >> 8])
