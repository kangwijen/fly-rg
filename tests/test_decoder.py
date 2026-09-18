"""Cartesian motor: DNa glide, DNp onset pulse, press at current XY."""

from __future__ import annotations

import math

import pytest

from fly_rg.brain_backend import MockBrain
from fly_rg.decoder import TAP_COOLDOWN_S, TAP_TYPES, V_MAX, ActionDecoder
from fly_rg.encoder import NoteEncoder
from fly_rg.judge import Judge
from fly_rg.play import _contact_sensors
from fly_rg.schema import Note, SlideInfo
from fly_rg.sensors import nearest_sensor, sensor_xy

DT = 0.004


def _quiet_drive(**overrides: float) -> dict[str, float]:
    drive = {
        "loomL": 0.0,
        "loomR": 0.0,
        "chaseL": 0.0,
        "chaseR": 0.0,
        "threatL": 0.0,
        "threatR": 0.0,
        "cwL": 0.0,
        "cwR": 0.0,
        "ccwL": 0.0,
        "ccwR": 0.0,
        "inL": 0.0,
        "inR": 0.0,
        "outL": 0.0,
        "outR": 0.0,
        "eastL": 0.0,
        "eastR": 0.0,
        "westL": 0.0,
        "westR": 0.0,
        "northL": 0.0,
        "northR": 0.0,
        "southL": 0.0,
        "southR": 0.0,
        "growthL": 0.0,
        "growthR": 0.0,
    }
    drive.update(overrides)
    return drive


def _motor(
    dec: ActionDecoder,
    brain: MockBrain,
    drive: dict[str, float],
    now: float,
    *,
    dt: float = DT,
):
    fired = brain.step(drive=drive)
    dec.observe(fired)
    return dec.decode(now, dt=dt, drive=drive), fired


def test_decoder_starts_on_a6_a3_rest():
    dec = ActionDecoder(MockBrain(dt=DT))
    assert nearest_sensor(*dec.hand_l) == "A6"
    assert nearest_sensor(*dec.hand_r) == "A3"


def test_positive_east_increases_x():
    brain = MockBrain(dt=DT)
    dec = ActionDecoder(brain)
    x0 = dec.hand_l[0]
    result, fired = _motor(dec, brain, _quiet_drive(eastL=1.0), 0.0)
    dna01 = set(brain.cells(["DNa01"], "L"))
    dna02 = set(brain.cells(["DNa02"], "L"))
    dna03 = set(brain.cells(["DNa03"], "L"))
    assert dna01 & set(fired)
    assert not (dna02 & set(fired))
    assert not (dna03 & set(fired))
    assert result.omega_l != 0.0 or dec.hand_l[0] > x0
    assert dec.hand_l[0] > x0
    assert result.hand_l[0] == pytest.approx(dec.hand_l[0], abs=1e-9)


def test_hand_stays_on_disk_when_driving_east():
    brain = MockBrain(dt=DT)
    dec = ActionDecoder(brain)
    dec.x_l, dec.y_l = 0.96, 0.0
    now = 0.0
    for _ in range(40):
        _motor(dec, brain, _quiet_drive(eastL=1.0), now)
        now += DT
        assert math.hypot(dec.x_l, dec.y_l) <= 1.0 + 1e-9


def test_tap_uses_nearest_sensor_to_xy():
    brain = MockBrain(dt=DT)
    dec = ActionDecoder(brain)
    dec.x_l, dec.y_l = sensor_xy("B5")
    result, _fired = _motor(dec, brain, _quiet_drive(growthL=1.0), 0.0)
    assert result.tap_l
    assert result.strike_l == pytest.approx(1.0)
    occ = nearest_sensor(*result.hand_l)
    assert occ == "B5"
    assert result.hand_l_sensor == occ
    assert result.hand_l_sensor != "A6"


def test_decoder_tap_is_spike_only_not_growth_drive():
    brain = MockBrain(dt=DT)
    dec = ActionDecoder(brain)
    dec.observe([])
    result = dec.decode(0.0, dt=DT, drive=_quiet_drive(growthL=1.0, growthR=1.0))
    assert not result.tap_l
    assert not result.tap_r
    tap_cell = brain.cells(list(TAP_TYPES), "L")[0]
    dec.observe([tap_cell])
    spiked = dec.decode(0.004, dt=DT, drive=_quiet_drive())
    assert spiked.tap_l
    assert spiked.strike_l == pytest.approx(1.0)


def test_tap_cooldown_suppresses_second_edge_within_window():
    brain = MockBrain(dt=DT)
    dec = ActionDecoder(brain)
    tap_cell = brain.cells(list(TAP_TYPES), "L")[0]
    edges = 0
    for step_i, now in enumerate((0.0, 0.004)):
        dec.observe([tap_cell])
        result = dec.decode(now, dt=DT, drive=_quiet_drive())
        if result.tap_l:
            edges += 1
        dec.observe([])
        dec.decode(now + DT / 2, dt=DT, drive=_quiet_drive())
    assert edges == 1


def test_idle_rest_blobs_drift_toward_homes_without_jump():
    brain = MockBrain(dt=DT)
    dec = ActionDecoder(brain)
    enc = NoteEncoder(mock=True)
    a5 = sensor_xy("A5")
    a6 = sensor_xy("A6")
    dec.x_l = a5[0] + 0.55 * (a6[0] - a5[0])
    dec.y_l = a5[1] + 0.55 * (a6[1] - a5[1])
    dist0 = math.hypot(dec.hand_l[0] - a6[0], dec.hand_l[1] - a6[1])
    now = 0.0
    prev = dec.hand_l
    max_step = 0.0
    for _ in range(80):
        enc_r = enc.encode(
            [],
            now,
            look_ahead_s=1.0,
            dt=DT,
            hand_l=dec.hand_l,
            hand_r=dec.hand_r,
        )
        _motor(dec, brain, enc_r.drive, now)
        cur = dec.hand_l
        max_step = max(
            max_step, math.hypot(cur[0] - prev[0], cur[1] - prev[1])
        )
        prev = cur
        now += DT
    dist1 = math.hypot(dec.hand_l[0] - a6[0], dec.hand_l[1] - a6[1])
    assert dist1 < dist0
    assert max_step < 0.08


def test_two_notes_one_step_does_not_teleport():
    brain = MockBrain(dt=DT)
    dec = ActionDecoder(brain)
    enc = NoteEncoder(mock=True)
    notes = [
        Note(t=1.0, button=1, type="tap", sensor="A1"),
        Note(t=1.0, button=6, type="tap", sensor="A6"),
    ]
    a6 = sensor_xy("A6")
    a3 = sensor_xy("A3")
    enc_r = enc.encode(
        notes,
        0.5,
        look_ahead_s=1.0,
        dt=DT,
        hand_l=dec.hand_l,
        hand_r=dec.hand_r,
    )
    result, _fired = _motor(dec, brain, enc_r.drive, 0.5)
    assert math.hypot(result.hand_l[0] - a6[0], result.hand_l[1] - a6[1]) < 0.12
    assert math.hypot(result.hand_r[0] - a3[0], result.hand_r[1] - a3[1]) < 0.15
    assert result.hand_r_sensor != "A1"


def test_intercept_arrives_and_taps_near_hit():
    notes = [Note(t=0.40, button=8, type="tap", sensor="A8")]
    enc = NoteEncoder(mock=True)
    brain = MockBrain(dt=DT)
    dec = ActionDecoder(brain)
    a8 = sensor_xy("A8")
    tap_times: list[float] = []
    now = 0.0
    while now <= 0.42:
        enc_r = enc.encode(
            notes,
            now,
            look_ahead_s=1.0,
            dt=DT,
            hand_l=dec.hand_l,
            hand_r=dec.hand_r,
        )
        result, _fired = _motor(dec, brain, enc_r.drive, now)
        if result.tap_l:
            tap_times.append(now)
        now += DT
    dist = math.hypot(dec.hand_l[0] - a8[0], dec.hand_l[1] - a8[1])
    assert dist < 0.22
    assert nearest_sensor(*dec.hand_l) == "A8"
    assert tap_times
    assert min(abs(t - 0.40) for t in tap_times) < 0.05


def test_jack_two_presses_with_lift_between():
    brain = MockBrain(dt=DT)
    dec = ActionDecoder(brain)
    now = 0.0
    first, _f1 = _motor(dec, brain, _quiet_drive(growthL=1.0), now)
    assert first.tap_l
    assert first.strike_l == pytest.approx(1.0)
    now += DT
    lifted, _f2 = _motor(dec, brain, _quiet_drive(), now)
    assert not lifted.tap_l
    assert lifted.strike_l == pytest.approx(0.0)
    while now < TAP_COOLDOWN_S + DT:
        now += DT
        _motor(dec, brain, _quiet_drive(), now)
    now += DT
    second, _f3 = _motor(dec, brain, _quiet_drive(growthL=1.0), now)
    assert second.tap_l
    assert second.strike_l == pytest.approx(1.0)


def test_trill_two_hands_pulse_without_glue():
    brain = MockBrain(dt=DT)
    dec = ActionDecoder(brain)
    result, _fired = _motor(
        dec, brain, _quiet_drive(growthL=1.0, growthR=1.0), 0.0
    )
    assert result.tap_l
    assert result.tap_r
    lifted, _f2 = _motor(dec, brain, _quiet_drive(), DT)
    assert lifted.strike_l == pytest.approx(0.0)
    assert lifted.strike_r == pytest.approx(0.0)
    assert not lifted.tap_l
    assert not lifted.tap_r


def test_dt_four_ms_integration():
    brain = MockBrain(dt=DT)
    dec = ActionDecoder(brain)
    x0 = dec.x_l
    result, _fired = _motor(dec, brain, _quiet_drive(eastL=1.0), 0.0, dt=DT)
    assert DT == pytest.approx(0.004)
    assert result.hand_l[0] == pytest.approx(x0 + V_MAX * DT, abs=1e-6)
    assert dec.x_l == pytest.approx(x0 + V_MAX * DT, abs=1e-6)


def test_north_increases_y():
    brain = MockBrain(dt=DT)
    dec = ActionDecoder(brain)
    y0 = dec.hand_l[1]
    result, _fired = _motor(dec, brain, _quiet_drive(northL=1.0), 0.0)
    assert dec.hand_l[1] > y0
    assert result.hand_l[1] > y0


def test_encoder_jack_two_taps_with_lift_between():
    notes = [
        Note(t=1.00, button=5, type="tap", sensor="A5"),
        Note(t=1.05, button=5, type="tap", sensor="A5"),
    ]
    enc = NoteEncoder(mock=True)
    brain = MockBrain(dt=DT)
    dec = ActionDecoder(brain)
    home_l = sensor_xy("A5")
    home_r = sensor_xy("A3")
    matched = [False, False]
    tap_times: list[float] = []
    strike_trace: list[tuple[float, float]] = []
    now = 0.96
    while now <= 1.08:
        dec.x_l, dec.y_l = home_l
        dec.x_r, dec.y_r = home_r
        enc_r = enc.encode(
            notes,
            now,
            look_ahead_s=1.0,
            dt=DT,
            hand_l=dec.hand_l,
            hand_r=dec.hand_r,
            matched=matched,
        )
        result, _fired = _motor(dec, brain, enc_r.drive, now)
        strike_trace.append((now, result.strike_l))
        if result.tap_l:
            tap_times.append(now)
            for i, flag in enumerate(matched):
                if not flag:
                    matched[i] = True
                    break
        now += DT
    assert len(tap_times) == 2
    assert tap_times[1] - tap_times[0] > TAP_COOLDOWN_S
    between = [
        strike
        for t, strike in strike_trace
        if tap_times[0] + DT / 2 < t < tap_times[1] - DT / 2
    ]
    assert between
    assert any(s == pytest.approx(0.0) for s in between)


def test_right_hemisphere_blob_does_not_tap_left():
    notes = [Note(t=1.0, button=1, type="tap", sensor="A1")]
    enc = NoteEncoder(mock=True)
    brain = MockBrain(dt=DT)
    dec = ActionDecoder(brain)
    home_l = sensor_xy("A5")
    home_r = sensor_xy("A3")
    now = 0.96
    while now <= 1.04:
        dec.x_l, dec.y_l = home_l
        dec.x_r, dec.y_r = home_r
        enc_r = enc.encode(
            notes,
            now,
            look_ahead_s=1.0,
            dt=DT,
            hand_l=dec.hand_l,
            hand_r=dec.hand_r,
        )
        assert enc_r.drive["growthL"] == 0.0
        result, _fired = _motor(dec, brain, enc_r.drive, now)
        assert not result.tap_l
        now += DT


def test_hold_contact_keeps_strike_while_on_pad():
    notes = [Note(t=1.0, button=5, type="hold", sensor="A5", end=2.0)]
    judge = Judge(notes)
    judge.press("A5", 1.0)
    contact = _contact_sensors(judge, 1.2)
    brain = MockBrain(dt=DT)
    dec = ActionDecoder(brain)
    dec.x_l, dec.y_l = sensor_xy("A5")
    fired = brain.step(drive=_quiet_drive())
    dec.observe(fired)
    result = dec.decode(1.2, dt=DT, drive=_quiet_drive(), contact=contact)
    assert result.hand_l_sensor == "A5"
    assert result.strike_l == pytest.approx(1.0)
    assert not result.tap_l


def test_mid_song_gap_does_not_drift_to_rest_homes():
    brain = MockBrain(dt=DT)
    dec = ActionDecoder(brain)
    enc = NoteEncoder(mock=True)
    notes = [
        Note(t=1.0, button=5, type="tap", sensor="A5"),
        Note(t=10.0, button=1, type="tap", sensor="A1"),
    ]
    dec.x_l, dec.y_l = sensor_xy("B5")
    dec.x_r, dec.y_r = sensor_xy("B1")
    a6 = sensor_xy("A6")
    a3 = sensor_xy("A3")
    dist_l0 = math.hypot(dec.hand_l[0] - a6[0], dec.hand_l[1] - a6[1])
    dist_r0 = math.hypot(dec.hand_r[0] - a3[0], dec.hand_r[1] - a3[1])
    now = 5.0
    for _ in range(120):
        enc_r = enc.encode(
            notes,
            now,
            look_ahead_s=1.0,
            dt=DT,
            hand_l=dec.hand_l,
            hand_r=dec.hand_r,
        )
        assert enc_r.drive["growthL"] == 0.0
        assert enc_r.drive["growthR"] == 0.0
        _motor(dec, brain, enc_r.drive, now)
        now += DT
    dist_l1 = math.hypot(dec.hand_l[0] - a6[0], dec.hand_l[1] - a6[1])
    dist_r1 = math.hypot(dec.hand_r[0] - a3[0], dec.hand_r[1] - a3[1])
    assert dist_l1 >= dist_l0 - 0.02
    assert dist_r1 >= dist_r0 - 0.02


def test_slide_abc_follow_crosses_center_after_b5():
    notes = [
        Note(
            t=1.0,
            button=5,
            type="slide",
            sensor="A5",
            slide=SlideInfo(
                shape="-",
                end_sensor="C",
                path=("A5", "B5", "C"),
                wait_t=1.0,
                end_t=2.0,
            ),
        )
    ]
    enc = NoteEncoder(mock=True)
    brain = MockBrain(dt=DT)
    dec = ActionDecoder(brain)
    judge = Judge(notes)
    dec.x_l, dec.y_l = sensor_xy("B5")
    dec.x_r, dec.y_r = sensor_xy("A3")
    judge.slide_next[0] = 1
    now = 1.05
    r_trace: list[float] = []
    while now <= 2.05:
        enc_r = enc.encode(
            notes,
            now,
            look_ahead_s=1.0,
            dt=DT,
            slide_next=judge.slide_next,
            hand_l=dec.hand_l,
            hand_r=dec.hand_r,
        )
        occ_l = nearest_sensor(*dec.hand_l)
        if enc_r.target_l is not None and occ_l == enc_r.target_l:
            judge.press(occ_l, now)
        _motor(dec, brain, enc_r.drive, now)
        r_trace.append(math.hypot(*dec.hand_l))
        now += DT
    assert min(r_trace[-40:]) < min(r_trace[:20]) - 0.05


def test_glide_a8_to_a4_crosses_interior():
    notes = [
        Note(t=0.25, button=4, type="tap", sensor="A4"),
        Note(t=0.25, button=3, type="tap", sensor="A3"),
    ]
    enc = NoteEncoder(mock=True)
    brain = MockBrain(dt=DT)
    dec = ActionDecoder(brain)
    dec.x_l, dec.y_l = sensor_xy("A8")
    dec.x_r, dec.y_r = sensor_xy("A3")
    now = 0.0
    while now < 0.12:
        enc_r = enc.encode(
            notes,
            now,
            look_ahead_s=1.0,
            dt=DT,
            hand_l=dec.hand_l,
            hand_r=dec.hand_r,
        )
        _motor(dec, brain, enc_r.drive, now)
        now += DT
    assert enc_r.target_l == "A4"
    assert math.hypot(*dec.hand_l) < 0.55
