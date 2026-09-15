"""Basic Simai slide path tables for shapes - > < ^ v V."""

from __future__ import annotations

from fly_rg.sensors import button_to_sensor, format_sensor

SUPPORTED_SHAPES = frozenset({"-", ">", "<", "^", "v", "V"})


def _next_button(button: int, *, clockwise: bool) -> int:
    if clockwise:
        return button % 8 + 1
    return 8 if button == 1 else button - 1


def _a_ring_path(start: int, end: int, *, clockwise: bool) -> list[str]:
    """Walk the A-ring from start to end (inclusive). Full circle if start==end."""
    path = [button_to_sensor(start)]
    cur = start
    if start == end:
        for _ in range(8):
            cur = _next_button(cur, clockwise=clockwise)
            path.append(button_to_sensor(cur))
        return path
    while cur != end:
        cur = _next_button(cur, clockwise=clockwise)
        path.append(button_to_sensor(cur))
    return path


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


def _straight_path(start: int, end: int) -> list[str]:
    """Straight slide through center: A_s, B_s, C, B_e, A_e."""
    return [
        button_to_sensor(start),
        format_sensor("B", start),
        "C",
        format_sensor("B", end),
        button_to_sensor(end),
    ]


def _curve_path(shape: str, start: int, end: int) -> list[str]:
    """Approximate V/^/v with A and B sensors along an arc."""
    if shape == "V":
        clockwise = not _short_clockwise(start, end)
    else:
        clockwise = _short_clockwise(start, end)

    buttons = _arc_buttons(start, end, clockwise=clockwise)
    if len(buttons) == 1:
        return [button_to_sensor(start)]

    if shape == "^":
        # Short arc: A head, B intermediates, A tail.
        path = [button_to_sensor(buttons[0])]
        for b in buttons[1:-1]:
            path.append(format_sensor("B", b))
        path.append(button_to_sensor(buttons[-1]))
        return path

    if shape == "v":
        # Short arc: A along the ring with B insets on intermediates.
        path: list[str] = [button_to_sensor(buttons[0])]
        for b in buttons[1:-1]:
            path.append(button_to_sensor(b))
            path.append(format_sensor("B", b))
        path.append(button_to_sensor(buttons[-1]))
        return path

    # V: longer arc, mostly A with a B approach near the end.
    path = [button_to_sensor(b) for b in buttons[:-1]]
    if len(buttons) >= 2:
        path.append(format_sensor("B", buttons[-2]))
    path.append(button_to_sensor(buttons[-1]))
    return path


def expand_slide(shape: str, start: int, end: int) -> list[str]:
    """Expand a basic slide into an ordered list of sensor ids."""
    if shape not in SUPPORTED_SHAPES:
        raise ValueError(f"unsupported slide shape {shape!r}")
    if not 1 <= start <= 8 or not 1 <= end <= 8:
        raise ValueError(f"slide buttons must be 1..8, got {start}->{end}")

    if shape == "-":
        if start == end:
            raise ValueError("straight slide requires distinct start and end")
        return _straight_path(start, end)
    if shape == ">":
        return _a_ring_path(start, end, clockwise=True)
    if shape == "<":
        return _a_ring_path(start, end, clockwise=False)
    return _curve_path(shape, start, end)


def _build_path_table() -> dict[tuple[str, int, int], tuple[str, ...]]:
    table: dict[tuple[str, int, int], tuple[str, ...]] = {}
    for shape in SUPPORTED_SHAPES:
        for start in range(1, 9):
            for end in range(1, 9):
                if shape == "-" and start == end:
                    continue
                table[(shape, start, end)] = tuple(expand_slide(shape, start, end))
    return table


# Precomputed lookup: (shape, start_button, end_button) -> path sensors.
PATH_TABLE: dict[tuple[str, int, int], tuple[str, ...]] = _build_path_table()


def path_for(shape: str, start: int, end: int) -> list[str]:
    """Return path from the table (same as expand_slide for supported keys)."""
    key = (shape, start, end)
    if key not in PATH_TABLE:
        return expand_slide(shape, start, end)
    return list(PATH_TABLE[key])
