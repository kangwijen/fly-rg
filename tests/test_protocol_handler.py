"""Client message parsing, maidata/note caps, and WS emit backpressure helpers."""

from __future__ import annotations

import pytest

from fly_rg.play import (
    MAX_CHART_NOTES,
    MAX_MAIDATA_BYTES,
    WRITE_BUFFER_SKIP,
    _emit_to_clients,
    _parse_client_message,
    _prepare_loaded_chart,
    _reject_maidata_size,
    _reject_note_count,
    _serve_origins,
)


def test_parse_client_message_rejects_non_dict():
    with pytest.raises((ValueError, TypeError), match="invalid JSON"):
        _parse_client_message("5")
    with pytest.raises((ValueError, TypeError), match="invalid JSON"):
        _parse_client_message("[1,2]")
    with pytest.raises((ValueError, TypeError), match="invalid JSON"):
        _parse_client_message('"x"')
    with pytest.raises(ValueError, match="invalid JSON"):
        _parse_client_message("not json")
    assert _parse_client_message('{"type":"stop"}')["type"] == "stop"


def test_note_count_cap_rejects_huge_list():
    assert _reject_note_count(MAX_CHART_NOTES) is None
    err = _reject_note_count(MAX_CHART_NOTES + 1)
    assert err is not None
    assert "20000" in err


def test_maidata_size_cap():
    assert _reject_maidata_size("ok") is None
    huge = "x" * (MAX_MAIDATA_BYTES + 1)
    err = _reject_maidata_size(huge)
    assert err is not None
    chart, skipped, msg = _prepare_loaded_chart(huge, 1)
    assert chart is None
    assert skipped == 0
    assert msg is not None
    assert msg["type"] == "error"
    assert "256 KiB" in msg["message"]


def test_prepare_loaded_chart_counts_skipped_notes():
    chart, skipped, err = _prepare_loaded_chart(
        "&title=t\n&artist=a\n&inote_1=(120){4}1,ZZ,",
        1,
    )
    assert err is None
    assert chart is not None
    assert len(chart.notes) == 1
    assert skipped == 1


def test_serve_origins_include_ui_and_bind():
    origins = _serve_origins("127.0.0.1", 8765)
    assert origins == [
        None,
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:8765",
    ]


def test_emit_skips_slow_client(monkeypatch):
    sent: list[tuple[list[object], str]] = []

    def fake_broadcast(clients, payload, **_kwargs):
        sent.append((list(clients), payload))

    monkeypatch.setattr("fly_rg.play.broadcast", fake_broadcast)

    class SlowTransport:
        def get_write_buffer_size(self) -> int:
            return WRITE_BUFFER_SKIP

    class FastTransport:
        def get_write_buffer_size(self) -> int:
            return 0

    slow = type("WS", (), {"transport": SlowTransport()})()
    fast = type("WS", (), {"transport": FastTransport()})()
    _emit_to_clients({slow, fast}, "hello")
    assert len(sent) == 1
    assert sent[0][1] == "hello"
    assert fast in sent[0][0]
    assert slow not in sent[0][0]
