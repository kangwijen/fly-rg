"""Encoder chase drives every approaching side, not only the nearest note."""

from __future__ import annotations

from fly_rg.encoder import NoteEncoder
from fly_rg.schema import Note
from fly_rg.sensors import sensor_xy


def test_simultaneous_left_right_notes_drive_both_chase():
    notes = [
        Note(t=1.0, button=1, type="tap", sensor="A1"),
        Note(t=1.0, button=6, type="tap", sensor="A6"),
    ]
    enc = NoteEncoder(mock=True)
    result = enc.encode(notes, 0.5, look_ahead_s=1.0, dt=0.004)
    assert result.drive["chaseL"] > 0
    assert result.drive["chaseR"] > 0


def test_both_blobs_contribute_cw_and_ccw():
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
        hand_r=sensor_xy("A4"),
    )
    assert result.drive["cwL"] > 0
    assert result.drive["ccwL"] > 0
