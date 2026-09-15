"""Load timed charts from JSON or a Simai maidata subset."""

from __future__ import annotations

import json
import re
import warnings
from pathlib import Path

from fly_rg.schema import Chart, Note

_META_RE = re.compile(r"^&(title|artist|first|inote_(\d+))\s*=\s*(.*)$", re.IGNORECASE | re.DOTALL)
_BPM_RE = re.compile(r"\((\d+(?:\.\d+)?)\)")
_DIV_RE = re.compile(r"\{(\d+)\}")
# Hold: 1h[8:1] or 1h[#1.5]; optional break marker b before/after h is ignored as type.
_HOLD_RE = re.compile(
    r"([1-8])b?h(?:b)?\[(?:#(\d+(?:\.\d+)?)|(\d+)\s*:\s*(\d+))\]",
    re.IGNORECASE,
)
_TAP_RE = re.compile(r"([1-8])(b)?")
# Tokens we skip with a warning (slides, touch, etc.).


def load_chart_json(path: str | Path) -> Chart:
    """Load a chart from timed-note JSON."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return Chart.from_dict(data)


def load_chart(path: str | Path) -> Chart:
    """Auto-detect .json vs maidata (.txt or other) and load."""
    p = Path(path)
    if p.suffix.lower() == ".json":
        return load_chart_json(p)
    return parse_simai_subset(p.read_text(encoding="utf-8"))


def parse_simai_subset(text: str) -> Chart:
    """Parse a minimal Simai subset into a timed Chart.

    Supported:
      &title=, &artist=, &first=
      (bpm), {divisor}
      taps 1-8, break 1b (treated as tap)
      holds 1h[n:m] or 1h[#seconds]
      commas as beat steps, / as each (simultaneous)

    Slides, touch notes, and other syntax are skipped with a warning.
    """
    title = ""
    artist = ""
    offset = 0.0
    chart_body = ""

    # Strip comments and gather meta / inote bodies.
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.split("||", 1)[0].strip()
        if not line:
            continue
        lines.append(line)

    inote_parts: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("&"):
            # Meta may span until next & or chart end for &inote_N=
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
                chunk = inote_match.group(2)
                i += 1
                while i < len(lines) and not lines[i].startswith("&"):
                    chunk += lines[i]
                    i += 1
                inote_parts.append(chunk.rstrip("E").rstrip())
                continue
        i += 1

    if inote_parts:
        chart_body = "".join(inote_parts)
    else:
        # Fallback: treat non-meta lines as chart text (simple demo files).
        chart_body = "".join(
            ln for ln in lines if not ln.startswith("&")
        ).rstrip("E")

    notes = _parse_note_stream(chart_body, offset)
    return Chart(title=title, artist=artist, offset=offset, notes=notes)


def _parse_note_stream(body: str, offset: float) -> list[Note]:
    bpm = 120.0
    divisor = 4
    t = float(offset)
    notes: list[Note] = []
    pos = 0
    body = re.sub(r"\s+", "", body)

    def step_seconds() -> float:
        # {d}: each comma is (4/d) beats at current BPM.
        return (60.0 / bpm) * (4.0 / divisor)

    def hold_duration(n: int, m: int) -> float:
        return (60.0 / bpm) * (4.0 / n) * m

    while pos < len(body):
        ch = body[pos]
        if ch == ",":
            t += step_seconds()
            pos += 1
            continue
        if ch == "/":
            pos += 1
            continue
        if ch == "E":
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

        hold_m = _HOLD_RE.match(body, pos)
        if hold_m:
            button = int(hold_m.group(1))
            if hold_m.group(2) is not None:
                dur = float(hold_m.group(2))
            else:
                dur = hold_duration(int(hold_m.group(3)), int(hold_m.group(4)))
            notes.append(Note(t=t, button=button, type="hold", end=t + dur))
            pos = hold_m.end()
            continue

        tap_m = _TAP_RE.match(body, pos)
        if tap_m:
            # Avoid consuming the leading digit of a hold (handled above).
            button = int(tap_m.group(1))
            notes.append(Note(t=t, button=button, type="tap", end=None))
            pos = tap_m.end()
            continue

        # Skip unknown tokens (slides Vw, touch A1, etc.).
        if body[pos] in "ABCDEFGabcdefgVWvw<>$?!@#%^*&=~`|\\.;:[](){}":
            # Advance one char, or a short known slide/touch chunk.
            warnings.warn(f"skipping unsupported simai token near: {body[pos:pos+8]!r}", stacklevel=2)
            pos += 1
            continue

        warnings.warn(f"skipping unrecognized simai char {body[pos]!r}", stacklevel=2)
        pos += 1

    notes.sort(key=lambda n: (n.t, n.button))
    return notes
