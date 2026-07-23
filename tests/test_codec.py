import pytest

from app.sensor.codec import (
    ModbusError,
    build_read_request,
    crc16,
    expected_response_length,
    parse_read_response,
)

# Captured from the SN-3002 probe on COM9, 22 July 2026.
REAL_REQUEST = bytes.fromhex("01030000000985cc")
REAL_RESPONSE = bytes.fromhex(
    "010312000001380000002f0000000000000000000090d4"
)


def test_crc16_matches_captured_request():
    assert crc16(bytes.fromhex("010300000009")) == bytes.fromhex("85cc")


def test_build_read_request_matches_captured_frame():
    assert build_read_request(0x01, 0x03, 0x0000, 9) == REAL_REQUEST


def test_expected_response_length():
    # address, function, byte count, two bytes per register, two CRC bytes.
    assert expected_response_length(9) == 23


def test_parse_read_response_returns_registers():
    registers = parse_read_response(REAL_RESPONSE, 0x01, 0x03, 9)
    assert registers == [0, 312, 0, 47, 0, 0, 0, 0, 0]


def test_parse_rejects_bad_crc():
    corrupted = REAL_RESPONSE[:-1] + bytes([REAL_RESPONSE[-1] ^ 0xFF])
    with pytest.raises(ModbusError, match="CRC"):
        parse_read_response(corrupted, 0x01, 0x03, 9)


def test_parse_rejects_wrong_address():
    with pytest.raises(ModbusError, match="address"):
        parse_read_response(REAL_RESPONSE, 0x02, 0x03, 9)


def test_parse_rejects_short_frame():
    with pytest.raises(ModbusError, match="too short"):
        parse_read_response(REAL_RESPONSE[:4], 0x01, 0x03, 9)


def test_parse_rejects_a_frame_that_is_too_long_with_accurate_wording():
    # A well-formed payload with one byte of trailing garbage after it: the
    # byte count field still matches, so only the final length guard fires,
    # and it must not misreport an over-length frame as "too short".
    body = REAL_RESPONSE[:-2] + b"\x00"
    frame = body + crc16(body)
    with pytest.raises(ModbusError, match="too long"):
        parse_read_response(frame, 0x01, 0x03, 9)


def test_parse_raises_on_exception_response():
    # Function code with the high bit set signals a Modbus exception.
    body = bytes([0x01, 0x83, 0x02])
    frame = body + crc16(body)
    with pytest.raises(ModbusError, match="exception code 2"):
        parse_read_response(frame, 0x01, 0x03, 9)


def test_parse_rejects_wrong_byte_count():
    body = bytes([0x01, 0x03, 0x04, 0x00, 0x00, 0x01, 0x38])
    frame = body + crc16(body)
    with pytest.raises(ModbusError, match="byte count"):
        parse_read_response(frame, 0x01, 0x03, 9)


def test_build_rejects_out_of_range_count():
    with pytest.raises(ValueError, match="count"):
        build_read_request(0x01, 0x03, 0x0000, 0)
