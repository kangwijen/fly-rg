"""Tests for Simai parsing and chart JSON loading."""

from __future__ import annotations

from pathlib import Path

from fly_rg.chart import list_difficulties, parse_simai
from fly_rg.schema import Chart
from fly_rg.slides import expand_slide, expand_wifi

DEMO = Path(__file__).resolve().parents[1] / "charts" / "demo"
TERATERA = DEMO / "てらてら" / "maidata.txt"
WORLDS_END = DEMO / "World_s end loneliness" / "maidata.txt"


def _assert_chart_roundtrip(chart: Chart) -> None:
    restored = Chart.from_dict(chart.to_dict())
    assert len(restored.notes) == len(chart.notes)
    for orig, back in zip(chart.notes, restored.notes):
        assert back.type == orig.type
        assert back.sensor == orig.sensor
        assert back.button == orig.button
        if orig.slide is not None:
            assert back.slide is not None
            assert back.slide.path == orig.slide.path
        else:
            assert back.slide is None


def test_demo_packs_parse_and_roundtrip():
    maidata_files = sorted(DEMO.glob("*/maidata.txt"))
    assert maidata_files, f"no demo packs under {DEMO}"
    for path in maidata_files:
        text = path.read_text(encoding="utf-8")
        for entry in list_difficulties(text):
            difficulty = int(entry["difficulty"])
            chart = parse_simai(text, difficulty=difficulty)
            assert len(chart.notes) > 0
            _assert_chart_roundtrip(chart)


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
    assert abs(chart.notes[1].t - chart.notes[0].t - 1.875 / 120) < 1e-9
    assert not chart.notes[0].is_each


def test_bare_hold_length_zero():
    chart = parse_simai("&title=x\n&inote_1=\n(120){4}1h,\nE\n")
    assert len(chart.notes) == 1
    hold = chart.notes[0]
    assert hold.type == "hold"
    assert hold.end == hold.t


def test_hold_then_slide():
    chart = parse_simai("&title=x\n&inote_1=\n(120){4}1h-5[8:1],\nE\n")
    holds = [n for n in chart.notes if n.type == "hold"]
    slides = [n for n in chart.notes if n.type == "slide"]
    assert len(holds) == 1
    assert len(slides) == 1
    hold = holds[0]
    slide = slides[0]
    assert abs(hold.end - hold.t - 0.5) < 1e-9
    assert slide.slide is not None
    assert slide.slide.path[0] == "A1"
    assert slide.slide.path[-1] == "A5"


def test_chained_slide_duration_sum():
    chart = parse_simai("&title=x\n&inote_1=\n(120){4}1-3[8:1]-5[8:1],\nE\n")
    slides = [n for n in chart.notes if n.type == "slide"]
    assert len(slides) == 1
    slide = slides[0].slide
    assert slide is not None
    assert slide.shape == "-"
    assert abs(slide.end_t - slide.wait_t - 0.5) < 1e-9


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


def test_teratera_parses_many_notes():
    assert TERATERA.is_file()
    text = TERATERA.read_text(encoding="utf-8")
    levels = list_difficulties(text)
    difficulty = min(int(e["difficulty"]) for e in levels)
    chart = parse_simai(text, difficulty=difficulty)
    assert len(chart.notes) > 100
    types = {n.type for n in chart.notes}
    assert "tap" in types
    assert types & {"hold", "slide", "touch", "touch_hold"}


def test_worlds_end_gt5_path():
    assert WORLDS_END.is_file()
    text = WORLDS_END.read_text(encoding="utf-8")
    levels = {int(e["difficulty"]) for e in list_difficulties(text)}
    if 4 in levels:
        difficulty = 4
    elif 5 in levels:
        difficulty = 5
    else:
        difficulty = max(levels)
    chart = parse_simai(text, difficulty=difficulty)
    assert len(chart.notes) > 0
    candidates = [
        n
        for n in chart.notes
        if n.type == "slide"
        and n.button == 5
        and n.slide is not None
        and (
            n.slide.shape == ">"
            or (n.slide.path and n.slide.path[0] == "A5" and ">" in n.slide.shape)
        )
    ]
    if candidates:
        path = candidates[0].slide.path
        assert path[0] == "A5"
        assert path[1] == "A4"
        assert path[2] == "A3"


def test_teratera_p_direction():
    assert TERATERA.is_file()
    text = TERATERA.read_text(encoding="utf-8")
    chart = None
    for entry in list_difficulties(text):
        candidate = parse_simai(text, difficulty=int(entry["difficulty"]))
        slides = [
            n
            for n in candidate.notes
            if n.type == "slide"
            and n.button == 7
            and n.slide is not None
            and n.slide.shape == "p"
        ]
        if slides:
            chart = candidate
            path = slides[0].slide.path
            break
    assert chart is not None
    assert "B6" in path
    assert "B8" not in path
    assert expand_slide("p", 7, 3) == list(path)
