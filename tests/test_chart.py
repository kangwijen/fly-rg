"""Tests for Simai subset parsing and chart JSON loading."""

from __future__ import annotations

from pathlib import Path

from fly_rg.chart import load_chart, load_chart_json, parse_simai_subset
from fly_rg.schema import Chart

DEMO = Path(__file__).resolve().parents[1] / "charts" / "demo"


def test_parse_simai_demo_eight_taps():
    text = (DEMO / "maidata.txt").read_text(encoding="utf-8")
    chart = parse_simai_subset(text)
    assert chart.title == "Demo Ring"
    assert chart.artist == "fly-rg"
    assert chart.offset == 0.0
    assert len(chart.notes) == 8
    assert [n.button for n in chart.notes] == list(range(1, 9))
    assert [n.t for n in chart.notes] == [i * 0.5 for i in range(8)]
    assert all(n.type == "tap" for n in chart.notes)


def test_parse_hold_fraction_and_seconds():
    text = """
&title=Holds
&artist=test
&first=1.0
&inote_1=
(120){4}
1h[8:1],2h[#0.5],
E
"""
    chart = parse_simai_subset(text)
    assert chart.offset == 1.0
    assert len(chart.notes) == 2
    assert chart.notes[0].type == "hold"
    assert chart.notes[0].button == 1
    assert chart.notes[0].t == 1.0
    # [8:1] at 120 BPM: (60/120)*(4/8)*1 = 0.25 s
    assert abs(chart.notes[0].end - 1.25) < 1e-9
    assert chart.notes[1].button == 2
    assert abs(chart.notes[1].t - 1.5) < 1e-9
    assert abs(chart.notes[1].end - 2.0) < 1e-9


def test_each_slash_same_time():
    chart = parse_simai_subset("&title=x\n&artist=y\n&inote_1=\n(60){4}\n1/5,\nE\n")
    assert len(chart.notes) == 2
    assert chart.notes[0].t == chart.notes[1].t == 0.0
    assert {n.button for n in chart.notes} == {1, 5}


def test_load_chart_json_matches_demo():
    chart = load_chart_json(DEMO / "chart.json")
    assert isinstance(chart, Chart)
    assert len(chart.notes) == 8
    maidata = load_chart(DEMO / "maidata.txt")
    assert [n.button for n in chart.notes] == [n.button for n in maidata.notes]
    for a, b in zip(chart.notes, maidata.notes):
        assert abs(a.t - b.t) < 1e-9
