"""Decoder assigns hands from L/R drive, not a hardcoded x-sort."""

from __future__ import annotations

from fly_rg.decoder import ActionDecoder
from fly_rg.schema import Note


def test_both_sides_drive_places_both_hands():
    notes = [
        Note(t=1.0, button=1, type="tap", sensor="A1"),
        Note(t=1.0, button=6, type="tap", sensor="A6"),
    ]
    dec = ActionDecoder(mock=True, seed=1)
    result = dec.decode(
        0.5,
        notes,
        look_ahead_s=1.0,
        drive={
            "loomL": 0.7,
            "loomR": 0.7,
            "chaseL": 0.4,
            "chaseR": 0.4,
        },
    )
    assert result.hand_l_sensor == "A6"
    assert result.hand_r_sensor == "A1"


def test_two_notes_never_share_a_hand():
    notes = [
        Note(t=1.0, button=1, type="tap", sensor="A1"),
        Note(t=1.0, button=6, type="tap", sensor="A6"),
    ]
    dec = ActionDecoder(mock=True, seed=1)
    result = dec.decode(
        0.5,
        notes,
        look_ahead_s=1.0,
        drive={"loomL": 0.8, "chaseL": 0.4},
    )
    assert result.hand_l_sensor == "A6"
    assert result.hand_r_sensor == "A1"
    assert result.hand_l_sensor != result.hand_r_sensor


def test_single_note_uses_one_hand():
    notes = [Note(t=1.0, button=6, type="tap", sensor="A6")]
    dec = ActionDecoder(mock=True, seed=1)
    result = dec.decode(
        0.5,
        notes,
        look_ahead_s=1.0,
        drive={"loomL": 0.8, "chaseL": 0.4},
    )
    assert result.hand_l_sensor == "A6"
    assert result.hand_r_sensor is None


def test_hands_still_assigned_at_note_time():
    notes = [
        Note(t=1.0, button=1, type="tap", sensor="A1"),
        Note(t=1.0, button=6, type="tap", sensor="A6"),
    ]
    dec = ActionDecoder(mock=True, seed=1)
    result = dec.decode(
        1.0,
        notes,
        look_ahead_s=1.0,
        drive={
            "loomL": 0.7,
            "loomR": 0.7,
            "chaseL": 0.4,
            "chaseR": 0.4,
        },
    )
    assert result.hand_l_sensor == "A6"
    assert result.hand_r_sensor == "A1"
