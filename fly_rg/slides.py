"""Simai slide path expanders matching official DX sensor sequences.

Reference: TRG "GUIDE: MAIMAI SLIDE NOTES TOUCH SENSOR USAGE"
and https://w.atwiki.jp/simai/pages/1003.html
"""

from __future__ import annotations

from fly_rg.sensors import button_to_sensor, format_sensor

SUPPORTED_SHAPES = frozenset(
    {"-", ">", "<", "^", "v", "V", "p", "q", "s", "z", "pp", "qq", "w"}
)


def _next_button(button: int, *, clockwise: bool) -> int:
    if clockwise:
        return button % 8 + 1
    return 8 if button == 1 else button - 1


def _wrap_button(button: int, delta: int) -> int:
    return (button - 1 + delta) % 8 + 1


def _cw_dist(start: int, end: int) -> int:
    return (end - start) % 8


def _ring_dist(start: int, end: int) -> int:
    cw = _cw_dist(start, end)
    return min(cw, (8 - cw) % 8)


def _arc_buttons(start: int, end: int, *, clockwise: bool) -> list[int]:
    buttons = [start]
    cur = start
    if start == end:
        for _ in range(8):
            cur = _next_button(cur, clockwise=clockwise)
            buttons.append(cur)
        return buttons
    while cur != end:
        cur = _next_button(cur, clockwise=clockwise)
        buttons.append(cur)
    return buttons


def _short_clockwise(start: int, end: int) -> bool:
    if start == end:
        return True
    return _cw_dist(start, end) <= _cw_dist(end, start)


def _simai_ring_cw(start: int, end: int, glyph: str) -> bool:
    """Ring direction for > < ^ per SimaiSharp DetermineRingType."""
    start_index = start - 1
    end_index = end - 1
    if glyph == ">":
        return (start_index + 2) % 8 < 4
    if glyph == "<":
        gt_cw = (start_index + 2) % 8 < 4
        return not gt_cw
    if glyph == "^":
        difference = end_index - start_index
        if difference >= 0:
            rotation = -1 if difference > 4 else 1
        else:
            rotation = 1 if difference < -4 else -1
        return rotation > 0
    raise ValueError(f"_simai_ring_cw does not support glyph {glyph!r}")


def _a(btn: int) -> str:
    return button_to_sensor(btn)


def _b(btn: int) -> str:
    return format_sensor("B", btn)


def _e(btn: int) -> str:
    return format_sensor("E", btn)


def _straight_path(start: int, end: int) -> list[str]:
    """Straight (-) by chord length."""
    if start == end:
        raise ValueError("straight slide requires distinct start and end")
    d = _ring_dist(start, end)
    if d == 1:
        return [_a(start), _a(end)]
    if d == 2:
        cw = _short_clockwise(start, end)
        mid = _next_button(start, clockwise=cw)
        # Guide: A1, A2/B2, A3 — use B mid as the touch step.
        return [_a(start), _b(mid), _a(end)]
    # Longer chords cross the center: A, B_start, C, B_end, A_end
    return [_a(start), _b(start), "C", _b(end), _a(end)]


def _edge_path(start: int, end: int, *, clockwise: bool) -> list[str]:
    """Edge (< > ^): walk outer A sensors only."""
    return [_a(b) for b in _arc_buttons(start, end, clockwise=clockwise)]


def _v_center_path(start: int, end: int) -> list[str]:
    """Lowercase v: into center then out."""
    if start == end:
        return [_a(start), _b(start), "C", _b(start), _a(start)]
    return [_a(start), _b(start), "C", _b(end), _a(end)]


def _grand_v(start: int, mid: int, end: int) -> list[str]:
    """Uppercase V: start -> mid -> end (reflect / two-leg)."""
    first = _straight_path(start, mid)
    second = _straight_path(mid, end)
    return first + second[1:]


def _inner_loop(start: int, end: int, *, clockwise: bool) -> list[str]:
    """p / q: enter B_start, walk B ring the long/chosen way to B_end, exit A_end.

    Example p2 from guide: A1, B1, B8, B7, B6, B5, B4, B3, B2, A2
    """
    # Prefer the longer B-ring walk when start!=end so it reads as a loop.
    short_cw = _short_clockwise(start, end)
    use_cw = clockwise
    if start != end:
        # p/q choose direction; if that is the short arc, still follow requested dir.
        use_cw = clockwise
        _ = short_cw
    b_buttons = _arc_buttons(start, end, clockwise=use_cw)
    # Full loop when start==end: walk all 8 B then back.
    path = [_a(start), _b(start)]
    for b in b_buttons[1:]:
        path.append(_b(b))
    if start != end:
        # Ensure we don't duplicate B_end before A_end
        if path[-1] != _b(end):
            path.append(_b(end))
        path.append(_a(end))
    else:
        path.append(_a(end))
    return path


def _outer_loop(start: int, end: int, *, clockwise: bool) -> list[str]:
    """pp / qq: wider loop using B, C, A, E.

    Example pp2: A1, B1, C, B8, A7, A8, B1, C, B2, A2 (approx for start->end).
    """
    path = [_a(start), _b(start), "C"]
    # Swing around via E/A on the chosen side, then into end.
    cur = start
    steps = _cw_dist(start, end) if clockwise else _cw_dist(end, start)
    if steps == 0:
        steps = 8
    for _ in range(max(steps - 1, 1)):
        cur = _next_button(cur, clockwise=clockwise)
        path.append(_e(cur))
        path.append(_a(cur))
    path.append(_b(end))
    path.append(_a(end))
    return path


def _thunder(start: int, end: int, *, mirror: bool) -> list[str]:
    """s / z zigzag. Example z 1->5: A1, B8, B7, C, B3, B4, A5."""
    if start == end:
        raise ValueError("thunder slide requires distinct start and end")
    if mirror:
        return [
            _a(start),
            _b(_wrap_button(start, -1)),
            _b(_wrap_button(start, -2)),
            "C",
            _b(_wrap_button(end, -2)),
            _b(_wrap_button(end, -1)),
            _a(end),
        ]
    return [
        _a(start),
        _b(_wrap_button(start, 1)),
        _b(_wrap_button(start, 2)),
        "C",
        _b(_wrap_button(end, 2)),
        _b(_wrap_button(end, 1)),
        _a(end),
    ]


def _wifi_paths(start: int) -> list[list[str]]:
    """Fan/wifi (w): three tails L / C / R from the head button."""
    end_l = _wrap_button(start, -3)
    end_c = _wrap_button(start, 4)
    end_r = _wrap_button(start, 3)

    left = [
        _a(start),
        _b(_wrap_button(start, -1)),
        _b(_wrap_button(start, -2)),
        _a(end_l),
    ]
    center = [_a(start), _b(start), "C", _b(end_c), _a(end_c)]
    right = [
        _a(start),
        _b(_wrap_button(start, 1)),
        _b(_wrap_button(start, 2)),
        _a(end_r),
    ]
    return [left, center, right]


def expand_slide(
    shape: str,
    start: int,
    end: int,
    *,
    mid: int | None = None,
) -> list[str]:
    """Expand one slide segment into ordered sensor ids."""
    if shape not in SUPPORTED_SHAPES:
        raise ValueError(f"unsupported slide shape {shape!r}")
    if not 1 <= start <= 8 or not 1 <= end <= 8:
        raise ValueError(f"slide buttons must be 1..8, got {start}->{end}")
    if mid is not None and not 1 <= mid <= 8:
        raise ValueError(f"slide mid must be 1..8, got {mid}")

    if shape == "-":
        return _straight_path(start, end)
    if shape == ">":
        return _edge_path(start, end, clockwise=_simai_ring_cw(start, end, ">"))
    if shape == "<":
        return _edge_path(start, end, clockwise=_simai_ring_cw(start, end, "<"))
    if shape == "^":
        return _edge_path(start, end, clockwise=_simai_ring_cw(start, end, "^"))
    if shape == "v":
        return _v_center_path(start, end)
    if shape == "V":
        if mid is None:
            # Legacy fallback: long edge the long way.
            return _edge_path(start, end, clockwise=not _short_clockwise(start, end))
        return _grand_v(start, mid, end)
    if shape == "p":
        return _inner_loop(start, end, clockwise=False)
    if shape == "q":
        return _inner_loop(start, end, clockwise=True)
    if shape == "pp":
        return _outer_loop(start, end, clockwise=False)
    if shape == "qq":
        return _outer_loop(start, end, clockwise=True)
    if shape == "s":
        return _thunder(start, end, mirror=False)
    if shape == "z":
        return _thunder(start, end, mirror=True)
    if shape == "w":
        return _wifi_paths(start)[1]
    raise ValueError(f"unsupported slide shape {shape!r}")


def expand_wifi(start: int) -> list[list[str]]:
    if not 1 <= start <= 8:
        raise ValueError(f"wifi start must be 1..8, got {start}")
    return _wifi_paths(start)


def path_for(shape: str, start: int, end: int, *, mid: int | None = None) -> list[str]:
    return expand_slide(shape, start, end, mid=mid)
