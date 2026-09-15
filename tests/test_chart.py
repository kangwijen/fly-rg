"""Tests for Simai parsing and chart JSON loading."""

from __future__ import annotations

from pathlib import Path

from fly_rg.chart import load_chart, load_chart_json, parse_simai, parse_simai_subset
from fly_rg.schema import Chart
from fly_rg.slides import expand_slide, expand_wifi

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
    assert slide.is_star
    # wait 1 beat (0.5s at 120) + [8:1]=0.25 after head at t=3.5
    assert abs(slide.t - 3.5) < 1e-9
    assert abs(slide.slide.wait_t - 4.0) < 1e-9
    assert abs(slide.slide.end_t - 4.25) < 1e-9


def test_parse_touch_and_touch_hold():
    chart = parse_simai(
        "&title=t\n&artist=a\n&inote_1=\n(120){4}\nA1,B2f,C,D5,E3,A1h[8:1],\nE\n"
    )
    sensors = [n.sensor for n in chart.notes]
    types = [n.type for n in chart.notes]
    assert sensors == ["A1", "B2", "C", "D5", "E3", "A1"]
    assert types == ["touch", "touch", "touch", "touch", "touch", "touch_hold"]
    assert chart.notes[1].is_hanabi
    hold = chart.notes[-1]
    assert hold.end is not None
    assert abs(hold.end - 2.75) < 1e-9


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
    chart = parse_simai(text)
    assert chart.offset == 1.0
    assert len(chart.notes) == 2
    assert chart.notes[0].type == "hold"
    assert chart.notes[0].button == 1
    assert chart.notes[0].sensor == "A1"
    assert chart.notes[0].t == 1.0
    assert abs(chart.notes[0].end - 1.25) < 1e-9
    assert chart.notes[1].button == 2
    assert abs(chart.notes[1].t - 1.5) < 1e-9
    assert abs(chart.notes[1].end - 2.0) < 1e-9


def test_break_ex_each_flags():
    chart = parse_simai("&title=x\n&inote_1=\n(120){4}1b/2x/3bx,4hb[8:1],5$,\nE\n")
    assert chart.notes[0].is_break and chart.notes[0].is_each
    assert chart.notes[1].is_ex and chart.notes[1].is_each
    assert chart.notes[2].is_break and chart.notes[2].is_ex
    assert chart.notes[3].type == "hold" and chart.notes[3].is_break
    assert chart.notes[4].is_star and chart.notes[4].head_style == "star"


def test_each_slash_same_time():
    chart = parse_simai("&title=x\n&artist=y\n&inote_1=\n(60){4}\n1/5,\nE\n")
    assert len(chart.notes) == 2
    assert chart.notes[0].t == chart.notes[1].t == 0.0
    assert {n.button for n in chart.notes} == {1, 5}
    assert all(n.is_each for n in chart.notes)


def test_compact_each_taps():
    chart = parse_simai("&title=x\n&inote_1=\n(120){4}12,\nE\n")
    assert len(chart.notes) == 2
    assert {n.button for n in chart.notes} == {1, 2}
    assert all(n.is_each for n in chart.notes)


def test_slide_shapes_and_multi():
    chart = parse_simai(
        "&title=x\n&inote_1=\n(120){4}1-5[8:1],1V35[8:1],1-4[4:1]*-6[8:1],\nE\n"
    )
    slides = [n for n in chart.notes if n.type == "slide"]
    assert len(slides) == 4  # straight, V, and two multi tails
    assert slides[0].slide and slides[0].slide.shape == "-"
    assert slides[1].slide and "V" in slides[1].slide.shape
    assert slides[1].slide.path[0] == "A1"
    assert slides[1].slide.path[-1] == "A5"


def test_wifi_slide():
    paths = expand_wifi(1)
    assert len(paths) == 3
    chart = parse_simai("&title=x\n&inote_1=\n(120){4}1w5[8:1],\nE\n")
    slides = [n for n in chart.notes if n.type == "slide"]
    assert len(slides) == 3


def test_pseudo_each_backtick():
    chart = parse_simai("&title=x\n&inote_1=\n(120){4}1`2,\nE\n")
    assert len(chart.notes) == 2
    assert abs(chart.notes[1].t - chart.notes[0].t - 0.001) < 1e-9
    assert not chart.notes[0].is_each


def test_absolute_step():
    chart = parse_simai("&title=x\n&inote_1=\n(120){#0.5}1,1,\nE\n")
    assert abs(chart.notes[1].t - 0.5) < 1e-9


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
    low = parse_simai(text)
    assert [n.button for n in low.notes] == [1, 2]
    high = parse_simai(text, difficulty=5)
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


def test_teratera_parses_many_notes():
    zpath = Path(__file__).resolve().parents[1] / "charts" / "zip" / "teratera.zip"
    if not zpath.exists():
        return
    import zipfile

    with zipfile.ZipFile(zpath) as zf:
        name = next(n for n in zf.namelist() if n.lower().endswith("maidata.txt"))
        text = zf.read(name).decode("utf-8")
    chart = parse_simai(text, difficulty=2)
    assert len(chart.notes) > 100
    types = {n.type for n in chart.notes}
    assert "tap" in types
    # Basic chart should include holds or slides or touches in real packs
    assert types & {"hold", "slide", "touch", "touch_hold"}
