"""Full Simai / maidata chart parser.

Implements the official notation from https://w.atwiki.jp/simai/pages/1003.html
and MajSimai feature coverage (taps/holds/touches/slides with break/ex/mine/
hanabi/star/each, duration forms, chained & multi slides, wifi, absolute
beat steps).
"""

from __future__ import annotations

import json
import re
import warnings
from pathlib import Path

from fly_rg.schema import Chart, HeadStyle, Note, SlideInfo
from fly_rg.sensors import button_to_sensor, format_sensor
from fly_rg.slides import expand_slide, expand_wifi

_PSEUDO_HOLD = 1280  # short-form hold length divider (official fan book)
_PSEUDO_EACH_DT = 0.001


def load_chart_json(path: str | Path) -> Chart:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return Chart.from_dict(data)


def list_difficulties(text: str) -> list[dict[str, str | int]]:
    levels: dict[int, dict[str, str | int]] = {}
    for raw in text.splitlines():
        line = raw.split("||", 1)[0].strip()
        lv = re.match(r"^&lv_(\d+)\s*=\s*(.*)$", line, re.IGNORECASE)
        if lv:
            n = int(lv.group(1))
            levels.setdefault(n, {"difficulty": n, "level": lv.group(2).strip()})
            continue
        inn = re.match(r"^&inote_(\d+)\s*=", line, re.IGNORECASE)
        if inn:
            n = int(inn.group(1))
            levels.setdefault(n, {"difficulty": n, "level": ""})
    return [levels[k] for k in sorted(levels)]


def load_chart(path: str | Path, difficulty: int | None = None) -> Chart:
    p = Path(path)
    if p.suffix.lower() == ".json":
        return load_chart_json(p)
    return parse_simai(p.read_text(encoding="utf-8"), difficulty=difficulty)


def parse_simai_subset(text: str, difficulty: int | None = None) -> Chart:
    """Backward-compatible alias for parse_simai."""
    return parse_simai(text, difficulty=difficulty)


def parse_simai(text: str, difficulty: int | None = None) -> Chart:
    title = ""
    artist = ""
    offset = 0.0

    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.split("||", 1)[0].strip()
        if not line:
            continue
        lines.append(line)

    inotes: dict[int, str] = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("&"):
            key_match = re.match(
                r"^&(title|artist|first)\s*=\s*(.*)$", line, re.IGNORECASE
            )
            if key_match:
                key = key_match.group(1).lower()
                val = key_match.group(2).strip()
                if key == "title":
                    title = val
                elif key == "artist":
                    artist = val
                elif key == "first":
                    offset = float(val) if val else 0.0
                i += 1
                continue
            inote_match = re.match(r"^&inote_(\d+)\s*=\s*(.*)$", line, re.IGNORECASE)
            if inote_match:
                level = int(inote_match.group(1))
                chunk = inote_match.group(2)
                i += 1
                while i < len(lines) and not lines[i].startswith("&"):
                    chunk += lines[i]
                    i += 1
                inotes[level] = chunk.rstrip("E").rstrip()
                continue
        i += 1

    if inotes:
        if difficulty is not None:
            if difficulty not in inotes:
                raise ValueError(
                    f"no &inote_{difficulty}= in maidata (have {sorted(inotes)})"
                )
            chart_body = inotes[difficulty]
        else:
            chart_body = inotes[min(inotes)]
    else:
        chart_body = "".join(ln for ln in lines if not ln.startswith("&")).rstrip("E")

    notes = _parse_note_stream(chart_body, offset)
    return Chart(title=title, artist=artist, offset=offset, notes=notes)


def _parse_note_stream(body: str, offset: float) -> list[Note]:
    bpm = 120.0
    divisor = 4.0
    absolute_step: float | None = None
    t = float(offset)
    notes: list[Note] = []
    pos = 0
    body = re.sub(r"\s+", "", body)

    def step_seconds() -> float:
        if absolute_step is not None:
            return absolute_step
        if bpm <= 0 or divisor <= 0:
            return 0.0
        return 240.0 / bpm / divisor

    def beat_seconds() -> float:
        if bpm <= 0:
            return 0.5
        return 60.0 / bpm

    while pos < len(body):
        ch = body[pos]
        if ch == ",":
            t += step_seconds()
            pos += 1
            continue
        if ch == "`":
            t += _PSEUDO_EACH_DT
            pos += 1
            continue
        if ch == "/":
            pos += 1
            continue
        if ch in "Ee":
            # Bare E ends chart; E1..E8 / Eh / Ef are touches.
            nxt = body[pos + 1] if pos + 1 < len(body) else ""
            if not (nxt.isdigit() or nxt.lower() in "hfxbm"):
                break

        if ch == "(":
            end = body.find(")", pos)
            if end < 0:
                raise ValueError("unclosed BPM (")
            bpm = float(body[pos + 1 : end] or bpm)
            pos = end + 1
            continue

        if ch == "{":
            end = body.find("}", pos)
            if end < 0:
                raise ValueError("unclosed divisor {")
            inner = body[pos + 1 : end]
            if inner.startswith("#"):
                absolute_step = float(inner[1:])
                divisor = 4.0
            else:
                absolute_step = None
                divisor = float(inner or 4)
                if divisor <= 0:
                    raise ValueError(f"invalid divisor {{{inner}}}")
            pos = end + 1
            continue

        # Note group until , / ` or E terminator.
        group_end = pos
        while group_end < len(body) and body[group_end] not in ",/`":
            if body[group_end] in "Ee":
                nxt = body[group_end + 1] if group_end + 1 < len(body) else ""
                if not (nxt.isdigit() or nxt.lower() in "hfxbm"):
                    break
            group_end += 1
        group = body[pos:group_end]
        if not group:
            pos += 1
            continue

        # Split EACH parts by / (already stripped of separators at stream level
        # when we only take until /). Here group has no / because we stop at /.
        # Compact EACH of bare taps: "12" "135" etc.
        parts = _split_compact_taps(group) if _is_compact_tap_run(group) else [group]
        is_each = len(parts) > 1
        # Also EACH if previous leftover used / — handled by calling this once
        # per slash-separated chunk; mark each when sibling chunks exist at
        # same time by scanning nearby. Simpler: track simultaneous bucket.
        bucket: list[Note] = []
        for part in parts:
            bucket.extend(
                _parse_note_token(part, t, bpm=bpm, beat_seconds=beat_seconds)
            )
        # Collect remaining / siblings at same time.
        while pos < len(body) and group_end < len(body) and body[group_end] == "/":
            pos = group_end + 1
            group_end = pos
            while group_end < len(body) and body[group_end] not in ",/`":
                if body[group_end] in "Ee":
                    nxt = body[group_end + 1] if group_end + 1 < len(body) else ""
                    if not (nxt.isdigit() or nxt.lower() in "hfxbm"):
                        break
                group_end += 1
            group = body[pos:group_end]
            if not group:
                break
            parts = _split_compact_taps(group) if _is_compact_tap_run(group) else [group]
            for part in parts:
                bucket.extend(
                    _parse_note_token(part, t, bpm=bpm, beat_seconds=beat_seconds)
                )
            is_each = True

        if len(bucket) > 1:
            is_each = True
        for n in bucket:
            if is_each:
                object.__setattr__(n, "is_each", True)
            notes.append(n)

        pos = group_end

    notes.sort(key=lambda n: (n.t, n.sensor, n.button or 0, n.type))
    return notes


def _is_compact_tap_run(group: str) -> bool:
    """True for runs like 12 / 135 of plain non-break taps only."""
    return bool(re.fullmatch(r"[1-8]{2,}", group))


def _split_compact_taps(group: str) -> list[str]:
    return list(group)


def _parse_duration(spec: str, *, bpm: float) -> float:
    """Parse [..] duration bodies into seconds."""
    spec = spec.strip()
    if not spec:
        return (60.0 / max(bpm, 1e-9)) * (4.0 / _PSEUDO_HOLD)

    # [time##...] absolute wait handled by caller for slides; here duration only.
    if "##" in spec:
        # Should not be used for hold length alone; treat right side as length.
        right = spec.split("##", 1)[1]
        return _parse_duration(right, bpm=bpm)

    # [bpm#division:beats] or [bpm#seconds]
    if "#" in spec and not spec.startswith("#"):
        left, right = spec.split("#", 1)
        local_bpm = float(left)
        if ":" in right:
            n_s, m_s = right.split(":", 1)
            return (60.0 / local_bpm) * (4.0 / float(n_s)) * float(m_s)
        return float(right)

    # [#seconds]
    if spec.startswith("#"):
        return float(spec[1:])

    # [division:beats]
    if ":" in spec:
        n_s, m_s = spec.split(":", 1)
        return (60.0 / max(bpm, 1e-9)) * (4.0 / float(n_s)) * float(m_s)

    raise ValueError(f"bad duration [{spec}]")


def _parse_slide_timing(
    spec: str, *, bpm: float, note_t: float, beat_seconds: float
) -> tuple[float, float]:
    """Return (wait_t, end_t) from a slide duration bracket."""
    spec = spec.strip()
    default_wait = note_t + beat_seconds

    if "##" in spec:
        left, right = spec.split("##", 1)
        wait = note_t + float(left)
        dur = _parse_duration(right, bpm=bpm)
        return wait, wait + dur

    if "#" in spec and not spec.startswith("#"):
        # [bpm#...] : wait is one beat at that bpm, length from right
        left, right = spec.split("#", 1)
        local_bpm = float(left)
        wait = note_t + (60.0 / local_bpm)
        if ":" in right:
            n_s, m_s = right.split(":", 1)
            dur = (60.0 / local_bpm) * (4.0 / float(n_s)) * float(m_s)
        else:
            dur = float(right)
        return wait, wait + dur

    dur = _parse_duration(spec, bpm=bpm)
    return default_wait, default_wait + dur


_FLAG_CHARS = set("bxm$@?!")  # not h (hold) or f (hanabi — touch-only)


def _take_flags(s: str, pos: int) -> tuple[set[str], int]:
    flags: set[str] = set()
    while pos < len(s) and s[pos].lower() in _FLAG_CHARS:
        ch = s[pos]
        if ch == "$" and pos + 1 < len(s) and s[pos + 1] == "$":
            flags.add("$$")
            pos += 2
            continue
        flags.add(ch.lower() if ch not in "$@?!" else ch)
        pos += 1
    return flags, pos


def _take_touch_flags(s: str, pos: int) -> tuple[set[str], int]:
    """Flags for touches: b x m f $ @ ? ! (h is hold marker, not a flag)."""
    flags: set[str] = set()
    while pos < len(s) and s[pos].lower() in "bxmf$@?!":
        ch = s[pos]
        if ch == "$" and pos + 1 < len(s) and s[pos + 1] == "$":
            flags.add("$$")
            pos += 2
            continue
        flags.add(ch.lower() if ch not in "$@?!" else ch)
        pos += 1
    return flags, pos


def _flags_to_style(flags: set[str]) -> tuple[bool, bool, bool, bool, bool, HeadStyle]:
    is_break = "b" in flags
    is_ex = "x" in flags
    is_mine = "m" in flags
    is_hanabi = "f" in flags
    is_star = "$" in flags or "$$" in flags
    head: HeadStyle = "normal"
    if "@" in flags:
        head = "tap"
    elif "?" in flags:
        head = "fade"
    elif "!" in flags:
        head = "sudden"
    elif is_star or "$$" in flags:
        head = "star"
    return is_break, is_ex, is_mine, is_hanabi, is_star, head


def _parse_note_token(
    token: str,
    t: float,
    *,
    bpm: float,
    beat_seconds,
) -> list[Note]:
    if not token:
        return []
    try:
        return _parse_note_token_inner(token, t, bpm=bpm, beat_seconds=beat_seconds)
    except Exception as exc:  # noqa: BLE001 — keep chart loading resilient
        warnings.warn(f"skipping note {token!r}: {exc}", stacklevel=2)
        return []


def _parse_note_token_inner(
    token: str,
    t: float,
    *,
    bpm: float,
    beat_seconds,
) -> list[Note]:
    # Touch: [A-E][1-8]? flags? h? [duration]?
    touch_m = re.match(r"^([A-Ea-e])([1-8])?", token)
    if touch_m and not token[0].isdigit():
        area = touch_m.group(1).upper()
        idx = touch_m.group(2)
        sensor = "C" if area == "C" else format_sensor(area, int(idx or "0"))
        if area != "C" and not idx:
            raise ValueError(f"touch {area} requires index")
        pos = touch_m.end()
        flags, pos = _take_touch_flags(token, pos)
        is_hold = False
        if pos < len(token) and token[pos].lower() == "h":
            is_hold = True
            pos += 1
            more, pos = _take_touch_flags(token, pos)
            flags |= more
        more, pos = _take_touch_flags(token, pos)
        flags |= more
        dur = None
        if pos < len(token) and token[pos] == "[":
            close = token.find("]", pos)
            if close < 0:
                raise ValueError("unclosed duration")
            dur = _parse_duration(token[pos + 1 : close], bpm=bpm)
            pos = close + 1
            more, pos = _take_touch_flags(token, pos)
            flags |= more
        elif is_hold:
            dur = _parse_duration("", bpm=bpm)

        br, ex, mine, hanabi, star, head = _flags_to_style(flags)
        if is_hold or dur is not None:
            return [
                Note(
                    t=t,
                    type="touch_hold",
                    sensor=sensor,
                    end=t + (dur or 0.0),
                    is_break=br,
                    is_ex=ex,
                    is_mine=mine,
                    is_hanabi=hanabi or "f" in flags,
                    is_star=star,
                    head_style=head,
                )
            ]
        return [
            Note(
                t=t,
                type="touch",
                sensor=sensor,
                is_break=br,
                is_ex=ex,
                is_mine=mine,
                is_hanabi=hanabi or "f" in flags,
                is_star=star,
                head_style=head,
            )
        ]

    if not token[0].isdigit():
        raise ValueError(f"expected button note, got {token!r}")

    button = int(token[0])
    pos = 1
    flags, pos = _take_flags(token, pos)

    # Hold: h ...
    if pos < len(token) and token[pos].lower() == "h":
        pos += 1
        more, pos = _take_flags(token, pos)
        flags |= more
        dur = _parse_duration("", bpm=bpm)
        if pos < len(token) and token[pos] == "[":
            close = token.find("]", pos)
            if close < 0:
                raise ValueError("unclosed hold duration")
            dur = _parse_duration(token[pos + 1 : close], bpm=bpm)
            pos = close + 1
            more, pos = _take_flags(token, pos)
            flags |= more
        br, ex, mine, hanabi, star, head = _flags_to_style(flags)
        return [
            Note(
                t=t,
                button=button,
                type="hold",
                sensor=button_to_sensor(button),
                end=t + dur,
                is_break=br,
                is_ex=ex,
                is_mine=mine,
                is_hanabi=hanabi,
                is_star=star,
                head_style=head,
            )
        ]

    # Slide if shape follows (or * chain / @?! already in flags)
    if pos < len(token) and (
        token[pos] in "-><^vVpPqQsSzZw*" or token[pos] in "@?!"
    ):
        return _parse_slides(
            button, token, pos, t, flags, bpm=bpm, beat_seconds=beat_seconds
        )

    # Plain tap (possibly with flags already taken)
    br, ex, mine, hanabi, star, head = _flags_to_style(flags)
    if star and head == "normal":
        head = "star"
    return [
        Note(
            t=t,
            button=button,
            type="tap",
            sensor=button_to_sensor(button),
            is_break=br,
            is_ex=ex,
            is_mine=mine,
            is_hanabi=hanabi,
            is_star=star,
            head_style=head,
        )
    ]


_SHAPE_RE = re.compile(r"(pp|qq|w|[-><\^vVpPqQsSzZ])")


def _parse_slides(
    start_button: int,
    token: str,
    pos: int,
    t: float,
    head_flags: set[str],
    *,
    bpm: float,
    beat_seconds,
) -> list[Note]:
    """Parse one or more slide tracks from a shared head button."""
    # Head modifiers may still be ahead: @ ? !
    more, pos = _take_flags(token, pos)
    flags = set(head_flags) | more
    br, ex, mine, hanabi, star, head = _flags_to_style(flags)
    if head == "normal":
        head = "star"
        star = True
    if "@" in flags:
        head = "tap"
        star = False
    elif "?" in flags:
        head = "fade"
    elif "!" in flags:
        head = "sudden"

    tracks: list[list[tuple[str, int | None, int, str | None]]] = []
    # Each track: list of (shape, mid, end, duration_spec|None)

    def parse_one_track(cur_start: int, p: int) -> tuple[
        list[tuple[str, int | None, int, str | None]], int
    ]:
        segs: list[tuple[str, int | None, int, str | None]] = []
        start = cur_start
        while p < len(token):
            if token[p] == "*":
                break
            sm = _SHAPE_RE.match(token, p)
            if not sm:
                break
            shape = sm.group(1)
            # Normalize case for p/q/s/z; keep V vs v.
            if shape in "pPqQsSzZw":
                shape = shape.lower() if shape not in "V" else shape
            if shape == "PP":
                shape = "pp"
            if shape == "QQ":
                shape = "qq"
            if len(shape) == 1 and shape in "pqszw":
                pass
            elif shape in ("pp", "qq"):
                pass
            elif shape == "V":
                pass
            elif shape == "v":
                pass
            else:
                shape = shape  # - > < ^
            p = sm.end()

            mid: int | None = None
            if shape == "V":
                if p >= len(token) or not token[p].isdigit():
                    raise ValueError("V slide needs mid and end buttons")
                mid = int(token[p])
                p += 1
                if p >= len(token) or not token[p].isdigit():
                    raise ValueError("V slide needs end button")
                end_b = int(token[p])
                p += 1
            elif shape == "w":
                # wifi: end implied; optional digit ignored
                end_b = (start + 3 - 1) % 8 + 1
                if p < len(token) and token[p].isdigit():
                    end_b = int(token[p])
                    p += 1
            else:
                if p >= len(token) or not token[p].isdigit():
                    raise ValueError(f"slide {shape} needs end button")
                end_b = int(token[p])
                p += 1

            dur_spec: str | None = None
            if p < len(token) and token[p] == "[":
                close = token.find("]", p)
                if close < 0:
                    raise ValueError("unclosed slide duration")
                dur_spec = token[p + 1 : close]
                p = close + 1

            # trailing break/mine after ]
            trail, p = _take_flags(token, p)
            if "b" in trail:
                flags.add("b")
            if "m" in trail:
                flags.add("m")
            if "x" in trail:
                flags.add("x")

            segs.append((shape, mid, end_b, dur_spec))
            start = end_b
            # Continue chain if another shape follows
            if p < len(token) and _SHAPE_RE.match(token, p):
                continue
            break
        return segs, p

    # First track
    segs, pos = parse_one_track(start_button, pos)
    if not segs:
        raise ValueError(f"empty slide in {token!r}")
    tracks.append(segs)

    while pos < len(token) and token[pos] == "*":
        pos += 1
        segs, pos = parse_one_track(start_button, pos)
        if segs:
            tracks.append(segs)

    br, ex, mine, hanabi, star, head = _flags_to_style(flags)
    if head == "normal":
        head = "star"
        star = True
    if "@" in flags:
        head = "tap"
        star = False

    out: list[Note] = []
    for segs in tracks:
        # Resolve durations: if only last has duration, apply to whole chain.
        if all(s[3] is None for s in segs[:-1]) and segs[-1][3] is not None:
            wait_t, end_t = _parse_slide_timing(
                segs[-1][3] or "4:1",
                bpm=bpm,
                note_t=t,
                beat_seconds=beat_seconds(),
            )
            path: list[str] = []
            shapes: list[str] = []
            cur = start_button
            for shape, mid, end_b, _ in segs:
                shapes.append(shape if mid is None else f"V{mid}")
                if shape == "w":
                    # wifi expands to three notes separately below
                    for wp in expand_wifi(cur):
                        out.append(
                            _slide_note(
                                t,
                                cur,
                                "w",
                                wp,
                                wait_t,
                                end_t,
                                br,
                                ex,
                                mine,
                                star,
                                head,
                            )
                        )
                    path = []
                    break
                seg_path = expand_slide(shape, cur, end_b, mid=mid)
                if path:
                    path.extend(seg_path[1:])
                else:
                    path = seg_path
                cur = end_b
            if path:
                out.append(
                    _slide_note(
                        t,
                        start_button,
                        "".join(shapes),
                        path,
                        wait_t,
                        end_t,
                        br,
                        ex,
                        mine,
                        star,
                        head,
                    )
                )
            continue

        # Per-segment durations (or default last)
        path = []
        shapes = []
        cur = start_button
        total_wait = t + beat_seconds()
        total_end = total_wait
        for shape, mid, end_b, dur_spec in segs:
            shapes.append(shape if mid is None else f"V{mid}")
            if dur_spec is None:
                dur_spec = "8:1"
            wait_t, end_t = _parse_slide_timing(
                dur_spec, bpm=bpm, note_t=t, beat_seconds=beat_seconds()
            )
            # For multi-duration chains, movement is continuous; use first wait
            # and last end.
            if not path:
                total_wait = wait_t
            total_end = end_t
            if shape == "w":
                for wp in expand_wifi(cur):
                    out.append(
                        _slide_note(
                            t,
                            cur,
                            "w",
                            wp,
                            wait_t,
                            end_t,
                            br,
                            ex,
                            mine,
                            star,
                            head,
                        )
                    )
                path = []
                break
            seg_path = expand_slide(shape, cur, end_b, mid=mid)
            if path:
                path.extend(seg_path[1:])
            else:
                path = seg_path
            cur = end_b
        if path:
            out.append(
                _slide_note(
                    t,
                    start_button,
                    "".join(shapes),
                    path,
                    total_wait,
                    total_end,
                    br,
                    ex,
                    mine,
                    star,
                    head,
                )
            )
    return out


def _slide_note(
    t: float,
    button: int,
    shape: str,
    path: list[str],
    wait_t: float,
    end_t: float,
    is_break: bool,
    is_ex: bool,
    is_mine: bool,
    is_star: bool,
    head: HeadStyle,
) -> Note:
    return Note(
        t=t,
        button=button,
        type="slide",
        sensor=path[0] if path else button_to_sensor(button),
        end=end_t,
        slide=SlideInfo(
            shape=shape,
            end_sensor=path[-1] if path else button_to_sensor(button),
            path=tuple(path),
            end_t=end_t,
            wait_t=wait_t,
        ),
        is_break=is_break,
        is_ex=is_ex,
        is_mine=is_mine,
        is_star=is_star,
        head_style=head,
    )
