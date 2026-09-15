"""CLI play loop: WebSocket session driven by chart zip uploads from the web UI."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
import warnings
from dataclasses import dataclass, field
from typing import Any

from websockets.asyncio.server import broadcast, serve

from fly_rg.brain_backend import MockBrain, make_brain
from fly_rg.chart import list_difficulties, parse_simai_subset
from fly_rg.decoder import ActionDecoder
from fly_rg.encoder import NoteEncoder
from fly_rg.judge import Judge
from fly_rg.neuron_view import NeuronAtlas
from fly_rg.protocol import (
    chart_message,
    dumps,
    end_message,
    hello_message,
    hit_message,
    state_message,
)
from fly_rg.schema import Chart


@dataclass
class Session:
    chart: Chart | None = None
    play_task: asyncio.Task | None = None
    stop_event: asyncio.Event = field(default_factory=asyncio.Event)
    clients: set = field(default_factory=set)


def _error(message: str) -> dict[str, Any]:
    return {"type": "error", "message": message}


def _levels_message(maidata: str) -> dict[str, Any]:
    return {"type": "levels", "levels": list_difficulties(maidata)}


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
    decoder = ActionDecoder(brain if not is_mock else None, mock=is_mock, seed=0)
    t0 = time.perf_counter()
    sim_t = 0.0
    step_i = 0
    session.stop_event.clear()

    emit(chart_message(chart))
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
            dt=args.dt,
            slide_next=judge.slide_next,
        )
        if is_mock and isinstance(brain, MockBrain):
            fired = brain.step(drive=enc.drive)
            last_drive = brain.last_inject
        else:
            fired = brain.step(inject=enc.inject)
            last_drive = enc.drive

        fired_list = list(fired) if fired is not None else []
        decoder.observe(fired_list)
        dec = decoder.decode(
            sim_t,
            chart.notes,
            look_ahead_s=args.look_ahead,
            drive=last_drive,
            last_inject=getattr(brain, "last_inject", None),
            slide_next=judge.slide_next,
        )

        for miss in judge.auto_miss(sim_t):
            emit(
                hit_message(
                    t=miss.t,
                    button=miss.button,
                    sensor=miss.sensor,
                    judgment=miss.judgment,
                )
            )

        if dec.tap and dec.tap_sensor is not None:
            hit = judge.press(dec.tap_sensor, sim_t)
            if hit is not None:
                emit(
                    hit_message(
                        t=hit.t,
                        button=hit.button,
                        sensor=hit.sensor,
                        judgment=hit.judgment,
                    )
                )

        spikes = atlas.spikes_for(
            last_drive,
            aim=dec.aim,
            strike=dec.strike,
            fired_count=len(fired_list),
            step=step_i,
        )
        step_i += 1

        emit(
            state_message(
                t=sim_t,
                aim_button=dec.aim_button,
                aim_sensor=dec.aim_sensor,
                tap=dec.tap,
                tap_button=dec.tap_button if dec.tap else None,
                tap_sensor=dec.tap_sensor if dec.tap else None,
                score=judge.score.to_dict(),
                active=judge.active_notes(sim_t, args.look_ahead),
                active_sensors=judge.active_sensors(sim_t, args.look_ahead),
                drive=enc.drive,
                pose={"aim": dec.aim, "strike": dec.strike},
                spikes=spikes,
                spike_total=len(fired_list) if fired_list else len(spikes),
            )
        )

        sim_t += args.dt

    emit(end_message(judge.score.to_dict()))
    print(
        f"end accuracy={judge.score.accuracy:.3f} "
        f"P={judge.score.perfect} G={judge.score.great} "
        f"g={judge.score.good} M={judge.score.miss} combo={judge.score.combo}",
        flush=True,
    )


async def run_play(args: argparse.Namespace) -> None:
    brain, is_mock = make_brain(mock=args.mock, device=args.device)
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

    async with serve(handler, args.host, args.port):
        print(
            f"websocket ws://{args.host}:{args.port} — waiting for zip upload from the UI",
            flush=True,
        )
        await asyncio.Future()  # run forever


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
    p.add_argument("--dt", type=float, default=0.02, help="simulation step seconds")
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        asyncio.run(run_play(args))
    except KeyboardInterrupt:
        print("interrupted", flush=True)


if __name__ == "__main__":
    main()
