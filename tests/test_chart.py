"""Tests for Simai subset parsing and chart JSON loading."""

from __future__ import annotations

from pathlib import Path

from fly_rg.chart import load_chart, load_chart_json, parse_simai_subset
from fly_rg.schema import Chart
from fly_rg.slides import expand_slide

DEMO = Path(__file__).resolve().parents[1] / "charts" / "demo"


def test_parse_simai_demo_notes():
    text = (DEMO / "maidata.txt").read_text(encoding="utf-8")
    chart = parse_simai_subset(text)
    assert chart.title == "Demo Ring"
    assert chart.artist == "fly-rg"
    assert chart.offset == 0.0
    assert len(chart.notes) == 12
    taps = [n for n in chart.notes if n.type == "tap"]
    touches = [n for n in chart.notes if n.type == "touch"]
    slides = [n for n in chart.notes if n.type == "slide"]
    assert len(taps) == 8
    assert len(touches) == 3
    assert len(slides) == 1
    assert [n.sensor for n in touches] == ["A1", "B5", "C"]
    slide = slides[0]
    assert slide.button == 1
    assert slide.slide is not None
    assert slide.slide.path == ("A1", "B1", "C", "B5", "A5")
    assert abs(slide.slide.end_t - 3.75) < 1e-9


def test_parse_touch_and_touch_hold():
    chart = parse_simai_subset(
        "&title=t\n&artist=a\n&inote_1=\n(120){4}\nA1,B2f,C,D5,E3,A1h[8:1],\nE\n"
    )
    sensors = [n.sensor for n in chart.notes]
    types = [n.type for n in chart.notes]
    assert sensors == ["A1", "B2", "C", "D5", "E3", "A1"]
    assert types == ["touch", "touch", "touch", "touch", "touch", "touch_hold"]
    hold = chart.notes[-1]
    assert hold.end is not None
    assert abs(hold.end - 2.75) < 1e-9  # t=2.5 + 0.25


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
    assert chart.notes[0].sensor == "A1"
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


def test_slide_path_straight_1_to_5():
    assert expand_slide("-", 1, 5) == ["A1", "B1", "C", "B5", "A5"]


def test_difficulty_picks_single_inote():
    text = """
&title=x
&artist=y
&inote_2=
(120){4}1,2,
&inote_5=
(120){4}5,6,7,8,
"""
    low = parse_simai_subset(text)
    assert [n.button for n in low.notes] == [1, 2]
    high = parse_simai_subset(text, difficulty=5)
    assert [n.button for n in high.notes] == [5, 6, 7, 8]


def test_load_chart_json_matches_demo():
    chart = load_chart_json(DEMO / "chart.json")
    assert isinstance(chart, Chart)
    assert len(chart.notes) == 12
    maidata = load_chart(DEMO / "maidata.txt")
    assert [n.type for n in chart.notes] == [n.type for n in maidata.notes]
    assert [n.sensor for n in chart.notes] == [n.sensor for n in maidata.notes]
    for a, b in zip(chart.notes, maidata.notes):
        assert abs(a.t - b.t) < 1e-9
