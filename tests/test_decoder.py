"""Polar motor: DNa spin/reach, DNp onset pulse, press at current XY."""

from __future__ import annotations

import math

import pytest

from fly_rg.brain_backend import MockBrain
from fly_rg.decoder import TAP_COOLDOWN_S, ActionDecoder
from fly_rg.encoder import NoteEncoder
from fly_rg.schema import Note
from fly_rg.sensors import nearest_sensor, sensor_polar, sensor_xy, wrap_angle

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


def test_positive_spin_fires_dna01_and_theta_increases():
    brain = MockBrain(dt=DT)
    dec = ActionDecoder(brain)
    theta0 = dec.theta_l
    result, fired = _motor(dec, brain, _quiet_drive(ccwL=1.0), 0.0)
    dna01 = set(brain.cells(["DNa01"], "L"))
    dna02 = set(brain.cells(["DNa02"], "L"))
    dna03 = set(brain.cells(["DNa03"], "L"))
    assert dna01 & set(fired)
    assert not (dna02 & set(fired))
    assert not (dna03 & set(fired))
    assert result.omega_l > 0
    assert dec.theta_l > theta0
    assert result.hand_l[0] == pytest.approx(dec.hand_l[0], abs=1e-9)


def test_theta_wraps_past_two_pi():
    brain = MockBrain(dt=DT)
    dec = ActionDecoder(brain)
    dec.theta_l = math.pi - 0.04
    thetas = [dec.theta_l]
    now = 0.0
    for _ in range(24):
        _motor(dec, brain, _quiet_drive(ccwL=1.0), now)
        thetas.append(dec.theta_l)
        now += DT
        assert -math.pi - 1e-9 <= dec.theta_l <= math.pi + 1e-9
    wrapped = any(
        thetas[i] < 0.0 and thetas[i - 1] > 1.0 for i in range(1, len(thetas))
    )
    assert wrapped


def test_tap_uses_nearest_sensor_to_xy():
    brain = MockBrain(dt=DT)
    dec = ActionDecoder(brain)
    bx, by = sensor_xy("B5")
    dec.theta_l, dec.r_l = math.atan2(by, bx), math.hypot(bx, by)
    result, _fired = _motor(dec, brain, _quiet_drive(growthL=1.0), 0.0)
    assert result.tap_l
    assert result.strike_l == pytest.approx(1.0)
    occ = nearest_sensor(*result.hand_l)
    assert occ == "B5"
    assert result.hand_l_sensor == occ
    assert result.hand_l_sensor != "A6"


def test_idle_rest_blobs_drift_toward_homes_without_jump():
    brain = MockBrain(dt=DT)
    dec = ActionDecoder(brain)
    enc = NoteEncoder(mock=True)
    t6, r6 = sensor_polar("A6")
    t5, r5 = sensor_polar("A5")
    dec.theta_l = t5 + 0.55 * wrap_angle(t6 - t5)
    dec.r_l = 0.5 * (r5 + r6)
    a5 = sensor_xy("A5")
    dist0 = math.hypot(dec.hand_l[0] - a5[0], dec.hand_l[1] - a5[1])
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
    dist1 = math.hypot(dec.hand_l[0] - a5[0], dec.hand_l[1] - a5[1])
    assert dist1 < dist0
    assert max_step < 0.08


def test_two_notes_inject_without_claiming_a6():
    brain = MockBrain(dt=DT)
    dec = ActionDecoder(brain)
    enc = NoteEncoder(mock=True)
    notes = [
        Note(t=1.0, button=1, type="tap", sensor="A1"),
        Note(t=1.0, button=6, type="tap", sensor="A6"),
    ]
    a5 = sensor_xy("A5")
    a4 = sensor_xy("A4")
    enc_r = enc.encode(
        notes,
        0.5,
        look_ahead_s=1.0,
        dt=DT,
        hand_l=dec.hand_l,
        hand_r=dec.hand_r,
    )
    result, _fired = _motor(dec, brain, enc_r.drive, 0.5)
    assert result.hand_l_sensor != "A6"
    assert math.hypot(result.hand_l[0] - a5[0], result.hand_l[1] - a5[1]) < 0.12
    assert math.hypot(result.hand_r[0] - a4[0], result.hand_r[1] - a4[1]) < 0.12


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
    theta0 = dec.theta_l
    result, _fired = _motor(dec, brain, _quiet_drive(ccwL=1.0), 0.0, dt=DT)
    assert DT == pytest.approx(0.004)
    assert result.omega_l * DT == pytest.approx(
        wrap_angle(dec.theta_l - theta0), abs=1e-6
    )


def test_reach_fallback_chase_minus_threat():
    brain = MockBrain(dt=DT)
    dec = ActionDecoder(brain)
    result, _fired = _motor(
        dec, brain, _quiet_drive(chaseL=0.9, threatL=0.1), 0.0
    )
    assert result.reach_l > 0
