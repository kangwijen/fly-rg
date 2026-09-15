"""Simai slide path expanders for all official shapes.

Shapes per https://w.atwiki.jp/simai/pages/1003.html :
  - straight, > < ^ arcs, v through center, V grand-v (mid button),
  p q curves, pp qq grand curves, s z thunder, w wifi (3 tails).
"""

from __future__ import annotations

from fly_rg.sensors import button_to_sensor, format_sensor

# Single-token shapes (V with mid is handled separately as "V").
SUPPORTED_SHAPES = frozenset(
    {"-", ">", "<", "^", "v", "V", "p", "q", "s", "z", "pp", "qq", "w"}
)


def _next_button(button: int, *, clockwise: bool) -> int:
    if clockwise:
        return button % 8 + 1
    return 8 if button == 1 else button - 1


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
    cw = (end - start) % 8
    ccw = (start - end) % 8
    return cw <= ccw


def _a_ring_path(start: int, end: int, *, clockwise: bool) -> list[str]:
    return [button_to_sensor(b) for b in _arc_buttons(start, end, clockwise=clockwise)]


def _straight_path(start: int, end: int) -> list[str]:
    if start == end:
        raise ValueError("straight slide requires distinct start and end")
    return [
        button_to_sensor(start),
        format_sensor("B", start),
        "C",
        format_sensor("B", end),
        button_to_sensor(end),
    ]


def _v_through_center(start: int, end: int) -> list[str]:
    """Lowercase v: start -> center -> end."""
    if start == end:
        return [button_to_sensor(start), "C", button_to_sensor(end)]
    return [
        button_to_sensor(start),
        format_sensor("B", start),
        "C",
        format_sensor("B", end),
        button_to_sensor(end),
    ]


def _grand_v(start: int, mid: int, end: int) -> list[str]:
    """Uppercase V: start -> mid (short) then mid -> end."""
    first = _straight_path(start, mid) if start != mid else [button_to_sensor(start)]
    second = _straight_path(mid, end) if mid != end else [button_to_sensor(mid)]
    # Drop duplicate mid junction.
    return first + second[1:]


def _curve_pq(start: int, end: int, *, clockwise: bool, grand: bool) -> list[str]:
    """p/q and pp/qq: arc around center with B/C insets."""
    buttons = _arc_buttons(start, end, clockwise=clockwise)
    if len(buttons) <= 1:
        return [button_to_sensor(start)]
    path: list[str] = [button_to_sensor(buttons[0])]
    for i, b in enumerate(buttons[1:-1], start=1):
        path.append(button_to_sensor(b))
        if grand or i % 2 == 1:
            path.append(format_sensor("B", b))
        if grand and i == len(buttons) // 2:
            path.append("C")
    path.append(button_to_sensor(buttons[-1]))
    return path


def _thunder(start: int, end: int, *, mirror: bool) -> list[str]:
    """s/z zigzag through offset buttons."""
    if start == end:
        raise ValueError("thunder slide requires distinct start and end")
    # Offset by +2 / -2 depending on mirror, then into end.
    mid1 = _next_button(start, clockwise=not mirror)
    mid1 = _next_button(mid1, clockwise=not mirror)
    mid2 = _next_button(end, clockwise=mirror)
    mid2 = _next_button(mid2, clockwise=mirror)
    path = [button_to_sensor(start), format_sensor("B", start)]
    if mid1 != start:
        path.append(button_to_sensor(mid1))
        path.append(format_sensor("B", mid1))
    path.append("C")
    if mid2 != end:
        path.append(format_sensor("B", mid2))
        path.append(button_to_sensor(mid2))
    path.append(format_sensor("B", end))
    path.append(button_to_sensor(end))
    return path


def _wifi_paths(start: int) -> list[list[str]]:
    """Fan/wifi: three tails toward opposite-ish buttons."""
    # Opposite and neighbors: start+3, +4, +5 (1-indexed mod 8).
    ends = [
        (start + 2 - 1) % 8 + 1,
        (start + 3 - 1) % 8 + 1,
        (start + 4 - 1) % 8 + 1,
    ]
    return [_straight_path(start, e) for e in ends]


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
        return _a_ring_path(start, end, clockwise=True)
    if shape == "<":
        return _a_ring_path(start, end, clockwise=False)
    if shape == "^":
        cw = _short_clockwise(start, end)
        buttons = _arc_buttons(start, end, clockwise=cw)
        path = [button_to_sensor(buttons[0])]
        for b in buttons[1:-1]:
            path.append(format_sensor("B", b))
        path.append(button_to_sensor(buttons[-1]))
        return path
    if shape == "v":
        return _v_through_center(start, end)
    if shape == "V":
        if mid is None:
            # Fallback: long arc if mid omitted (legacy charts).
            cw = not _short_clockwise(start, end)
            return _a_ring_path(start, end, clockwise=cw)
        return _grand_v(start, mid, end)
    if shape == "p":
        return _curve_pq(start, end, clockwise=True, grand=False)
    if shape == "q":
        return _curve_pq(start, end, clockwise=False, grand=False)
    if shape == "pp":
        return _curve_pq(start, end, clockwise=True, grand=True)
    if shape == "qq":
        return _curve_pq(start, end, clockwise=False, grand=True)
    if shape == "s":
        return _thunder(start, end, mirror=False)
    if shape == "z":
        return _thunder(start, end, mirror=True)
    if shape == "w":
        # Caller should use expand_wifi; single path uses middle tail.
        return _wifi_paths(start)[1]
    raise ValueError(f"unsupported slide shape {shape!r}")


def expand_wifi(start: int) -> list[list[str]]:
    if not 1 <= start <= 8:
        raise ValueError(f"wifi start must be 1..8, got {start}")
    return _wifi_paths(start)


def path_for(shape: str, start: int, end: int, *, mid: int | None = None) -> list[str]:
    return expand_slide(shape, start, end, mid=mid)
