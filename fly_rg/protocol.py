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
) -> dict[str, Any]:
    return {
        "type": "state",
        "t": float(t),
        "aim_button": aim_button,
        "tap": bool(tap),
        "tap_button": tap_button,
        "score": score,
        "active": active,
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
        },
    }


def hit_message(*, t: float, button: int, judgment: str) -> dict[str, Any]:
    return {
        "type": "hit",
        "t": float(t),
        "button": int(button),
        "judgment": judgment,
    }


def end_message(score: dict[str, Any]) -> dict[str, Any]:
    return {"type": "end", "score": score}


def dumps(message: dict[str, Any]) -> str:
    return json.dumps(message, separators=(",", ":"))
