"""Resource snapshot shape and protocol message."""

from __future__ import annotations

import json
import time

from fly_rg.protocol import dumps, resources_message
from fly_rg.resources import ResourceMonitor


def test_sample_has_cpu_and_rss():
    monitor = ResourceMonitor()
    try:
        monitor.sample()
        time.sleep(0.15)
        stats = monitor.sample()
    finally:
        monitor.close()
    assert isinstance(stats["cpu_pct"], float)
    assert 0.0 <= stats["cpu_pct"] <= 100.0
    assert stats["rss_mb"] > 0
    assert stats["sys_cpu_pct"] is None or 0.0 <= stats["sys_cpu_pct"] <= 100.0
    if stats["ram_total_mb"] is not None:
        assert stats["ram_total_mb"] >= stats["ram_used_mb"] >= 0
    if stats["gpu_pct"] is not None:
        assert 0.0 <= stats["gpu_pct"] <= 100.0
    if stats["vram_total_mb"] is not None:
        assert stats["vram_total_mb"] >= (stats["vram_used_mb"] or 0)


def test_resources_message_is_json_and_typed():
    msg = resources_message(
        {
            "cpu_pct": 12.4,
            "sys_cpu_pct": 40.0,
            "rss_mb": 512.2,
            "ram_used_mb": 8000.0,
            "ram_total_mb": 16000.0,
            "gpu_pct": 55.0,
            "vram_used_mb": 2048.0,
            "vram_total_mb": 8192.0,
            "gpu_name": "NVIDIA GeForce RTX 5060",
        }
    )
    assert msg["type"] == "resources"
    assert msg["cpu_pct"] == 12.4
    assert msg["gpu_name"] == "NVIDIA GeForce RTX 5060"
    parsed = json.loads(dumps(msg))
    assert parsed["type"] == "resources"
    assert parsed["vram_total_mb"] == 8192.0


def test_resources_message_strips_control_chars_from_gpu_name():
    msg = resources_message({"gpu_name": "bad\x00name\n"})
    assert msg["gpu_name"] == "badname"
    assert msg["cpu_pct"] == 0.0
    assert msg["gpu_pct"] is None
