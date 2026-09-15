"""CLI play loop: WebSocket session driven by chart zip uploads from the web UI."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import warnings
from dataclasses import dataclass, field
from typing import Any, Never

from websockets.asyncio.server import broadcast, serve

from fly_rg.brain_backend import MockBrain, make_brain
from fly_rg.chart import list_difficulties, parse_simai_subset
from fly_rg.decoder import ActionDecoder
from fly_rg.encoder import ON_PAD_TTH_S, NoteEncoder
from fly_rg.judge import Judge
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
from fly_rg.schema import Chart
from fly_rg.sensors import nearest_sensor

STATE_PERIOD_S = 0.016
SPIKE_PERIOD_S = 0.050
LOG_PERIOD_S = 0.5
BRAIN_WARMUP = 16
OVERRUN_MEAN_S = 0.008


@dataclass
class Session:
    chart: Chart | None = None
    play_task: asyncio.Task | None = None
    stop_event: asyncio.Event = field(default_factory=asyncio.Event)
    clients: set = field(default_factory=set)
    last_resources: dict[str, Any] | None = None


def _error(message: str) -> dict[str, Any]:
    return {"type": "error", "message": message}


def _levels_message(maidata: str) -> dict[str, Any]:
    return {"type": "levels", "levels": list_difficulties(maidata)}


def _press_sensor(x: float, y: float) -> str | None:
    return nearest_sensor(x, y)


def _want_press(
    *,
    tap: bool,
    occupancy: str | None,
    intended: str | None,
    slide_target: str | None,
    tth: float | None = None,
) -> bool:
    if occupancy is None or intended is None:
        return False
    if occupancy != intended:
        return False
    if slide_target is not None and occupancy == slide_target:
        return True
    if tap:
        return True
    return tth is not None and tth <= ON_PAD_TTH_S


def _contact_sensors(judge: Judge, now: float) -> set[str]:
    """Pads that should stay planted (hold sustain / in-progress slide)."""
    out: set[str] = set()
    for i, note in enumerate(judge.notes):
        nt = note.type
        if nt == "hold" or nt == "touch_hold":
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
    while True:
        try:
            stats = monitor.sample()
            session.last_resources = stats
            if session.clients:
                broadcast(session.clients, dumps(resources_message(stats)))
        except Exception:
            pass
        await asyncio.sleep(RESOURCE_PERIOD_S)


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
) -> None:
    def emit(msg: dict) -> None:
        if session.clients:
            broadcast(session.clients, dumps(msg))

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
        )
    )
    if not is_mock:
        try:
            brain.step(inject=[])
        except Exception:
            pass
    t0 = time.perf_counter()
    sim_t = 0.0
    step_i = 0
    session.stop_event.clear()
    motor_dt = float(args.dt)
    brain_dt = motor_dt
    next_brain_t = 0.0
    last_state_t = -1e9
    last_spikes_t = -1e9
    last_drive: dict[str, float] = {}
    last_fired: list = []
    overrun_logged = False
    step_times: list[float] = []
    last_brain_ms = 0.0
    last_log_t = -1e9
    brain_steps = 0

    print(
        f"playing {chart.title!r} notes={len(chart.notes)} end={end_t:.1f}s",
        flush=True,
    )

    while sim_t <= end_t:
        if session.stop_event.is_set() or not session.clients:
            print("play stopped", flush=True)
            return

        target = t0 + (sim_t / max(args.speed, 1e-9))
        delay = target - time.perf_counter()
        if delay > 0:
            await asyncio.sleep(delay)

        enc = encoder.encode(
            chart.notes,
            sim_t,
            look_ahead_s=args.look_ahead,
            dt=motor_dt,
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
            last_brain_ms = elapsed * 1000.0
            if not is_mock:
                brain_steps += 1
                if brain_steps <= 5 or brain_steps == BRAIN_WARMUP:
                    print(
                        f"brain step n={brain_steps} {last_brain_ms:.1f}ms "
                        f"(motor dt={motor_dt * 1000:.1f}ms)",
                        flush=True,
                    )
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
            dt=motor_dt,
            drive=last_drive,
            contact=_contact_sensors(judge, sim_t),
        )

        for miss in judge.auto_miss(sim_t):
            emit(
                hit_message(
                    t=miss.t,
                    button=miss.button,
                    sensor=miss.sensor,
                    judgment=miss.judgment,
                    timing=miss.timing,
                )
            )

        occupancy_l = _press_sensor(*dec.hand_l)
        press_l = _want_press(
            tap=dec.tap_l,
            occupancy=occupancy_l,
            intended=enc.target_l,
            slide_target=enc.slide_l,
            tth=enc.tth_l,
        )
        occupancy_r = _press_sensor(*dec.hand_r)
        press_r = _want_press(
            tap=dec.tap_r,
            occupancy=occupancy_r,
            intended=enc.target_r,
            slide_target=enc.slide_r,
            tth=enc.tth_r,
        )
        if press_l and occupancy_l is not None:
            hit = judge.press(occupancy_l, sim_t)
            if hit is not None:
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

        if sim_t + 1e-12 >= last_log_t + LOG_PERIOD_S:
            last_log_t = sim_t
            tth_l = f"{enc.tth_l:.3f}" if enc.tth_l is not None else "-"
            tth_r = f"{enc.tth_r:.3f}" if enc.tth_r is not None else "-"
            slide_l = enc.slide_l
            slide_r = enc.slide_r
            print(
                f"t={sim_t:.2f}s brain={last_brain_ms:.1f}ms/"
                f"{brain_dt * 1000:.0f}ms "
                f"L={dec.hand_l_sensor}->{enc.target_l} tth={tth_l} "
                f"w={dec.omega_l:.2f} tap={int(press_l)} "
                f"R={dec.hand_r_sensor}->{enc.target_r} tth={tth_r} "
                f"w={dec.omega_r:.2f} tap={int(press_r)} "
                f"growthL={enc.drive.get('growthL', 0.0):.2f} "
                f"growthR={enc.drive.get('growthR', 0.0):.2f} "
                f"slide={slide_l}/{slide_r} "
                f"C={judge.score.critical} M={judge.score.miss}",
                flush=True,
            )

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

        sim_t += motor_dt

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
        f"(upload a Majdata zip from the web UI)",
        flush=True,
    )

    encoder = NoteEncoder(brain if not is_mock else None, mock=is_mock)
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

    async def start_chart(chart: Chart) -> None:
        await stop_play()
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
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    await websocket.send(dumps(_error("invalid JSON")))
                    continue
                mtype = msg.get("type")
                if mtype == "inspect_chart":
                    maidata = str(msg.get("maidata") or "")
                    if not maidata.strip():
                        await websocket.send(dumps(_error("maidata is empty")))
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
                        with warnings.catch_warnings():
                            warnings.simplefilter("ignore", UserWarning)
                            chart = parse_simai_subset(maidata, difficulty=diff)
                    except Exception as exc:  # noqa: BLE001 — surface to UI
                        await websocket.send(dumps(_error(str(exc))))
                        continue
                    if not chart.notes:
                        await websocket.send(dumps(_error("chart has no playable notes")))
                        continue
                    await start_chart(chart)
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
        async with serve(handler, args.host, args.port):
            print(
                f"websocket ws://{args.host}:{args.port} — waiting for zip upload from the UI",
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
