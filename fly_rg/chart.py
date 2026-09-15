"""Load timed charts from JSON or a Simai maidata subset."""

from __future__ import annotations

import json
import re
import warnings
from pathlib import Path

from fly_rg.schema import Chart, Note, SlideInfo
from fly_rg.sensors import button_to_sensor, format_sensor, parse_sensor
from fly_rg.slides import SUPPORTED_SHAPES, expand_slide

_BPM_RE = re.compile(r"\((\d+(?:\.\d+)?)\)")
_DIV_RE = re.compile(r"\{(\d+)\}")
# Hold: 1h[8:1] or 1h[#1.5]; optional break marker b before/after h is ignored as type.
_HOLD_RE = re.compile(
    r"([1-8])b?h(?:b)?\[(?:#(\d+(?:\.\d+)?)|(\d+)\s*:\s*(\d+))\]",
    re.IGNORECASE,
)
# Slide: 1-5[8:1], 1>3[8:1], optional break b after start digit.
_SLIDE_RE = re.compile(
    r"([1-8])b?([-><\^vV])([1-8])\[(?:#(\d+(?:\.\d+)?)|(\d+)\s*:\s*(\d+))\]",
)
# Touch hold: A1h[8:1], B2fh[#1], Ch[4:1], C1h[#0.5]
_TOUCH_HOLD_RE = re.compile(
    r"([A-Ea-e])([1-8])?(f)?h\[(?:#(\d+(?:\.\d+)?)|(\d+)\s*:\s*(\d+))\]",
    re.IGNORECASE,
)
# Touch: A1, B2f, C, C1, D5, E3f
_TOUCH_RE = re.compile(r"([A-Ea-e])([1-8])?(f)?", re.IGNORECASE)
_TAP_RE = re.compile(r"([1-8])(b)?")


def load_chart_json(path: str | Path) -> Chart:
    """Load a chart from timed-note JSON."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return Chart.from_dict(data)


def list_difficulties(text: str) -> list[dict[str, str | int]]:
    """Return available chart levels from &lv_N= / &inote_N=."""
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
    """Auto-detect .json vs maidata (.txt or other) and load."""
    p = Path(path)
    if p.suffix.lower() == ".json":
        return load_chart_json(p)
    return parse_simai_subset(p.read_text(encoding="utf-8"), difficulty=difficulty)


def parse_simai_subset(text: str, difficulty: int | None = None) -> Chart:
    """Parse a minimal Simai subset into a timed Chart.

    Supported:
      &title=, &artist=, &first=
      (bpm), {divisor}
      taps 1-8, break 1b (treated as tap)
      holds 1h[n:m] or 1h[#seconds]
      touch A1 / B2f / C / D5 / E3
      touch hold A1h[n:m]
      basic slides 1-5[8:1], 1>3[8:1], shapes - > < ^ v V
      commas as beat steps, / as each (simultaneous)

    Wifi / exotic slides are skipped with a warning.
    If difficulty is set, only &inote_{difficulty}= is used; otherwise the
    lowest numbered inote is used (not all concatenated).
    """
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
            key_match = re.match(r"^&(title|artist|first)\s*=\s*(.*)$", line, re.IGNORECASE)
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
                    f"no &inote_{difficulty}= in maidata "
                    f"(have {sorted(inotes)})"
                )
            chart_body = inotes[difficulty]
        else:
            chart_body = inotes[min(inotes)]
    else:
        chart_body = "".join(
            ln for ln in lines if not ln.startswith("&")
        ).rstrip("E")

    notes = _parse_note_stream(chart_body, offset)
    return Chart(title=title, artist=artist, offset=offset, notes=notes)


def _normalize_touch_sensor(area: str, index: str | None) -> str:
    area_u = area.upper()
    if area_u == "C":
        return "C"
    if not index:
        raise ValueError(f"touch area {area_u} requires index 1..8")
    return format_sensor(area_u, int(index))  # type: ignore[arg-type]


def _parse_note_stream(body: str, offset: float) -> list[Note]:
    bpm = 120.0
    divisor = 4
    t = float(offset)
    notes: list[Note] = []
    pos = 0
    body = re.sub(r"\s+", "", body)

    def step_seconds() -> float:
        return (60.0 / bpm) * (4.0 / divisor)

    def hold_duration(n: int, m: int) -> float:
        return (60.0 / bpm) * (4.0 / n) * m

    def parse_len(groups_hash: str | None, n: str | None, m: str | None) -> float:
        if groups_hash is not None:
            return float(groups_hash)
        return hold_duration(int(n or "4"), int(m or "1"))

    while pos < len(body):
        ch = body[pos]
        if ch == ",":
            t += step_seconds()
            pos += 1
            continue
        if ch == "/":
            pos += 1
            continue
        if ch in "Ee":
            # Bare E ends the chart; E1..E8 / Eh / Ef are touch notes.
            if not (
                _TOUCH_HOLD_RE.match(body, pos)
                or (
                    (touch_e := _TOUCH_RE.match(body, pos)) is not None
                    and touch_e.group(2) is not None
                )
            ):
                break

        bpm_m = _BPM_RE.match(body, pos)
        if bpm_m:
            bpm = float(bpm_m.group(1))
            pos = bpm_m.end()
            continue

        div_m = _DIV_RE.match(body, pos)
        if div_m:
            divisor = int(div_m.group(1))
            if divisor <= 0:
                raise ValueError(f"invalid divisor {{{div_m.group(1)}}}")
            pos = div_m.end()
            continue

        touch_hold_m = _TOUCH_HOLD_RE.match(body, pos)
        if touch_hold_m:
            try:
                sensor = _normalize_touch_sensor(touch_hold_m.group(1), touch_hold_m.group(2))
            except ValueError:
                warnings.warn(
                    f"skipping bad touch hold near: {body[pos:pos+12]!r}",
                    stacklevel=2,
                )
                pos = touch_hold_m.end()
                continue
            dur = parse_len(touch_hold_m.group(4), touch_hold_m.group(5), touch_hold_m.group(6))
            notes.append(
                Note(
                    t=t,
                    type="touch_hold",
                    sensor=sensor,
                    end=t + dur,
                )
            )
            pos = touch_hold_m.end()
            continue

        touch_m = _TOUCH_RE.match(body, pos)
        if touch_m and touch_m.group(1).upper() in "ABCDE":
            # Avoid stealing trailing letters from unrelated tokens; require area letter.
            area = touch_m.group(1)
            # Do not match if this looks like nothing (should always match letter).
            try:
                sensor = _normalize_touch_sensor(area, touch_m.group(2))
                parse_sensor(sensor)  # validate
            except ValueError:
                warnings.warn(
                    f"skipping bad touch near: {body[pos:pos+8]!r}",
                    stacklevel=2,
                )
                pos = touch_m.end()
                continue
            notes.append(Note(t=t, type="touch", sensor=sensor, end=None))
            pos = touch_m.end()
            continue

        hold_m = _HOLD_RE.match(body, pos)
        if hold_m:
            button = int(hold_m.group(1))
            if hold_m.group(2) is not None:
                dur = float(hold_m.group(2))
            else:
                dur = hold_duration(int(hold_m.group(3)), int(hold_m.group(4)))
            notes.append(
                Note(
                    t=t,
                    button=button,
                    type="hold",
                    sensor=button_to_sensor(button),
                    end=t + dur,
                )
            )
            pos = hold_m.end()
            continue

        slide_m = _SLIDE_RE.match(body, pos)
        if slide_m:
            start = int(slide_m.group(1))
            shape = slide_m.group(2)
            end_btn = int(slide_m.group(3))
            if shape not in SUPPORTED_SHAPES:
                warnings.warn(
                    f"skipping unsupported slide shape {shape!r} near: {body[pos:pos+12]!r}",
                    stacklevel=2,
                )
                pos = slide_m.end()
                continue
            try:
                path = expand_slide(shape, start, end_btn)
            except ValueError as exc:
                warnings.warn(f"skipping slide: {exc}", stacklevel=2)
                pos = slide_m.end()
                continue
            dur = parse_len(slide_m.group(4), slide_m.group(5), slide_m.group(6))
            end_t = t + dur
            end_sensor = path[-1]
            notes.append(
                Note(
                    t=t,
                    button=start,
                    type="slide",
                    sensor=path[0],
                    end=end_t,
                    slide=SlideInfo(
                        shape=shape,
                        end_sensor=end_sensor,
                        path=tuple(path),
                        end_t=end_t,
                    ),
                )
            )
            pos = slide_m.end()
            continue

        # Wifi / exotic multi-char shapes after a digit: warn and skip to comma.
        exotic = re.match(r"[1-8]b?[pqszwPPQSZWqqpp]{1,3}", body[pos:])
        if exotic:
            warnings.warn(
                f"skipping unsupported slide near: {body[pos:pos+12]!r}",
                stacklevel=2,
            )
            while pos < len(body) and body[pos] not in ",/E":
                if body[pos] == "[":
                    close = body.find("]", pos)
                    pos = len(body) if close < 0 else close + 1
                    continue
                pos += 1
            continue

        tap_m = _TAP_RE.match(body, pos)
        if tap_m:
            button = int(tap_m.group(1))
            notes.append(
                Note(
                    t=t,
                    button=button,
                    type="tap",
                    sensor=button_to_sensor(button),
                    end=None,
                )
            )
            pos = tap_m.end()
            continue

        if body[pos] in "ABCDEFGabcdefgVWvw<>$?!@#%^*&=~`|\\.;:[](){}":
            warnings.warn(f"skipping unsupported simai token near: {body[pos:pos+8]!r}", stacklevel=2)
            pos += 1
            continue

        warnings.warn(f"skipping unrecognized simai char {body[pos]!r}", stacklevel=2)
        pos += 1

    notes.sort(key=lambda n: (n.t, n.sensor, n.button or 0))
    return notes
