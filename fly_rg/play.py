"""CLI play loop: chart -> encoder -> brain -> decoder -> judge -> WebSocket."""

from __future__ import annotations

import argparse
import asyncio
import time
from pathlib import Path

from websockets.asyncio.server import broadcast, serve

from fly_rg.brain_backend import MockBrain, make_brain
from fly_rg.chart import load_chart
from fly_rg.decoder import ActionDecoder
from fly_rg.encoder import NoteEncoder
from fly_rg.judge import Judge
from fly_rg.protocol import (
    chart_message,
    dumps,
    end_message,
    hello_message,
    hit_message,
    state_message,
)


async def run_play(args: argparse.Namespace) -> None:
    chart = load_chart(args.chart)
    brain, is_mock = make_brain(mock=args.mock, device=args.device)
    if args.mock:
        is_mock = True
    print(
        f"chart={chart.title!r} notes={len(chart.notes)} "
        f"brain={'mock' if is_mock else 'flybrain'} device={args.device}",
        flush=True,
    )

    encoder = NoteEncoder(brain if not is_mock else None, mock=is_mock)

    clients: set = set()

    async def handler(websocket) -> None:
        clients.add(websocket)
        try:
            await websocket.send(dumps(hello_message()))
            await websocket.send(dumps(chart_message(chart)))
            await websocket.wait_closed()
        finally:
            clients.discard(websocket)

    def emit(msg: dict) -> None:
        if clients:
            broadcast(clients, dumps(msg))

    last_note_t = max((n.t for n in chart.notes), default=0.0)
    end_t = last_note_t + 2.0

    async with serve(handler, args.host, args.port) as server:
        print(f"websocket ws://{args.host}:{args.port} (silent clock)", flush=True)
        await asyncio.sleep(0.05)

        while True:
            judge = Judge(chart.notes)
            decoder = ActionDecoder(brain if not is_mock else None, mock=is_mock, seed=0)
            t0 = time.perf_counter()
            sim_t = 0.0

            while sim_t <= end_t:
                target = t0 + (sim_t / max(args.speed, 1e-9))
                delay = target - time.perf_counter()
                if delay > 0:
                    await asyncio.sleep(delay)

                enc = encoder.encode(
                    chart.notes,
                    sim_t,
                    look_ahead_s=args.look_ahead,
                    dt=args.dt,
                )
                if is_mock and isinstance(brain, MockBrain):
                    fired = brain.step(drive=enc.drive)
                    last_drive = brain.last_inject
                else:
                    fired = brain.step(inject=enc.inject)
                    last_drive = enc.drive

                decoder.observe(fired)
                dec = decoder.decode(
                    sim_t,
                    chart.notes,
                    look_ahead_s=args.look_ahead,
                    drive=last_drive,
                    last_inject=getattr(brain, "last_inject", None),
                )

                for miss in judge.auto_miss(sim_t):
                    emit(hit_message(t=miss.t, button=miss.button, judgment=miss.judgment))

                if dec.tap and dec.tap_button is not None:
                    hit = judge.press(dec.tap_button, sim_t)
                    if hit is not None:
                        emit(hit_message(t=hit.t, button=hit.button, judgment=hit.judgment))

                emit(
                    state_message(
                        t=sim_t,
                        aim_button=dec.aim_button,
                        tap=dec.tap,
                        tap_button=dec.tap_button if dec.tap else None,
                        score=judge.score.to_dict(),
                        active=judge.active_notes(sim_t, args.look_ahead),
                        drive=enc.drive,
                        pose={"aim": dec.aim, "strike": dec.strike},
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
            if not args.loop:
                break
            print("loop: restarting chart", flush=True)

        await asyncio.sleep(0.1)
        server.close()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="fly-rg closed-loop maimai play")
    p.add_argument(
        "--chart",
        type=Path,
        default=Path("charts/demo/maidata.txt"),
        help="path to chart.json or maidata.txt",
    )
    p.add_argument("--mock", action="store_true", help="use MockBrain (no flybrain download)")
    p.add_argument("--device", default="auto", help="flybrain device: auto|cpu|cuda")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--speed", type=float, default=1.0, help="playback speed multiplier")
    p.add_argument("--look-ahead", type=float, default=1.0, dest="look_ahead")
    p.add_argument("--dt", type=float, default=0.02, help="simulation step seconds")
    p.add_argument("--loop", action="store_true", help="repeat chart after end")
    return p


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        asyncio.run(run_play(args))
    except KeyboardInterrupt:
        print("interrupted", flush=True)


if __name__ == "__main__":
    main()
