"""CLI play loop: WebSocket session driven by chart zip uploads from the web UI."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import warnings
from collections.abc import Sequence
from dataclasses import dataclass, field
from re import Pattern
from typing import Any, Never

from websockets.asyncio.server import broadcast, serve
from websockets.exceptions import ConnectionClosed, PayloadTooBig
from websockets.typing import Origin

from fly_rg.brain_backend import MockBrain, make_brain
from fly_rg.chart import list_difficulties, parse_simai_subset
from fly_rg.decoder import ActionDecoder
from fly_rg.encoder import DEADZONE, ON_PAD_TTH_S, NoteEncoder
from fly_rg.judge import HitEvent, Judge
from fly_rg.neuron_view import NeuronAtlas
from fly_rg.protocol import (
    chart_message,
    dumps,
    end_message,
    hello_message,
    hit_message,
    resources_message,
    state_message,
)
from fly_rg.resources import RESOURCE_PERIOD_S, ResourceMonitor
from fly_rg.schema import Chart, Note
from fly_rg.sensors import nearest_sensor

STATE_PERIOD_S = 0.016
SPIKE_PERIOD_S = 0.050
BRAIN_WARMUP = 16
OVERRUN_MEAN_S = 0.008
MAX_STEP_DT_S = 0.050
# A DNp tap edge and the on-pad geometry gate do not land on the same motor step:
# the spike edge leads the arrival by a few ms (measured ~20ms at dt=0.004), so
# AND-ing them per step scores nothing. The edge arms the hand for this long.
TAP_LATCH_S = 0.060
MAX_MAIDATA_BYTES = 256 * 1024
MAX_CHART_NOTES = 20_000
# Incoming frame cap (library default is 1 MiB). Maidata is already capped at 256 KiB.
WS_MAX_SIZE = 512 * 1024
# Skip a client whose asyncio write buffer is at/above serve() write_limit (32 KiB).
WRITE_BUFFER_SKIP = 32_768


@dataclass
class Session:
    chart: Chart | None = None
    play_task: asyncio.Task | None = None
    stop_event: asyncio.Event = field(default_factory=asyncio.Event)
    clients: set = field(default_factory=set)
    last_resources: dict[str, Any] | None = None


def _error(message: str, *, warning_count: int | None = None) -> dict[str, Any]:
    msg: dict[str, Any] = {"type": "error", "message": message}
    if warning_count:
        msg["warnings"] = int(warning_count)
    return msg


def _parse_client_message(raw: str | bytes | bytearray) -> dict[str, Any]:
    """Decode a client JSON object. Raises ValueError with a UI-safe reason."""
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("invalid JSON") from exc
    if not isinstance(msg, dict):
        raise TypeError("invalid JSON")
    return msg


def _reject_maidata_size(maidata: str) -> str | None:
    if len(maidata.encode("utf-8")) > MAX_MAIDATA_BYTES:
        return "maidata exceeds 256 KiB"
    return None


def _reject_note_count(n_notes: int) -> str | None:
    if n_notes > MAX_CHART_NOTES:
        return f"chart has more than {MAX_CHART_NOTES} notes"
    return None


def _skipped_note_count(caught: list[warnings.WarningMessage]) -> int:
    n = 0
    for item in caught:
        if str(item.message).startswith("skipping note"):
            n += 1
    return n


def _prepare_loaded_chart(
    maidata: str,
    difficulty: int | None,
) -> tuple[Chart | None, int, dict[str, Any] | None]:
    """Parse maidata for load_chart. Returns (chart, skipped, error_msg)."""
    size_err = _reject_maidata_size(maidata)
    if size_err is not None:
        return None, 0, _error(size_err)
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            chart = parse_simai_subset(maidata, difficulty=difficulty)
        skipped = _skipped_note_count(caught)
    except Exception as exc:  # noqa: BLE001  surface parse errors to the UI
        return None, 0, _error(str(exc))
    count_err = _reject_note_count(len(chart.notes))
    if count_err is not None:
        return None, skipped, _error(count_err, warning_count=skipped or None)
    if not chart.notes:
        return None, skipped, _error(
            "chart has no playable notes",
            warning_count=skipped or None,
        )
    return chart, skipped, None


def _serve_origins(host: str, port: int) -> Sequence[Origin | Pattern[str] | None]:
    """Allow-list for the local Vite UI and the bound play server origin.

    None is included so local Python clients that send no Origin header still
    connect. Browser pages must match an exact origin string.
    """
    origins: list[Origin | Pattern[str] | None] = [
        None,
        Origin("http://127.0.0.1:5173"),
        Origin("http://localhost:5173"),
        Origin(f"http://{host}:{port}"),
    ]
    seen: list[Origin | Pattern[str] | None] = []
    for origin in origins:
        if origin not in seen:
            seen.append(origin)
    return seen


def _client_write_buffered(websocket: Any) -> int:
    transport = getattr(websocket, "transport", None)
    if transport is None:
        return 0
    getter = getattr(transport, "get_write_buffer_size", None)
    if getter is None:
        return 0
    return int(getter())


def _emit_to_clients(clients: set, payload: str) -> None:
    """Push one frame; skip a client whose write buffer is already full."""
    ready: list[Any] = []
    for websocket in list(clients):
        try:
            if _client_write_buffered(websocket) >= WRITE_BUFFER_SKIP:
                continue
            ready.append(websocket)
        except Exception:  # noqa: S112
            continue
    if not ready:
        return
    try:
        broadcast(ready, payload)
    except (ConnectionClosed, PayloadTooBig):
        return


def _levels_message(maidata: str) -> dict[str, Any]:
    return {"type": "levels", "levels": list_difficulties(maidata)}


def _press_sensor(x: float, y: float) -> str | None:
    return nearest_sensor(x, y)


@dataclass
class TapLatch:
    """Per-hand arm times set by DNp tap edges; an arm expires after TAP_LATCH_S.

    A later edge on the same hand re-arms it, so sustained spiking keeps the hand
    pressable while the geometry gate catches up.
    """

    armed_t: dict[str, float] = field(
        default_factory=lambda: {"L": -1e9, "R": -1e9}
    )

    def arm(self, side: str, now: float) -> None:
        self.armed_t[side] = float(now)

    def is_armed(self, side: str, now: float) -> bool:
        return (float(now) - self.armed_t[side]) <= TAP_LATCH_S


def _want_press(
    *,
    tap: bool,
    occupancy: str | None,
    intended: str | None,
    tth: float | None = None,
) -> bool:
    """Press when a spike-armed hand sits on the intended pad at hit time.

    `tap` is the latched DNp tap edge for this hand, so no spikes means no press.
    """
    if not tap:
        return False
    if occupancy is None or intended is None:
        return False
    if occupancy != intended:
        return False
    if tth is None:
        return False
    return tth <= ON_PAD_TTH_S


def _contact_sensors(judge: Judge, now: float) -> set[str]:
    """Pads that should stay planted (hold sustain / in-progress slide)."""
    out: set[str] = set()
    notes = judge.notes
    for i in judge._live:
        note = notes[i]
        nt = note.type
        if nt == "hold" or nt == "touch_hold":
            if not judge.hold_started[i] or judge.matched[i]:
                continue
            end = note.end if note.end is not None else note.t
            if note.t <= now <= end:
                out.add(note.sensor)
            continue
        if nt == "slide":
            if note.slide is not None and judge.slide_next[i] > 0 and now <= note.slide.end_t:
                path = note.slide.path
                nxt = min(judge.slide_next[i], len(path) - 1)
                out.add(path[nxt])
            continue
        if nt == "tap" or nt == "touch":
            continue
        _exhaustive: Never = nt
        raise ValueError(f"unknown note type: {_exhaustive}")
    return out


async def _resource_loop(session: Session, monitor: ResourceMonitor) -> None:
    fail_logged = False
    while True:
        try:
            stats = monitor.sample()
            session.last_resources = stats
            if session.clients:
                _emit_to_clients(session.clients, dumps(resources_message(stats)))
        except Exception as exc:
            if not fail_logged:
                fail_logged = True
                print(f"resource loop error: {exc}", flush=True)
        await asyncio.sleep(RESOURCE_PERIOD_S)


async def _pace(delay: float) -> None:
    """Always yield so Stop, resources, and WS flushes can run."""
    await asyncio.sleep(delay if delay > 0.0 else 0.0)


def _wall_sim_t(t0: float, speed: float) -> float:
    return (time.perf_counter() - t0) * max(speed, 1e-9)


def _step_dt(prev_t: float, sim_t: float, motor_dt: float) -> float:
    raw = sim_t - prev_t
    if raw <= 1e-12:
        return motor_dt
    return min(raw, MAX_STEP_DT_S)


def _format_judgment_log(hit: HitEvent, note: Note) -> str | None:
    if hit.error_ms is None and hit.judgment != "miss":
        return None
    bits = [f"judge {hit.judgment}"]
    if hit.error_ms is not None:
        if hit.error_ms < -0.05:
            bits.append("FAST")
        elif hit.error_ms > 0.05:
            bits.append("LATE")
        bits.append(f"{abs(hit.error_ms):.1f}ms")
    bits.append(hit.sensor)
    bits.append(note.type)
    return " ".join(bits)


def _log_judgment(hit: HitEvent, notes: list[Note]) -> None:
    line = _format_judgment_log(hit, notes[hit.note_index])
    if line is not None:
        print(line, flush=True)


def _state_due(
    sim_t: float,
    last_state_t: float,
    period: float,
    *,
    tap: bool,
    strike_l: float = 0.0,
    strike_r: float = 0.0,
) -> bool:
    # strike_l/strike_r are ignored: hold/slide sustain used to flood WS every 4ms.
    del strike_l, strike_r
    if tap:
        return True
    return sim_t + 1e-12 >= last_state_t + period


async def _play_once(
    *,
    session: Session,
    chart: Chart,
    brain: Any,
    is_mock: bool,
    encoder: NoteEncoder,
    atlas: NeuronAtlas,
    args: argparse.Namespace,
    parse_warnings: int = 0,
) -> None:
    emit_fail_logged = False

    def emit(msg: dict) -> None:
        nonlocal emit_fail_logged
        if not session.clients:
            return
        try:
            _emit_to_clients(session.clients, dumps(msg))
        except Exception as exc:
            if not emit_fail_logged:
                emit_fail_logged = True
                print(f"ws emit error: {exc}", flush=True)

    last_note_t = max((n.t for n in chart.notes), default=0.0)
    # Pad for holds/slides that extend past last head time.
    extra = 0.0
    for n in chart.notes:
        if n.end is not None:
            extra = max(extra, n.end - last_note_t)
        if n.slide is not None:
            extra = max(extra, n.slide.end_t - last_note_t)
    end_t = last_note_t + max(2.0, extra + 0.5)

    judge = Judge(chart.notes)
    decoder = ActionDecoder(brain, mock=is_mock, seed=0)
    encoder.clear_locks()
    emit(
        chart_message(
            chart,
            active=judge.active_notes(0.0, args.look_ahead),
            active_sensors=judge.active_sensors(0.0, args.look_ahead),
            warnings=parse_warnings or None,
        )
    )
    await _pace(0.0)
    if session.stop_event.is_set() or not session.clients:
        print("play stopped", flush=True)
        return
    t0 = time.perf_counter()
    sim_t = 0.0
    prev_t = 0.0
    step_i = 0
    motor_dt = float(args.dt)
    brain_dt = motor_dt
    next_brain_t = 0.0
    last_state_t = -1e9
    last_spikes_t = -1e9
    last_drive: dict[str, float] = {}
    last_fired: list = []
    tap_latch = TapLatch()
    overrun_logged = False
    step_times: list[float] = []
    brain_steps = 0
    speed = max(args.speed, 1e-9)

    print(
        f"playing {chart.title!r} notes={len(chart.notes)} end={end_t:.1f}s",
        flush=True,
    )

    while True:
        if session.stop_event.is_set() or not session.clients:
            print("play stopped", flush=True)
            return

        sim_t = _wall_sim_t(t0, speed)
        if sim_t > end_t:
            break
        step_dt = _step_dt(prev_t, sim_t, motor_dt)
        prev_t = sim_t

        enc = encoder.encode(
            chart.notes,
            sim_t,
            look_ahead_s=args.look_ahead,
            dt=step_dt,
            slide_next=judge.slide_next,
            matched=judge.matched,
            hand_l=decoder.hand_l,
            hand_r=decoder.hand_r,
        )
        last_drive = enc.drive
        if sim_t + 1e-12 >= next_brain_t:
            t_brain = time.perf_counter()
            if is_mock and isinstance(brain, MockBrain):
                fired = brain.step(drive=enc.drive)
                last_drive = brain.last_inject
            else:
                fired = brain.step(inject=enc.inject)
                last_drive = enc.drive
            elapsed = time.perf_counter() - t_brain
            if not is_mock:
                brain_steps += 1
                if brain_steps > BRAIN_WARMUP:
                    step_times.append(elapsed)
                    if len(step_times) > 8:
                        del step_times[0]
                    mean_elapsed = sum(step_times) / len(step_times)
                    if mean_elapsed > OVERRUN_MEAN_S and not overrun_logged:
                        print(
                            f"brain step mean={mean_elapsed * 1000:.1f}ms overran "
                            f"motor dt={motor_dt * 1000:.1f}ms; brain dt=0.020 "
                            f"(hands still intercept every {motor_dt * 1000:.0f}ms "
                            f"from note time-to-hit, DNa rates held for spikes)",
                            flush=True,
                        )
                        overrun_logged = True
                        brain_dt = 0.020
                        brain.dt = 0.020
            next_brain_t = sim_t + brain_dt
            last_fired = list(fired) if fired is not None else []
            decoder.observe(last_fired)
        fired_list = last_fired
        dec = decoder.decode(
            sim_t,
            dt=step_dt,
            drive=last_drive,
            contact=_contact_sensors(judge, sim_t),
        )

        occupancy_l = _press_sensor(*dec.hand_l)
        occupancy_r = _press_sensor(*dec.hand_r)
        for miss in judge.auto_miss(
            sim_t,
            {s for s in (occupancy_l, occupancy_r) if s is not None},
        ):
            _log_judgment(miss, chart.notes)
            emit(
                hit_message(
                    t=miss.t,
                    button=miss.button,
                    sensor=miss.sensor,
                    judgment=miss.judgment,
                    timing=miss.timing,
                )
            )

        if dec.tap_l:
            tap_latch.arm("L", sim_t)
        if dec.tap_r:
            tap_latch.arm("R", sim_t)

        press_l = _want_press(
            tap=tap_latch.is_armed("L", sim_t),
            occupancy=occupancy_l,
            intended=enc.target_l,
            tth=enc.tth_l,
        )
        press_r = _want_press(
            tap=tap_latch.is_armed("R", sim_t),
            occupancy=occupancy_r,
            intended=enc.target_r,
            tth=enc.tth_r,
        )
        if press_l and occupancy_l is not None:
            hit = judge.press(occupancy_l, sim_t)
            if hit is not None:
                _log_judgment(hit, chart.notes)
                emit(
                    hit_message(
                        t=hit.t,
                        button=hit.button,
                        sensor=hit.sensor,
                        judgment=hit.judgment,
                        timing=hit.timing,
                    )
                )
        if press_r and occupancy_r is not None:
            hit = judge.press(occupancy_r, sim_t)
            if hit is not None:
                _log_judgment(hit, chart.notes)
                emit(
                    hit_message(
                        t=hit.t,
                        button=hit.button,
                        sensor=hit.sensor,
                        judgment=hit.judgment,
                        timing=hit.timing,
                    )
                )

        strike_l = 1.0 if press_l else dec.strike_l
        strike_r = 1.0 if press_r else dec.strike_r
        strike = max(strike_l, strike_r, dec.strike)
        tap = dec.tap or press_l or press_r
        tap_sensor = (
            occupancy_l
            if press_l
            else (occupancy_r if press_r else dec.tap_sensor)
        )

        spikes = atlas.spikes_for(
            last_drive,
            aim=dec.aim,
            strike=strike,
            strike_l=strike_l,
            strike_r=strike_r,
            fired_count=len(fired_list),
            step=step_i,
        )
        step_i += 1

        if _state_due(
            sim_t,
            last_state_t,
            STATE_PERIOD_S,
            tap=tap,
        ):
            last_state_t = sim_t
            if sim_t + 1e-12 >= last_spikes_t + SPIKE_PERIOD_S:
                last_spikes_t = sim_t
                spike_payload = spikes
            else:
                spike_payload = []
            emit(
                state_message(
                    t=sim_t,
                    aim_button=dec.aim_button,
                    aim_sensor=dec.aim_sensor,
                    tap=tap,
                    tap_button=dec.tap_button if tap else None,
                    tap_sensor=tap_sensor if tap else None,
                    score=judge.score.to_dict(),
                    active=judge.active_notes(sim_t, args.look_ahead),
                    active_sensors=judge.active_sensors(sim_t, args.look_ahead),
                    drive=enc.drive,
                    pose={
                        "aim": dec.aim,
                        "strike": strike,
                        "strike_l": strike_l,
                        "strike_r": strike_r,
                        "omega_l": dec.omega_l,
                        "omega_r": dec.omega_r,
                        "reach_l": dec.reach_l,
                        "reach_r": dec.reach_r,
                    },
                    spikes=spike_payload,
                    spike_total=len(fired_list) if fired_list else len(spikes),
                    hand_l_sensor=dec.hand_l_sensor,
                    hand_r_sensor=dec.hand_r_sensor,
                    hand_l=dec.hand_l,
                    hand_r=dec.hand_r,
                )
            )

        next_wall = t0 + (sim_t + motor_dt) / speed
        await _pace(next_wall - time.perf_counter())

    emit(end_message(judge.score.to_dict()))
    print(
        f"end achievement={judge.score.achievement:.6f} "
        f"acc={judge.score.accuracy:.3f} "
        f"C={judge.score.critical} P={judge.score.perfect} G={judge.score.great} "
        f"g={judge.score.good} M={judge.score.miss} combo={judge.score.combo}",
        flush=True,
    )


async def run_play(args: argparse.Namespace) -> None:
    args.dt = min(0.005, max(0.001, float(args.dt)))
    brain, is_mock = make_brain(mock=args.mock, device=args.device, dt=args.dt)
    if args.mock:
        is_mock = True
    print(
        f"brain={'mock' if is_mock else 'flybrain'} device={args.device} "
        f"press_gate={ON_PAD_TTH_S * 1000:.0f}ms deadzone={DEADZONE} "
        f"(upload a Majdata zip from the web UI)",
        flush=True,
    )

    encoder = NoteEncoder(brain if not is_mock else None, mock=is_mock)
    if not is_mock:
        try:
            brain.step(inject=[])
        except Exception:
            pass
    atlas = NeuronAtlas(n=720, seed=7)
    layout_msg = atlas.layout_message()
    session = Session()
    monitor = ResourceMonitor()
    session.last_resources = monitor.sample()
    # Stash last maidata so client can pick difficulty then play.
    last_maidata: dict[str, str] = {"text": ""}

    async def stop_play() -> None:
        session.stop_event.set()
        task = session.play_task
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        session.play_task = None

    async def start_chart(chart: Chart, *, parse_warnings: int = 0) -> None:
        await stop_play()
        session.stop_event = asyncio.Event()
        session.chart = chart
        session.play_task = asyncio.create_task(
            _play_once(
                session=session,
                chart=chart,
                brain=brain,
                is_mock=is_mock,
                encoder=encoder,
                atlas=atlas,
                args=args,
                parse_warnings=parse_warnings,
            )
        )

    async def handler(websocket) -> None:
        session.clients.add(websocket)
        try:
            await websocket.send(dumps(hello_message()))
            await websocket.send(dumps(layout_msg))
            if session.last_resources is not None:
                await websocket.send(dumps(resources_message(session.last_resources)))
            await websocket.send(
                dumps(
                    {
                        "type": "ready",
                        "message": "Upload a Majdata zip (maidata.txt + track + bg).",
                    }
                )
            )
            async for raw in websocket:
                try:
                    msg = _parse_client_message(raw)
                except (ValueError, TypeError) as exc:
                    await websocket.send(dumps(_error(str(exc))))
                    continue
                mtype = msg.get("type")
                if mtype == "inspect_chart":
                    maidata = str(msg.get("maidata") or "")
                    if not maidata.strip():
                        await websocket.send(dumps(_error("maidata is empty")))
                        continue
                    size_err = _reject_maidata_size(maidata)
                    if size_err is not None:
                        await websocket.send(dumps(_error(size_err)))
                        continue
                    last_maidata["text"] = maidata
                    await websocket.send(dumps(_levels_message(maidata)))
                elif mtype == "load_chart":
                    maidata = str(msg.get("maidata") or last_maidata["text"] or "")
                    if not maidata.strip():
                        await websocket.send(dumps(_error("maidata is empty")))
                        continue
                    last_maidata["text"] = maidata
                    difficulty = msg.get("difficulty")
                    try:
                        diff = int(difficulty) if difficulty is not None else None
                    except (TypeError, ValueError) as exc:
                        await websocket.send(dumps(_error(str(exc))))
                        continue
                    chart, skipped, err = _prepare_loaded_chart(maidata, diff)
                    if err is not None or chart is None:
                        await websocket.send(
                            dumps(err or _error("chart load failed"))
                        )
                        continue
                    await start_chart(chart, parse_warnings=skipped)
                elif mtype == "stop":
                    await stop_play()
                    await websocket.send(dumps({"type": "ready", "message": "stopped"}))
                else:
                    await websocket.send(dumps(_error(f"unknown message type {mtype!r}")))
            await websocket.wait_closed()
        finally:
            session.clients.discard(websocket)
            if not session.clients:
                await stop_play()

    resource_task = asyncio.create_task(_resource_loop(session, monitor))
    try:
        async with serve(
            handler,
            args.host,
            args.port,
            origins=_serve_origins(args.host, args.port),
            max_size=WS_MAX_SIZE,
        ):
            print(
                f"websocket ws://{args.host}:{args.port} waiting for zip upload from the UI",
                flush=True,
            )
            await asyncio.Future()  # run forever
    finally:
        resource_task.cancel()
        try:
            await resource_task
        except asyncio.CancelledError:
            pass
        monitor.close()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="fly-rg play server (charts come from the web UI zip upload)"
    )
    p.add_argument("--mock", action="store_true", help="use MockBrain (no flybrain download)")
    p.add_argument("--device", default="auto", help="flybrain device: auto|cpu|cuda")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--speed", type=float, default=1.0, help="playback speed multiplier")
    p.add_argument("--look-ahead", type=float, default=1.0, dest="look_ahead")
    p.add_argument("--dt", type=float, default=0.004, help="motor step seconds (1-5ms)")
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    args.dt = min(0.005, max(0.001, float(args.dt)))
    try:
        asyncio.run(run_play(args))
    except KeyboardInterrupt:
        print("interrupted", flush=True)


if __name__ == "__main__":
    main()
