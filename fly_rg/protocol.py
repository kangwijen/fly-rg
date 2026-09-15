"""WebSocket JSON message builders (shared with the web client)."""

from __future__ import annotations

import json
from typing import Any

from fly_rg.schema import Chart


def hello_message(version: int = 1) -> dict[str, Any]:
    return {"type": "hello", "version": version}


def chart_message(chart: Chart) -> dict[str, Any]:
    d = chart.to_dict()
    return {
        "type": "chart",
        "title": d["title"],
        "artist": d["artist"],
        "notes": d["notes"],
    }


def state_message(
    *,
    t: float,
    aim_button: int | None,
    tap: bool,
    tap_button: int | None,
    score: dict[str, Any],
    active: list[dict[str, Any]],
    drive: dict[str, float],
    pose: dict[str, float],
    spikes: list[int] | None = None,
    spike_total: int = 0,
    aim_sensor: str | None = None,
    tap_sensor: str | None = None,
    active_sensors: list[str] | None = None,
    hand_l_sensor: str | None = None,
    hand_r_sensor: str | None = None,
) -> dict[str, Any]:
    # aim_button / tap_button stay ints for A-sensors, else null.
    return {
        "type": "state",
        "t": float(t),
        "aim_button": aim_button,
        "aim_sensor": aim_sensor,
        "tap": bool(tap),
        "tap_button": tap_button,
        "tap_sensor": tap_sensor,
        "hand_l_sensor": hand_l_sensor,
        "hand_r_sensor": hand_r_sensor,
        "score": score,
        "active": active,
        "active_sensors": list(active_sensors or []),
        "drive": {
            "loomL": float(drive.get("loomL", 0.0)),
            "loomR": float(drive.get("loomR", 0.0)),
            "chaseL": float(drive.get("chaseL", 0.0)),
            "chaseR": float(drive.get("chaseR", 0.0)),
            "threatL": float(drive.get("threatL", 0.0)),
            "threatR": float(drive.get("threatR", 0.0)),
        },
        "pose": {
            "aim": float(pose.get("aim", 0.0)),
            "strike": float(pose.get("strike", 0.0)),
            "strike_l": float(pose.get("strike_l", pose.get("strike", 0.0))),
            "strike_r": float(pose.get("strike_r", pose.get("strike", 0.0))),
        },
        "spikes": list(spikes or []),
        "spike_total": int(spike_total),
    }


def brain_layout_message(layout: dict[str, Any]) -> dict[str, Any]:
    """Pass-through helper; layout already includes type=brain_layout."""
    return layout


def hit_message(
    *,
    t: float,
    button: int | None,
    judgment: str,
    sensor: str | None = None,
    timing: str | None = None,
) -> dict[str, Any]:
    return {
        "type": "hit",
        "t": float(t),
        "button": button,
        "sensor": sensor,
        "judgment": judgment,
        "timing": timing,
    }


def end_message(score: dict[str, Any]) -> dict[str, Any]:
    return {"type": "end", "score": score}


def dumps(message: dict[str, Any]) -> str:
    return json.dumps(message, separators=(",", ":"))
