"""Play-loop occupancy press, hold/slide contact, and state emit timing."""

from __future__ import annotations

import argparse
import asyncio
import time

import pytest

from fly_rg.brain_backend import MockBrain
from fly_rg.chart import parse_simai_subset
from fly_rg.decoder import ActionDecoder
from fly_rg.encoder import ON_PAD_TTH_S, NoteEncoder
from fly_rg.judge import HitEvent, Judge
from fly_rg.neuron_view import NeuronAtlas
from fly_rg.play import (
    MAX_STEP_DT_S,
    STATE_PERIOD_S,
    TAP_LATCH_S,
    Session,
    TapLatch,
    _contact_sensors,
    _format_judgment_log,
    _pace,
    _play_once,
    _press_sensor,
    _state_due,
    _step_dt,
    _wall_sim_t,
    _want_press,
)
from fly_rg.protocol import chart_message
from fly_rg.schema import Chart, Note, SlideInfo
from fly_rg.sensors import sensor_xy

PLAY_LOOP_DT = 0.004

LIVE_SILENT_CHARTS = {
    "taps": "&inote_1=(120){4}1,2,3,4,5,6,7,8,",
    "each": "&inote_1=(120){4}1/5,2/6,3/7,4/8,",
    "touch": "&inote_1=(120){4}C,B1,E1,",
}


class SilentBrain(MockBrain):
    def step(self, inject=None, drive=None):
        super().step(inject=inject, drive=drive)
        return []


def _non_miss_count(judge: Judge) -> int:
    s = judge.score
    return s.critical + s.perfect + s.great + s.good


def _run_maidata_loop(maidata: str, *, silent: bool) -> Judge:
    chart = parse_simai_subset(maidata, difficulty=1)
    brain = SilentBrain(dt=PLAY_LOOP_DT) if silent else MockBrain(dt=PLAY_LOOP_DT)
    enc = NoteEncoder(mock=True)
    dec = ActionDecoder(brain, mock=True, seed=0)
    judge = Judge(chart.notes)
    latch = TapLatch()
    end = (
        max(
            max(
                n.t,
                n.end if n.end is not None else n.t,
                n.slide.end_t if n.slide is not None else n.t,
            )
            for n in chart.notes
        )
        + 1.0
    )
    now = 0.0
    while now <= end:
        enc_r = enc.encode(
            chart.notes,
            now,
            look_ahead_s=1.0,
            dt=PLAY_LOOP_DT,
            slide_next=judge.slide_next,
            matched=judge.matched,
            hand_l=dec.hand_l,
            hand_r=dec.hand_r,
        )
        fired = brain.step(drive=enc_r.drive)
        dec.observe(fired)
        res = dec.decode(
            now,
            dt=PLAY_LOOP_DT,
            drive=brain.last_inject,
            contact=_contact_sensors(judge, now),
        )
        occupancy_l = _press_sensor(*res.hand_l)
        occupancy_r = _press_sensor(*res.hand_r)
        judge.auto_miss(
            now,
            {s for s in (occupancy_l, occupancy_r) if s is not None},
        )
        if res.tap_l:
            latch.arm("L", now)
        if res.tap_r:
            latch.arm("R", now)
        for side, occ, intended, tth in (
            ("L", occupancy_l, enc_r.target_l, enc_r.tth_l),
            ("R", occupancy_r, enc_r.target_r, enc_r.tth_r),
        ):
            if occ is not None and _want_press(
                tap=latch.is_armed(side, now),
                occupancy=occ,
                intended=intended,
                tth=tth,
            ):
                judge.press(occ, now)
        now += PLAY_LOOP_DT
    return judge


def test_press_sensor_is_occupancy_only():
    assert _press_sensor(*sensor_xy("A5")) == "A5"
    assert _press_sensor(0.0, 0.50) is None


def test_contact_sensors_hold_after_match():
    notes = [Note(t=1.0, button=5, type="hold", sensor="A5", end=2.0)]
    judge = Judge(notes)
    assert _contact_sensors(judge, 1.5) == set()
    head = judge.press("A5", 1.0)
    assert head is not None
    assert not judge.matched[0]
    assert 0 in judge._live
    assert "A5" in _contact_sensors(judge, 1.0)
    assert "A5" in _contact_sensors(judge, 1.5)
    assert "A5" in _contact_sensors(judge, 2.0)
    assert "A5" not in _contact_sensors(judge, 2.1)

    planted = Judge(notes)
    planted.press("A5", 1.0)
    planted_events = planted.auto_miss(2.01, {"A5"})
    assert len(planted_events) == 1
    assert planted.matched[0]
    assert planted_events[0].judgment != "miss"
    assert planted._live == set()
    assert _contact_sensors(planted, 2.01) == set()

    unwired = Judge(notes)
    unwired.press("A5", 1.0)
    none_events = unwired.auto_miss(2.01)
    assert len(none_events) == 1
    assert none_events[0].judgment != "miss"
    assert unwired.matched[0]
    assert unwired.score.miss == 0


def test_contact_sensors_touch_hold_uses_live():
    notes = [Note(t=1.0, button=0, type="touch_hold", sensor="C", end=2.0)]
    judge = Judge(notes)
    assert _contact_sensors(judge, 1.5) == set()
    head = judge.press("C", 1.0)
    assert head is not None
    assert not judge.matched[0]
    assert "C" in _contact_sensors(judge, 1.5)
    assert "C" not in _contact_sensors(judge, 2.1)


def test_contact_sensors_taps_and_touches_empty():
    notes = [
        Note(t=1.0, button=1, type="tap", sensor="A1"),
        Note(t=1.0, button=0, type="touch", sensor="C"),
    ]
    judge = Judge(notes)
    judge.press("A1", 1.0)
    judge.press("C", 1.0)
    assert judge._live == set()
    assert _contact_sensors(judge, 1.0) == set()


def test_contact_sensors_slide_until_end():
    notes = [
        Note(
            t=1.0,
            button=1,
            type="slide",
            sensor="A1",
            slide=SlideInfo(
                shape="-",
                end_sensor="A5",
                path=("A1", "B1", "A5"),
                end_t=2.0,
            ),
        )
    ]
    judge = Judge(notes)
    assert _contact_sensors(judge, 1.2) == set()
    judge.press("A1", 1.0)
    assert not judge.matched[0]
    assert 0 in judge._live
    assert "B1" in _contact_sensors(judge, 1.2)
    judge.press("B1", 1.3)
    assert "A5" in _contact_sensors(judge, 1.4)
    judge.press("A5", 1.6)
    assert judge.matched[0]
    assert judge._live == set()
    assert _contact_sensors(judge, 1.8) == set()
    assert _contact_sensors(judge, 2.1) == set()


def test_state_due_emits_pulses_immediately():
    period = 0.008
    assert _state_due(0.004, 0.0, period, tap=True, strike_l=0.0, strike_r=0.0)
    assert not _state_due(0.004, 0.0, period, tap=False, strike_l=1.0, strike_r=0.0)
    assert not _state_due(0.004, 0.0, period, tap=False, strike_l=0.0, strike_r=1.0)
    assert not _state_due(0.004, 0.0, period, tap=False, strike_l=0.0, strike_r=0.0)
    assert _state_due(0.008, 0.0, period, tap=False, strike_l=0.0, strike_r=0.0)


def test_state_period_is_16ms():
    assert STATE_PERIOD_S == 0.016


def test_want_press_requires_spike_latch_and_on_pad_tth():
    assert not _want_press(
        tap=False,
        occupancy="B1",
        intended="B1",
        tth=0.0,
    )
    assert not _want_press(
        tap=True,
        occupancy="B1",
        intended="B1",
        tth=0.20,
    )
    assert _want_press(
        tap=True,
        occupancy="B1",
        intended="B1",
        tth=ON_PAD_TTH_S,
    )


def test_want_press_hovering_idle():
    assert not _want_press(
        tap=False,
        occupancy="A5",
        intended=None,
    )
    assert not _want_press(
        tap=False,
        occupancy="A5",
        intended="A5",
    )


def test_want_press_wrong_pad():
    assert not _want_press(
        tap=True,
        occupancy="A5",
        intended="A6",
    )


def test_want_press_tap_does_not_fire_150ms_early():
    assert not _want_press(
        tap=True,
        occupancy="A6",
        intended="A6",
        tth=0.150,
    )


def test_want_press_correct_tap():
    assert _want_press(
        tap=True,
        occupancy="A6",
        intended="A6",
        tth=ON_PAD_TTH_S,
    )


def test_want_press_without_tap_never_commits():
    assert not _want_press(
        tap=False,
        occupancy="A2",
        intended="A2",
        tth=0.0,
    )
    assert not _want_press(
        tap=False,
        occupancy="A2",
        intended="A2",
        tth=ON_PAD_TTH_S,
    )


def test_want_press_hover_on_intended_pad_before_commit():
    assert not _want_press(
        tap=False,
        occupancy="A2",
        intended="A2",
        tth=0.20,
    )


def test_dense_taps_are_pressed_on_commit_not_only_rising_edge():
    dt = PLAY_LOOP_DT
    notes: list[Note] = []
    t = 0.25
    for i in range(40):
        button = 1 + (i % 8)
        notes.append(Note(t=t, button=button, type="tap", sensor=f"A{button}"))
        t += 0.07
    enc = NoteEncoder(mock=True)
    brain = MockBrain(dt=dt)
    dec = ActionDecoder(brain)
    judge = Judge(notes)
    latch = TapLatch()
    now = 0.0
    end = notes[-1].t + 0.4
    while now <= end:
        enc_r = enc.encode(
            notes,
            now,
            look_ahead_s=1.0,
            dt=dt,
            slide_next=judge.slide_next,
            matched=judge.matched,
            hand_l=dec.hand_l,
            hand_r=dec.hand_r,
        )
        fired = brain.step(drive=enc_r.drive)
        dec.observe(fired)
        result = dec.decode(now, dt=dt, drive=enc_r.drive)
        for _miss in judge.auto_miss(now):
            pass
        if result.tap_l:
            latch.arm("L", now)
        if result.tap_r:
            latch.arm("R", now)
        for side, xy, intended, tth in (
            ("L", result.hand_l, enc_r.target_l, enc_r.tth_l),
            ("R", result.hand_r, enc_r.target_r, enc_r.tth_r),
        ):
            occ = _press_sensor(*xy)
            if _want_press(
                tap=latch.is_armed(side, now),
                occupancy=occ,
                intended=intended,
                tth=tth,
            ):
                judge.press(occ, now)
        now += dt
    assert judge.score.miss <= 5
    assert judge.score.miss + judge.score.critical + judge.score.perfect + judge.score.great + judge.score.good == 40


def test_tap_latch_arm_duration_and_rearm():
    latch = TapLatch()
    t0 = 0.0
    latch.arm("L", t0)
    assert latch.is_armed("L", t0)
    assert latch.is_armed("L", t0 + TAP_LATCH_S)
    assert not latch.is_armed("L", t0 + TAP_LATCH_S + 1e-6)
    latch.arm("L", t0 + 0.03)
    assert latch.is_armed("L", t0 + 0.03 + TAP_LATCH_S)
    assert not latch.is_armed("R", t0)


@pytest.mark.parametrize("chart_key", tuple(LIVE_SILENT_CHARTS))
def test_live_mockbrain_scores_more_than_silent(chart_key: str):
    maidata = LIVE_SILENT_CHARTS[chart_key]
    silent = _run_maidata_loop(maidata, silent=True)
    live = _run_maidata_loop(maidata, silent=False)
    assert _non_miss_count(silent) == 0
    assert _non_miss_count(live) > _non_miss_count(silent)


def test_chart_message_includes_active_preview():
    notes = [Note(t=0.5, button=6, type="tap", sensor="A6")]
    chart = Chart(title="T", artist="A", notes=notes)
    judge = Judge(notes)
    active = judge.active_notes(0.0, 1.0)
    active_sensors = judge.active_sensors(0.0, 1.0)
    assert active
    msg = chart_message(chart, active=active, active_sensors=active_sensors)
    assert msg["type"] == "chart"
    assert msg["title"] == "T"
    assert msg["artist"] == "A"
    assert msg["notes"]
    assert msg["active"] == active
    assert msg["active_sensors"] == active_sensors


def test_chart_message_omits_active_when_not_passed():
    chart = Chart(title="X", artist="Y", notes=[])
    msg = chart_message(chart)
    assert "active" not in msg
    assert "active_sensors" not in msg
    assert "warnings" not in msg


def test_format_judgment_log_fast_late_and_skip_waypoint():
    note = Note(t=1.0, button=1, type="tap", sensor="A1")
    fast = HitEvent(
        t=0.980,
        button=1,
        judgment="perfect",
        note_index=0,
        sensor="A1",
        timing="fast",
        error_ms=-20.0,
    )
    late = HitEvent(
        t=1.020,
        button=1,
        judgment="perfect",
        note_index=0,
        sensor="A1",
        timing="late",
        error_ms=20.0,
    )
    crit = HitEvent(
        t=1.0,
        button=1,
        judgment="critical",
        note_index=0,
        sensor="A1",
        error_ms=0.0,
    )
    waypoint = HitEvent(
        t=1.2,
        button=1,
        judgment="perfect",
        note_index=0,
        sensor="B1",
        error_ms=None,
    )
    missed = HitEvent(
        t=1.16,
        button=1,
        judgment="miss",
        note_index=0,
        sensor="A1",
        error_ms=160.0,
    )
    assert _format_judgment_log(fast, note) == "judge perfect FAST 20.0ms A1 tap"
    assert _format_judgment_log(late, note) == "judge perfect LATE 20.0ms A1 tap"
    assert _format_judgment_log(crit, note) == "judge critical 0.0ms A1 tap"
    assert _format_judgment_log(waypoint, note) is None
    assert _format_judgment_log(missed, note) == "judge miss LATE 160.0ms A1 tap"


def test_step_dt_uses_wall_gap_without_catchup_burst():
    assert _step_dt(0.0, 0.0, 0.004) == 0.004
    assert _step_dt(1.0, 1.004, 0.004) == pytest.approx(0.004)
    assert _step_dt(1.0, 1.020, 0.004) == pytest.approx(0.020)
    assert _step_dt(1.0, 1.5, 0.004) == MAX_STEP_DT_S


def test_wall_sim_t_tracks_elapsed(monkeypatch) -> None:
    clock = {"t": 10.0}

    def fake_counter() -> float:
        return clock["t"]

    monkeypatch.setattr(time, "perf_counter", fake_counter)
    assert _wall_sim_t(10.0, 1.0) == pytest.approx(0.0)
    clock["t"] = 10.25
    assert _wall_sim_t(10.0, 1.0) == pytest.approx(0.25)
    assert _wall_sim_t(10.0, 2.0) == pytest.approx(0.50)


def test_pace_yields_when_clock_is_behind():
    async def main() -> None:
        flag = {"ok": False}

        async def mark() -> None:
            flag["ok"] = True

        task = asyncio.create_task(mark())
        await _pace(-1.0)
        await task
        assert flag["ok"]

    asyncio.run(main())


def test_stop_event_halts_play_when_behind_realtime(monkeypatch) -> None:
    monkeypatch.setattr("fly_rg.play.broadcast", lambda *_a, **_k: None)

    orig_encode = NoteEncoder.encode

    def slow_encode(self, *args, **kwargs):
        time.sleep(0.015)
        return orig_encode(self, *args, **kwargs)

    monkeypatch.setattr(NoteEncoder, "encode", slow_encode)

    async def main() -> None:
        args = argparse.Namespace(dt=0.004, speed=1.0, look_ahead=1.0)
        session = Session()
        session.clients.add(object())
        chart = Chart(
            title="t",
            artist="a",
            notes=[Note(t=8.0, button=1, type="tap", sensor="A1")],
        )
        task = asyncio.create_task(
            _play_once(
                session=session,
                chart=chart,
                brain=MockBrain(dt=0.004),
                is_mock=True,
                encoder=NoteEncoder(mock=True),
                atlas=NeuronAtlas(n=24, seed=0),
                args=args,
            )
        )

        async def stop_soon() -> None:
            await asyncio.sleep(0.05)
            session.stop_event.set()

        asyncio.create_task(stop_soon())
        await asyncio.wait_for(task, timeout=0.5)

    asyncio.run(main())
