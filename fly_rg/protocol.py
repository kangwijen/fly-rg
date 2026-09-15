"""WebSocket JSON message builders (shared with the web client)."""

from __future__ import annotations

import json
from typing import Any

from fly_rg.schema import Chart


def hello_message(version: int = 1) -> dict[str, Any]:
    return {"type": "hello", "version": version}


def chart_message(
    chart: Chart,
    *,
    active: list | None = None,
    active_sensors: list | None = None,
) -> dict[str, Any]:
    d = chart.to_dict()
    msg: dict[str, Any] = {
        "type": "chart",
        "title": d["title"],
        "artist": d["artist"],
        "notes": d["notes"],
    }
    if active is not None:
        msg["active"] = active
    if active_sensors is not None:
        msg["active_sensors"] = active_sensors
    return msg


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
    hand_l: list[float] | tuple[float, float] | None = None,
    hand_r: list[float] | tuple[float, float] | None = None,
) -> dict[str, Any]:
    hl = [0.0, 0.0] if hand_l is None else [float(hand_l[0]), float(hand_l[1])]
    hr = [0.0, 0.0] if hand_r is None else [float(hand_r[0]), float(hand_r[1])]
    return {
        "type": "state",
        "t": float(t),
        "aim_button": aim_button,
        "aim_sensor": aim_sensor,
        "tap": bool(tap),
        "tap_button": tap_button,
        "tap_sensor": tap_sensor,
        "hand_l": hl,
        "hand_r": hr,
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
            "omega_l": float(pose.get("omega_l", 0.0)),
            "omega_r": float(pose.get("omega_r", 0.0)),
            "reach_l": float(pose.get("reach_l", 0.0)),
            "reach_r": float(pose.get("reach_r", 0.0)),
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


def resources_message(stats: dict[str, Any]) -> dict[str, Any]:
    def _num(key: str) -> float | None:
        value = stats.get(key)
        if value is None:
            return None
        return float(value)

    name = stats.get("gpu_name")
    gpu_name = None
    if isinstance(name, str):
        cleaned = "".join(ch for ch in name if ch.isprintable()).strip()
        gpu_name = cleaned[:64] if cleaned else None
    return {
        "type": "resources",
        "cpu_pct": float(stats.get("cpu_pct") or 0.0),
        "sys_cpu_pct": _num("sys_cpu_pct"),
        "rss_mb": float(stats.get("rss_mb") or 0.0),
        "ram_used_mb": _num("ram_used_mb"),
        "ram_total_mb": _num("ram_total_mb"),
        "gpu_pct": _num("gpu_pct"),
        "vram_used_mb": _num("vram_used_mb"),
        "vram_total_mb": _num("vram_total_mb"),
        "gpu_name": gpu_name,
    }


def dumps(message: dict[str, Any]) -> str:
    return json.dumps(message, separators=(",", ":"))
