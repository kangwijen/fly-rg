"""Encoder chase drives every approaching side, not only the nearest note."""

from __future__ import annotations

from fly_rg.encoder import CHASE_TYPES, NoteEncoder
from fly_rg.schema import Note, SlideInfo
from fly_rg.sensors import sensor_xy


class _StubBrain:
    def __init__(self) -> None:
        self._ids: dict[tuple[tuple[str, ...], str], list[int]] = {}
        self._n = 1

    def cells(self, types: list[str], side: str) -> list[int]:
        key = (tuple(types), side)
        if key not in self._ids:
            self._ids[key] = [self._n]
            self._n += 1
        return self._ids[key]


def test_simultaneous_left_right_notes_drive_both_chase():
    notes = [
        Note(t=1.0, button=1, type="tap", sensor="A1"),
        Note(t=1.0, button=6, type="tap", sensor="A6"),
    ]
    enc = NoteEncoder(mock=True)
    result = enc.encode(notes, 0.5, look_ahead_s=1.0, dt=0.004)
    assert result.drive["chaseL"] > 0
    assert result.drive["chaseR"] > 0


def test_right_blob_does_not_copy_left_visual():
    notes = [Note(t=1.0, button=1, type="tap", sensor="A1")]
    enc = NoteEncoder(mock=True)
    result = enc.encode(notes, 0.5, look_ahead_s=1.0, dt=0.004)
    assert result.drive["chaseR"] > 0
    assert result.drive["threatR"] > 0
    assert result.drive["chaseL"] == 0
    assert result.drive["threatL"] == 0
    assert result.drive["loomL"] == 0
    assert result.drive["growthL"] == 0


def test_closer_hand_intercepts_one_east_west_pair():
    notes = [
        Note(t=1.0, button=7, type="tap", sensor="A7"),
        Note(t=1.0, button=1, type="tap", sensor="A1"),
    ]
    enc = NoteEncoder(mock=True)
    result = enc.encode(
        notes,
        0.5,
        look_ahead_s=1.0,
        dt=0.004,
        hand_l=sensor_xy("A8"),
        hand_r=sensor_xy("A3"),
    )
    assert result.target_l == "A7"
    assert result.target_r == "A1"
    left_ew = (result.drive["eastL"] > 0.02, result.drive["westL"] > 0.02)
    assert left_ew != (True, True)
    assert left_ew[0] or left_ew[1]


def test_slide_growth_pulses_current_waypoint():
    notes = [
        Note(
            t=1.0,
            button=5,
            type="slide",
            sensor="A5",
            slide=SlideInfo(
                shape="-",
                end_sensor="A7",
                path=("A5", "A6", "A7"),
                end_t=2.0,
            ),
        )
    ]
    enc = NoteEncoder(mock=True)
    on_node = enc.encode(
        notes,
        1.2,
        look_ahead_s=1.0,
        dt=0.004,
        slide_next=[1],
        hand_l=sensor_xy("A6"),
        hand_r=sensor_xy("A3"),
    )
    assert on_node.drive["growthL"] > 0.05
    off_node = enc.encode(
        notes,
        1.2,
        look_ahead_s=1.0,
        dt=0.004,
        slide_next=[1],
        hand_l=sensor_xy("A5"),
        hand_r=sensor_xy("A3"),
    )
    assert off_node.drive["growthL"] < 0.05


def test_real_inject_has_hand_laterality():
    brain = _StubBrain()
    enc = NoteEncoder(brain, mock=False)
    result = enc.encode(
        [Note(t=1.0, button=1, type="tap", sensor="A1")],
        0.5,
        look_ahead_s=1.0,
        dt=0.004,
    )
    left_chase = set(brain.cells(list(CHASE_TYPES), "L"))
    right_chase = set(brain.cells(list(CHASE_TYPES), "R"))
    injected = [set(idx) for idx, amount in result.inject if amount > 0]
    assert any(right_chase & ids for ids in injected)
    assert not any(left_chase & ids for ids in injected)


def test_slide_in_progress_not_stolen_by_tap():
    slide = Note(
        t=1.0,
        button=5,
        type="slide",
        sensor="A5",
        slide=SlideInfo(
            shape="-",
            end_sensor="A7",
            path=("A5", "A6", "A7"),
            end_t=2.0,
            wait_t=1.0,
        ),
    )
    tap = Note(t=1.2, button=1, type="tap", sensor="A1")
    enc = NoteEncoder(mock=True)
    enc.encode(
        [slide],
        1.2,
        look_ahead_s=1.0,
        dt=0.004,
        slide_next=[1],
        hand_l=sensor_xy("A6"),
        hand_r=sensor_xy("A3"),
    )
    result = enc.encode(
        [slide, tap],
        1.2,
        look_ahead_s=1.0,
        dt=0.004,
        slide_next=[1, 0],
        hand_l=sensor_xy("A6"),
        hand_r=sensor_xy("A3"),
    )
    assert result.target_l == "A6"
    assert result.slide_l is not None
    assert result.target_r == "A1"


def test_on_pad_tth_zero_still_grows():
    notes = [Note(t=1.0, button=5, type="tap", sensor="A5")]
    enc = NoteEncoder(mock=True)
    result = enc.encode(
        notes,
        1.0,
        look_ahead_s=1.0,
        dt=0.004,
        hand_l=sensor_xy("A5"),
        hand_r=sensor_xy("A3"),
    )
    assert result.drive["growthL"] >= 0.05


def test_matched_notes_are_skipped():
    notes = [Note(t=1.0, button=6, type="tap", sensor="A6")]
    enc = NoteEncoder(mock=True)
    result = enc.encode(
        notes,
        0.5,
        look_ahead_s=1.0,
        dt=0.004,
        matched=[True],
        hand_l=sensor_xy("A6"),
        hand_r=sensor_xy("A3"),
    )
    assert result.target_l is None
    assert result.drive["growthL"] == 0.0
