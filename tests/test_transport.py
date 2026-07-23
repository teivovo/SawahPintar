import pytest

from app.sensor.profile import SensorProfile
from app.sensor.transport import FakeTransport, SerialTransport, TransportError

REQUEST = bytes.fromhex("01030000000985cc")
RESPONSE = bytes.fromhex("010312000001380000002f0000000000000000000090d4")

MINIMAL_PROFILE = SensorProfile.from_dict(
    {
        "key": "test",
        "label": "Test probe",
        "address": 1,
        "baud": 4800,
        "read_plans": [{"function": 3, "start": 0, "count": 9}],
        "registers": [],
    }
)


class _DoubleFaultPort:
    """Stands in for a pyserial handle that fails on both read and close.

    Models a dongle yanked mid exchange: the read raises because the device
    is gone, and the subsequent close attempt also raises because the
    handle is already invalid.
    """

    is_open = True

    def reset_input_buffer(self) -> None:
        pass

    def write(self, data: bytes) -> int:
        return len(data)

    def read(self, size: int) -> bytes:
        raise OSError("device reports no response")

    def close(self) -> None:
        raise OSError("handle already invalid")


def test_fake_transport_returns_configured_response():
    transport = FakeTransport({REQUEST: RESPONSE})
    transport.open()
    assert transport.is_open is True
    assert transport.exchange(REQUEST, len(RESPONSE)) == RESPONSE


def test_fake_transport_rejects_exchange_while_closed():
    transport = FakeTransport({REQUEST: RESPONSE})
    with pytest.raises(TransportError, match="not open"):
        transport.exchange(REQUEST, len(RESPONSE))


def test_fake_transport_returns_empty_for_unknown_request():
    transport = FakeTransport({REQUEST: RESPONSE})
    transport.open()
    assert transport.exchange(bytes.fromhex("0103000000018409"), 7) == b""


def test_fake_transport_can_simulate_a_dead_port():
    transport = FakeTransport({}, fail_on_open=True)
    with pytest.raises(TransportError, match="could not open"):
        transport.open()
    assert transport.is_open is False


def test_fake_transport_records_requests():
    transport = FakeTransport({REQUEST: RESPONSE})
    transport.open()
    transport.exchange(REQUEST, len(RESPONSE))
    transport.exchange(REQUEST, len(RESPONSE))
    assert transport.sent == [REQUEST, REQUEST]


def test_fake_transport_close_is_idempotent():
    transport = FakeTransport({})
    transport.open()
    transport.close()
    transport.close()
    assert transport.is_open is False


def test_serial_transport_exchange_raises_transport_error_on_double_fault():
    # If the exchange fails AND the subsequent close() also fails, the
    # caller must still see TransportError, not the raw close failure.
    transport = SerialTransport("COM_TEST", MINIMAL_PROFILE)
    transport._serial = _DoubleFaultPort()

    with pytest.raises(TransportError, match="exchange failed"):
        transport.exchange(REQUEST, len(RESPONSE))

    # close() still ran and cleared the handle despite raising internally.
    assert transport.is_open is False
