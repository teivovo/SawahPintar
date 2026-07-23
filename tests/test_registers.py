import pytest

from app.config import WorkshopConfig
from app.registers import open_transport_for_inspection, read_registers
from app.sensor.codec import ModbusError
from app.sensor.transport import FakeTransport, SerialTransport, TransportError
from app.state import WorkshopState
from app.storage import db

REQUEST = bytes.fromhex("01030000000985cc")
RESPONSE = bytes.fromhex("010312000001380000002f0000000000000000000090d4")


def make_state():
    connection = db.connect(":memory:")
    db.initialise_schema(connection)
    config = WorkshopConfig.from_dict({"sensors": {"probe-a": {"mode": "simulate"}}})
    return WorkshopState.build(connection, config, "config.json")


def test_read_registers_returns_raw_values():
    transport = FakeTransport({REQUEST: RESPONSE})
    transport.open()
    values = read_registers(transport, address=1, function=3, start=0, count=9)
    assert values == [0, 312, 0, 47, 0, 0, 0, 0, 0]


def test_read_registers_opens_a_closed_transport():
    transport = FakeTransport({REQUEST: RESPONSE})
    values = read_registers(transport, address=1, function=3, start=0, count=9)
    assert transport.is_open is True
    assert values == [0, 312, 0, 47, 0, 0, 0, 0, 0]


def test_read_registers_propagates_transport_error():
    transport = FakeTransport({}, fail_on_open=True)
    with pytest.raises(TransportError):
        read_registers(transport, address=1, function=3, start=0, count=9)


def test_read_registers_propagates_modbus_error_on_bad_crc():
    corrupted = RESPONSE[:-1] + bytes([RESPONSE[-1] ^ 0xFF])
    transport = FakeTransport({REQUEST: corrupted})
    transport.open()
    with pytest.raises(ModbusError, match="CRC"):
        read_registers(transport, address=1, function=3, start=0, count=9)


def test_open_transport_for_inspection_returns_a_serial_transport():
    transport = open_transport_for_inspection("COM9", baud=4800)
    assert isinstance(transport, SerialTransport)


def test_register_read_endpoint_returns_values():
    from fastapi.testclient import TestClient

    from app.server import create_app

    state = make_state()
    fake_transport = FakeTransport({REQUEST: RESPONSE})
    state.transport_factory = lambda port, baud=4800, **kwargs: fake_transport
    client = TestClient(create_app(state))

    response = client.post(
        "/api/registers/read",
        json={"port": "COM9", "address": 1, "function": 3, "start": 0, "count": 9, "baud": 4800},
    )

    assert response.status_code == 200
    assert response.json()["registers"] == [0, 312, 0, 47, 0, 0, 0, 0, 0]
    state.con.close()


def test_register_read_endpoint_reports_transport_failure():
    from fastapi.testclient import TestClient

    from app.server import create_app

    state = make_state()
    state.transport_factory = lambda port, baud=4800, **kwargs: FakeTransport({}, fail_on_open=True)
    client = TestClient(create_app(state))

    response = client.post(
        "/api/registers/read", json={"port": "COM9", "address": 1, "start": 0, "count": 9}
    )

    assert response.status_code == 502
    state.con.close()


def test_register_read_endpoint_reports_modbus_error():
    from fastapi.testclient import TestClient

    from app.server import create_app

    corrupted = RESPONSE[:-1] + bytes([RESPONSE[-1] ^ 0xFF])
    state = make_state()
    state.transport_factory = lambda port, baud=4800, **kwargs: FakeTransport({REQUEST: corrupted})
    client = TestClient(create_app(state))

    response = client.post(
        "/api/registers/read", json={"port": "COM9", "address": 1, "start": 0, "count": 9}
    )

    assert response.status_code == 422
    state.con.close()
