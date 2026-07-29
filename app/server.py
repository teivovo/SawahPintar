"""FastAPI application: REST routes and static file serving.

The websocket feed is added in Task 5, the register inspector in Task 6,
the operator console routes in Task 10. Each later task edits this file in
place rather than replacing it, since the static mount must always stay
the last route registered so that /api and every explicit route wins
against it.
"""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.config import GROWTH_STAGES, LANGUAGES, FieldCard, PutsResult, SensorBinding
from app.detector import StepChangeDetector
from app.export import export_session
from app.insights.permentan import dose_for_status
from app.observations import (
    initialise_schema as initialise_puts_schema,
    list_observations,
    record_observation,
)
from app.registers import read_registers
from app.reset import reset_live_data
from app.sensor.codec import ModbusError
from app.sensor.profile import SensorProfile
from app.sensor.transport import TransportError
from app.state import (
    WEB_DIR,
    WorkshopState,
    build_history_payload,
    build_reader,
    build_state_payload,
    build_ws_payload,
)
from app.storage import db

EXPORT_DIR = Path("data/exports")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RegisterReadRequest(BaseModel):
    """One arbitrary register read requested from the operator console."""

    port: str
    address: int
    start: int
    count: int
    function: int = 3
    baud: int = 4800


class ConfigUpdateRequest(BaseModel):
    """A partial update to the workshop configuration. A field left out of
    the request body is left unchanged."""

    language: str | None = None
    growth_stage: str | None = None
    site_name: str | None = None
    transplanting_date: str | None = None


class FieldCardRequest(BaseModel):
    field_size_ha: float | None = None
    variety: str = ""
    seedling_age_days: int | None = None
    water_source: str = ""
    previous_yield_t_ha: float | None = None
    fertiliser_available: str = ""


class PutsRequest(BaseModel):
    nitrogen_class: str
    phosphorus_class: str
    potassium_class: str
    ph: float | None = None


class ScenarioRequest(BaseModel):
    sensor_id: str
    action: str


class SensorBindRequest(BaseModel):
    port: str = "COM9"
    profile: str = "data/profiles/sn3002.json"
    mode: str = "simulate"
    # Optional plot metadata. When omitted the sensor keeps whatever label
    # and outline it already had, so switching a plot between live and
    # simulation from the field map never erases the zone the operator drew.
    name: str | None = None
    zone: list | None = None


class ZoneRequest(BaseModel):
    """One plot as drawn in the zone editor."""

    id: str
    name: str = ""
    mode: str = "simulate"
    port: str = "COM9"
    profile: str = "data/profiles/sn3002.json"
    zone: list | None = None


class ZonesUpdateRequest(BaseModel):
    """The full set of plots the operator laid out on the field photo."""

    zones: list[ZoneRequest]
    field_image: str | None = None
    field_view: list | None = None


class SensorSettingsRequest(BaseModel):
    """A per-plot label and/or growth-stage change that needs no reader rebuild."""

    name: str | None = None
    growth_stage: str | None = None


async def _default_sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


def _insert_if_map_mode(reader, map_mode: bool) -> None:
    """In a field-map demo (any plot has a zone drawn) a simulated plot is a
    probe already in the ground, so a reader built after startup - by a
    rebind or a zone save - must be put in soil too, matching what app.main
    does once at startup. Without this a fresh simulate reader reads air and
    the map shows a false "reflood now" alert. A no-op for live readers."""
    if map_mode and reader is not None and hasattr(reader, "insert_probe"):
        reader.insert_probe()


async def broadcast_loop(
    websocket,
    state: WorkshopState,
    sensor_id: str,
    interval: float = 2.0,
    clock: Callable[[], datetime] = utc_now,
    sleep: Callable[[float], Awaitable[None]] = _default_sleep,
    stop_after: int | None = None,
) -> None:
    """Push one update for sensor_id every interval until the socket closes.

    clock, sleep and stop_after are injected exactly as poll_forever in
    Plan 1 injects its clock and sleeper, so this loop is tested without a
    real websocket, a real clock or a real wait.

    The reader and detector are looked up from state.readers/state.detectors
    on every iteration rather than once before the loop starts. POST
    /api/sensors/{id}/bind replaces both dict entries when the operator
    recovers a stuck sensor, but a loop already running for an open socket
    (for example the console left open on a second window, or the display
    itself) had its own captured references and never saw the rebind for
    the life of that socket. Re-reading the dict each tick means the very
    next broadcast after a rebind uses the new reader.
    """
    sent = 0

    while stop_after is None or sent < stop_after:
        reader = state.readers.get(sensor_id)
        detector = state.detectors.get(sensor_id)
        # The plot may be detached (mode 'off') or removed from the layout
        # entirely (POST /api/zones) while this socket is open. Either leaves
        # no reader. Close cleanly with the same code the connect guard uses,
        # rather than indexing a missing key and crashing the socket with an
        # unhandled KeyError that would trap the client in a reconnect loop.
        if reader is None:
            await websocket.close(code=4004)
            return
        # read_once() is a synchronous, blocking serial call bounded by the
        # sensor profile's timeout (1.0 s by default). Run it off the event
        # loop thread so a probe that has stopped answering stalls only
        # this call, not every other websocket and route the server is
        # handling at the same time.
        try:
            reading = await asyncio.to_thread(reader.read_once, clock())
        except Exception as error:  # noqa: BLE001 - any read failure, handled below
            # A live probe that cannot be read - not connected, wrong port, the
            # port held by another program - raises here. It must NOT kill the
            # feed. Killing it closes the socket, traps the display in a
            # permanent reconnect loop, and stops the operator recovering by
            # switching back to simulation, because the replacement reader is
            # only picked up on the next tick of this same loop. So keep the
            # loop alive, tell the client the sensor is not responding, and
            # carry on. The very next successful read, whether a reconnected
            # probe or a switch back to simulation, clears the warning.
            await websocket.send_json(
                {
                    "sensor_id": sensor_id,
                    "error": "sensor-not-responding",
                    "detail": str(error),
                }
            )
            sent += 1
            await sleep(interval)
            continue
        advice = state.latest_advice(sensor_id, reading)
        probe_inserted = detector.observe(reading)
        db.insert_reading(state.con, reading)
        payload = build_ws_payload(state, sensor_id, reading, advice, probe_inserted)
        await websocket.send_json(payload)
        sent += 1
        await sleep(interval)


def create_app(state: WorkshopState) -> FastAPI:
    app = FastAPI(title="SawahPintar")
    initialise_puts_schema(state.con)

    @app.get("/api/state")
    def get_state():
        return build_state_payload(state)

    @app.get("/api/history")
    def get_history(sensor_id: str, metric: str, limit: int = 500):
        if sensor_id not in state.config.sensors:
            raise HTTPException(status_code=404, detail=f"unknown sensor: {sensor_id}")
        return build_history_payload(state, sensor_id, metric, limit=limit)

    @app.websocket("/ws")
    async def websocket_feed(websocket: WebSocket, sensor_id: str = "probe-a"):
        # A None reader means an unknown sensor or a detached plot (mode
        # 'off'): there is no feed to open, so reject rather than accept a
        # socket that would only ever report the sensor as not responding.
        if state.readers.get(sensor_id) is None:
            await websocket.close(code=4004)
            return
        await websocket.accept()
        try:
            await broadcast_loop(websocket, state, sensor_id)
        except WebSocketDisconnect:
            return

    @app.post("/api/registers/read")
    def read_registers_endpoint(payload: RegisterReadRequest):
        transport = state.transport_factory(payload.port, baud=payload.baud)
        try:
            values = read_registers(
                transport, payload.address, payload.function, payload.start, payload.count
            )
        except TransportError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error
        except ModbusError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        finally:
            transport.close()
        return {"registers": values}

    @app.get("/operator")
    def operator_page():
        return FileResponse(WEB_DIR / "operator.html")

    @app.get("/api/ports")
    def list_ports():
        from serial.tools import list_ports as pyserial_list_ports

        return {
            "ports": [
                {"device": port.device, "description": port.description}
                for port in pyserial_list_ports.comports()
            ]
        }

    @app.get("/api/profiles")
    def list_profiles():
        profiles_dir = Path("data/profiles")
        entries = []
        if profiles_dir.is_dir():
            for path in sorted(profiles_dir.glob("*.json")):
                try:
                    profile = SensorProfile.load(path)
                except (ValueError, OSError):
                    continue
                entries.append({"path": str(path), "key": profile.key, "label": profile.label})
        return {"profiles": entries}

    @app.post("/api/config")
    def update_config(payload: ConfigUpdateRequest):
        if payload.language is not None:
            if payload.language not in LANGUAGES:
                raise HTTPException(status_code=422, detail="unknown language")
            state.config.language = payload.language
        if payload.growth_stage is not None:
            if payload.growth_stage not in GROWTH_STAGES:
                raise HTTPException(status_code=422, detail="unknown growth stage")
            state.config.growth_stage = payload.growth_stage
        if payload.site_name is not None:
            state.config.site_name = payload.site_name
        if payload.transplanting_date is not None:
            state.config.transplanting_date = payload.transplanting_date
        state.config.save(state.config_path)
        return build_state_payload(state)

    @app.post("/api/field-card")
    def update_field_card(payload: FieldCardRequest):
        state.field_card = FieldCard(**payload.model_dump())
        return {"field_card": payload.model_dump()}

    @app.post("/api/puts")
    def record_puts(payload: PutsRequest):
        """Record one PUTS observation and, where a Permentan table has been
        wired in, return the official phosphorus dose for the entered
        class alongside it.

        Design spec 8.1 promises a dose the moment PUTS classes are
        entered, sourced from Permentan 13 of 2022 rather than the probe.
        This is the only place in the application that computes a dose; it
        never touches the probe's own nitrogen, phosphorus or potassium
        registers (spec 8.4). The dose is validated, and therefore raised
        as a client error on a mistyped class, before the observation is
        written, so a rejected request never leaves a half-recorded row in
        the paired observation log.
        """
        puts = PutsResult(**payload.model_dump())

        phosphorus_dose = None
        if state.permentan is not None:
            try:
                dose = dose_for_status(state.permentan, puts.phosphorus_class)
            except KeyError as error:
                raise HTTPException(status_code=422, detail=str(error)) from error
            phosphorus_dose = {
                "status": dose.status,
                "p2o5_kg_per_ha": dose.p2o5_kg_per_ha,
                "sp36_kg_per_ha": dose.sp36_kg_per_ha,
                "source": "Permentan 13 of 2022, from the operator's PUTS entry",
            }

        sensor_id = next(iter(state.config.sensors), None)
        conductivity = None
        if sensor_id is not None:
            latest = db.latest(state.con, sensor_id)
            if latest is not None:
                conductivity = latest.values.get("conductivity")
        record_observation(
            state.con,
            utc_now(),
            state.config.site_name,
            state.config.growth_stage,
            sensor_id or "",
            conductivity,
            puts,
        )
        state.puts_history.append(puts)

        response = {"recorded": True, "observations": list_observations(state.con)}
        if phosphorus_dose is not None:
            response["phosphorus_dose"] = phosphorus_dose
        return response

    @app.post("/api/scenario")
    def run_scenario(payload: ScenarioRequest):
        reader = state.readers.get(payload.sensor_id)
        if reader is None:
            raise HTTPException(status_code=404, detail=f"unknown sensor: {payload.sensor_id}")
        if not hasattr(reader, "insert_probe"):
            raise HTTPException(status_code=409, detail="sensor is not in simulate mode")
        if payload.action == "insert":
            reader.insert_probe()
        elif payload.action == "withdraw":
            reader.withdraw_probe()
        else:
            raise HTTPException(status_code=422, detail=f"unknown action: {payload.action}")
        return {"sensor_id": payload.sensor_id, "action": payload.action}

    @app.post("/api/sensors/{sensor_id}/bind")
    def bind_sensor(sensor_id: str, payload: SensorBindRequest):
        # Preserve the plot label and outline across a rebind unless the
        # caller supplies new ones: switching a plot between live and
        # simulation must not wipe the zone the operator drew for it.
        existing = state.config.sensors.get(sensor_id)
        name = payload.name if payload.name is not None else (existing.name if existing else "")
        zone = payload.zone if payload.zone is not None else (existing.zone if existing else None)
        reader = build_reader(payload.port, payload.profile, sensor_id, payload.mode)
        state.readers[sensor_id] = reader
        state.detectors[sensor_id] = StepChangeDetector()
        state.config.sensors[sensor_id] = SensorBinding(
            port=payload.port, profile=payload.profile, mode=payload.mode, name=name, zone=zone
        )
        _insert_if_map_mode(reader, any(b.zone for b in state.config.sensors.values()))
        state.config.save(state.config_path)
        return {"sensor_id": sensor_id, "mode": payload.mode}

    @app.post("/api/sensors/{sensor_id}/settings")
    def update_sensor_settings(sensor_id: str, payload: SensorSettingsRequest):
        """Rename a plot or restage it without rebuilding its reader, so the
        change never interrupts a live feed or reseeds a simulation, and it
        persists so the next launch shows the same setup."""
        binding = state.config.sensors.get(sensor_id)
        if binding is None:
            raise HTTPException(status_code=404, detail=f"unknown sensor: {sensor_id}")
        if payload.name is not None:
            binding.name = payload.name
        if payload.growth_stage is not None:
            if payload.growth_stage not in GROWTH_STAGES:
                raise HTTPException(status_code=422, detail="unknown growth stage")
            binding.growth_stage = payload.growth_stage
        state.config.save(state.config_path)
        return {
            "sensor_id": sensor_id,
            "name": binding.name,
            "growth_stage": binding.growth_stage or state.config.growth_stage,
        }

    @app.post("/api/zones")
    def update_zones(payload: ZonesUpdateRequest):
        """Replace the full set of plots with what the operator drew in the
        zone editor.

        A sensor dropped from the list is removed with its reader; a new one
        gets a reader built. A plot that only changed shape or label keeps
        its existing reader, so re-saving a layout does not needlessly
        reopen serial ports or reseed simulations for unchanged plots.
        """
        if payload.field_image is not None:
            state.config.field_image = payload.field_image
        if payload.field_view is not None:
            state.config.field_view = list(payload.field_view)

        new_sensors = {
            z.id: SensorBinding(port=z.port, profile=z.profile, mode=z.mode, name=z.name, zone=z.zone)
            for z in payload.zones
        }
        map_mode = any(binding.zone for binding in new_sensors.values())
        for sensor_id in list(state.readers):
            if sensor_id not in new_sensors:
                state.readers.pop(sensor_id, None)
                state.detectors.pop(sensor_id, None)
        old_sensors = state.config.sensors
        for sensor_id, binding in new_sensors.items():
            existing = old_sensors.get(sensor_id)
            wiring_changed = existing is None or (
                existing.port,
                existing.profile,
                existing.mode,
            ) != (binding.port, binding.profile, binding.mode)
            if wiring_changed or sensor_id not in state.readers:
                reader = build_reader(binding.port, binding.profile, sensor_id, binding.mode)
                state.readers[sensor_id] = reader
                state.detectors[sensor_id] = StepChangeDetector()
                # Newly built simulate plots start in soil in a field-map
                # demo, so a saved layout shows soil values, not a false
                # air-reads-dry "reflood now" alert.
                _insert_if_map_mode(reader, map_mode)
        state.config.sensors = new_sensors
        state.config.save(state.config_path)
        return build_state_payload(state)

    @app.post("/api/demo-reset")
    def demo_reset():
        deleted = reset_live_data(state.con)
        state.puts_history = []
        state.field_card = None
        return {"deleted": deleted}

    @app.post("/api/export")
    def export_readings():
        try:
            paths = export_session(state.con, EXPORT_DIR, site_name=state.config.site_name)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return paths

    # --- static mount: must stay last. app/web/ is populated in Task 7; ---
    # --- check_dir=False lets the app start before that directory exists. ---
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True, check_dir=False), name="web")

    return app
