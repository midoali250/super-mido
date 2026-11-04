"""Header parsing, format detection, and validation warnings."""

from fixtures import RomSpec, build_header, build_rom, rom_from_bytes

from romforge.ines import HeaderFormat, HeaderWarning, RomImage


def test_magic_and_nrom_defaults():
    img = RomImage.from_bytes(build_rom(spec=RomSpec()).data, "synthetic.nes")
    assert img.data[:4] == b"NES\x1a"
    assert img.fmt is HeaderFormat.INES
    assert img.mapper == 0
    assert img.mapper_name == "NROM"
    assert img.prg_size == 16384
    assert img.chr_size == 8192
    assert img.mirroring == "horizontal"
    assert not img.warnings or all(w is not HeaderWarning.BAD_MAGIC for w in img.warnings)


def test_mapper_number_combines_both_nybbles():
    for mapper in (0, 1, 4, 71, 228, 255):
        spec = RomSpec(mapper=mapper)
        img = RomImage.from_bytes(build_rom(spec=spec).data)
        assert img.mapper == mapper, mapper


def test_mmc1_flags_survive_round_trip():
    spec = RomSpec(mapper=1, mirroring="vertical", battery=True, four_screen=False)
    img = RomImage.from_bytes(build_rom(spec=spec).data)
    assert img.mapper == 1
    assert img.mirroring == "vertical"
    assert img.battery is True
    assert HeaderWarning.BATTERY in img.warnings


def test_nes2_detection_uses_flags7_bits_3_2():
    spec = RomSpec(mapper=4, submapper=3, ines2=True)
    header = build_header(spec)
    assert header[7] & 0x0C == 0x08
    img = RomImage.from_bytes(build_rom(spec=spec).data)
    assert img.fmt is HeaderFormat.NES_2_0
    assert img.mapper == 4
    assert img.submapper == 3


def test_trainer_offsets_are_accounted_for():
    spec = RomSpec(trainer=True)
    img = RomImage.from_bytes(build_rom(spec=spec).data)
    assert img.has_trainer is True
    assert len(img.trainer) == 512
    assert img.prg_size == 16384
    assert HeaderWarning.TRAINER in img.warnings


def test_chr_ram_board_reports_zero_chr():
    spec = RomSpec(chr_banks=0, chr_pattern="blank")
    img = RomImage.from_bytes(build_rom(spec=spec).data)
    assert img.chr_size == 0
    assert HeaderWarning.CHR_ZERO_MEANS_RAM in img.warnings


def test_ripper_signature_in_padding_is_detected_and_masked():
    """Bytes 12-15 scribbled by an old ROM manager inflate the mapper by 64."""
    spec = RomSpec(mapper=4)
    data = bytearray(build_rom(spec=spec).data)
    data[12:16] = b"Dude"          # ripper tag, non-zero padding
    data[7] = (data[7] & 0x0F) | 0x40  # what an archaic ripper would produce
    img = RomImage.from_bytes(bytes(data))
    assert HeaderWarning.NONZERO_PADDING in img.warnings
    assert HeaderWarning.DISKDUDE in img.warnings
    assert img.mapper == 4  # high nybble masked back off


def test_truncated_image_is_flagged_not_crashing():
    good = build_rom(spec=RomSpec(prg_banks=2, chr_banks=1)).data
    img = RomImage.from_bytes(good[: 16 + 100])
    assert HeaderWarning.TRUNCATED_PRG in img.warnings
    assert img.prg_size == 100


def test_bad_magic_is_rejected_with_warning():
    data = bytearray(build_rom().data)
    data[0:4] = b"FAM\x1a"
    img = RomImage.from_bytes(bytes(data))
    assert HeaderWarning.BAD_MAGIC in img.warnings


def test_too_small_file_is_handled():
    img = RomImage.from_bytes(b"NES\x1a\x01\x01")
    assert HeaderWarning.TOO_SMALL in img.warnings
    assert img.fmt is HeaderFormat.UNKNOWN
    assert img.prg_rom == b""


def test_vectors_and_entry_points():
    src = """
        reset: lda #$01
               sta $0050
               jmp reset
        nmi:   rti
        irq:   rti
    """
    built = build_rom(src)
    img = RomImage.from_bytes(built.data)
    ep = img.entry_points
    assert ep["reset"] == built.symbols["reset"]
    assert ep["nmi"] == built.symbols["nmi"]
    assert img.base_address == 0xC000


def test_base_address_for_32k_prg_is_0x8000():
    img = RomImage.from_bytes(build_rom(spec=RomSpec(prg_banks=2)).data)
    assert img.base_address == 0x8000


def test_summary_is_json_shaped():
    img = RomImage.from_bytes(build_rom(spec=RomSpec(mapper=4)).data)
    s = img.summary()
    assert s["mapper"] == 4
    assert s["mapper_name"] == "MMC3"
    assert isinstance(s["warnings"], list)
    assert s["prg_rom_bytes"] == 16384


def test_from_bytes_wrapping_helper_pads_to_bank_boundary():
    data = rom_from_bytes(b"\xEA" * 100, mapper=2)
    img = RomImage.from_bytes(data)
    assert img.mapper == 2
    assert img.mapper_name == "UxROM"
    assert img.prg_size == 16384
