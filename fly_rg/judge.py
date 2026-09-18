"""Judgment windows, combo, and score tracking (sensor-based)."""

from __future__ import annotations

from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from typing import Literal, Never

from fly_rg.schema import Note
from fly_rg.sensors import button_to_sensor, parse_sensor

Judgment = Literal["critical", "perfect", "great", "good", "miss"]
Timing = Literal["fast", "late"]

# Tap / hold / slide-head windows in seconds, as n/60 (one 60 fps frame).
# Source: donmai, "GekiChuMai Timing Windows and Offsets" (2022-12-29)
# https://listed.to/@donmai/41511/gekichumai-timing-windows-and-offsets
# SilentBlue User:MENDES/Timing copies the same table.
# 1/60 = 16.67ms Critical Perfect; 2/60 high Perfect; 3/60 low Perfect;
# 6/60 Great; 9/60 Good. Owner's ~20ms critical matches 1 frame.
CRITICAL = 1.0 / 60.0
PERFECT_HIGH = 2.0 / 60.0
PERFECT = 3.0 / 60.0
GREAT_HIGH = 4.0 / 60.0
GREAT_MID = 5.0 / 60.0
GREAT = 6.0 / 60.0
GOOD = 9.0 / 60.0

# Touch / touch_hold (same donmai / SilentBlue table). Early within 9/60 is
# Critical; Perfect/Great/Good exist only on the late side.
TOUCH_CRITICAL = 9.0 / 60.0
TOUCH_PERFECT = 12.0 / 60.0
TOUCH_GREAT = 15.0 / 60.0
TOUCH_GOOD = 18.0 / 60.0

# Slide body / waypoint windows (donmai simplified slide row; footnote: slide
# judgement is not only this window). No Perfect tier. Fast Good is unbounded
# on the arcade; middles use a two-sided SLIDE_GOOD match so a press far from
# the interpolated node cannot advance. Per-node times are not stored.
SLIDE_CRITICAL = 14.0 / 60.0
SLIDE_GREAT = 26.0 / 60.0
SLIDE_GOOD = 36.0 / 60.0


# DX achievement tables (donmai / spiritsunite): TAP 1, HOLD 2, SLIDE 3,
# TOUCH 1, BREAK 5 in the 100% pool; extra 1% from break bonus.
# Non-break Great is x0.8. Break Great splits high/mid/low (x0.8 / x0.6 / x0.5)
# in base points only; combo label stays "great". High/low Perfect (2/60 vs
# 3/60) splits only the break bonus (75 vs 50) per spiritsunite / donmai.
_TAP_BASE = {
    "critical": 500,
    "perfect": 500,
    "great": 400,
    "good": 250,
    "miss": 0,
}
_HOLD_BASE = {
    "critical": 1000,
    "perfect": 1000,
    "great": 800,
    "good": 500,
    "miss": 0,
}
_SLIDE_BASE = {
    "critical": 1500,
    "perfect": 1500,
    "great": 1200,
    "good": 750,
    "miss": 0,
}
_BREAK_BASE = {
    "critical": 2500,
    "perfect": 2500,
    "good": 1000,
    "miss": 0,
}
# spiritsunite: Break Great x0.8 / x0.6 / x0.5 of 5 tap-units = 2000 / 1500 / 1250.
_BREAK_GREAT_HIGH = 2000
_BREAK_GREAT_MID = 1500
_BREAK_GREAT_LOW = 1250
_BREAK_BONUS = {
    "critical": 100,
    "perfect": 50,
    "great": 40,
    "good": 30,
    "miss": 0,
}
_DX_POINTS = {
    "critical": 3,
    "perfect": 2,
    "great": 1,
    "good": 0,
    "miss": 0,
}
_JUDGMENT_ORDER: tuple[Judgment, ...] = (
    "miss",
    "good",
    "great",
    "perfect",
    "critical",
)

# ARG wiki hold-drop mapping (https://argw.miraheze.org/wiki/Maimai_DX).
# "just a moment" vs "a while" has no millisecond table; use held_frac.
_HOLD_MOMENT_FRAC = 0.85
_HOLD_WHILE_FRAC = 0.50

# donmai last-zone dl/dt by clockwise places (0 means full loop 0/8).
# Empty cells are omitted (ratio 0).
_STRAIGHT_RATIO: dict[int, float] = {
    2: 0.1920,
    3: 0.1793,
    4: 0.1629,
    5: 0.1793,
    6: 0.1920,
}
_CIRC_CW_RATIO: dict[int, float] = {
    0: 0.0582,
    1: 0.4653,
    2: 0.2326,
    3: 0.1551,
    4: 0.1163,
    5: 0.0931,
    6: 0.0775,
    7: 0.0665,
}
_CIRC_CCW_RATIO: dict[int, float] = {
    0: 0.0582,
    1: 0.0665,
    2: 0.0775,
    3: 0.0931,
    4: 0.1163,
    5: 0.1551,
    6: 0.2326,
    7: 0.4653,
}
# expand_slide("p",1,2) contains B8: donmai Arc along the center CCW (p).
_P_CCW_RATIO: dict[int, float] = {
    0: 0.0921,
    1: 0.0840,
    2: 0.0817,
    3: 0.0752,
    4: 0.1693,
    5: 0.1436,
    6: 0.1247,
    7: 0.1114,
}
# expand_slide("q",1,2) is the opposite: donmai Arc along the center CW (q).
_Q_CW_RATIO: dict[int, float] = {
    0: 0.0921,
    1: 0.1114,
    2: 0.1247,
    3: 0.1436,
    4: 0.1693,
    5: 0.0752,
    6: 0.0817,
    7: 0.0840,
}
_ZIGZAG_RATIO: dict[int, float] = {4: 0.1055}
_V_CENTER_RATIO: dict[int, float] = {
    1: 0.1629,
    2: 0.1629,
    3: 0.1629,
    5: 0.1629,
    6: 0.1629,
    7: 0.1629,
}
_PP_RATIO: dict[int, float] = {
    0: 0.0734,
    1: 0.0872,
    2: 0.1509,
    3: 0.0698,
    4: 0.0698,
    5: 0.0711,
    6: 0.0811,
    7: 0.0603,
}
_QQ_RATIO: dict[int, float] = {
    0: 0.0734,
    1: 0.0603,
    2: 0.0811,
    3: 0.0711,
    4: 0.0698,
    5: 0.0698,
    6: 0.1509,
    7: 0.0872,
}
_GRAND_V_CW_RATIO: dict[int, float] = {4: 0.0960, 5: 0.1018, 6: 0.0955, 7: 0.0948}
_GRAND_V_CCW_RATIO: dict[int, float] = {1: 0.0948, 2: 0.0955, 3: 0.1018, 4: 0.0960}
# Fan w: left dist 5, mid 4, right 3.
_WIFI_RATIO: dict[int, float] = {3: 0.1793, 4: 0.1629, 5: 0.1793}


def _base_max(note: Note) -> int:
    if note.is_mine:
        return 0
    if note.is_break:
        return 2500
    nt = note.type
    if nt == "tap" or nt == "touch":
        return 500
    if nt == "hold" or nt == "touch_hold":
        return 1000
    if nt == "slide":
        return 1500
    _exhaustive: Never = nt
    raise ValueError(f"unknown note type: {_exhaustive}")


def _bonus_max(note: Note) -> int:
    if note.is_mine or not note.is_break:
        return 0
    return 100


def _dx_max(note: Note) -> int:
    return 0 if note.is_mine else 3


def _break_great_base(err: float | None) -> int:
    # donmai tap windows: Great high (3/60, 4/60], mid (4/60, 5/60], low (5/60, 6/60].
    if err is None or err <= GREAT_HIGH:
        return _BREAK_GREAT_HIGH
    if err <= GREAT_MID:
        return _BREAK_GREAT_MID
    return _BREAK_GREAT_LOW


def _break_bonus(judgment: Judgment, err: float | None) -> int:
    if judgment == "perfect":
        if err is not None and err <= PERFECT_HIGH:
            return 75
        return 50
    return _BREAK_BONUS[judgment]


def _judgment_points(
    note: Note, judgment: Judgment, *, err: float | None = None
) -> tuple[int, int, int]:
    dx = _DX_POINTS[judgment]
    if note.is_mine:
        return 0, 0, 0
    if note.is_break:
        if judgment == "great":
            return _break_great_base(err), _break_bonus(judgment, err), dx
        return _BREAK_BASE[judgment], _break_bonus(judgment, err), dx
    nt = note.type
    if nt == "tap" or nt == "touch":
        return _TAP_BASE[judgment], 0, dx
    if nt == "hold" or nt == "touch_hold":
        return _HOLD_BASE[judgment], 0, dx
    if nt == "slide":
        return _SLIDE_BASE[judgment], 0, dx
    _exhaustive: Never = nt
    raise ValueError(f"unknown note type: {_exhaustive}")


def _worse(a: Judgment, b: Judgment) -> Judgment:
    return a if _JUDGMENT_ORDER.index(a) <= _JUDGMENT_ORDER.index(b) else b


def _hold_end(note: Note) -> float:
    return note.end if note.end is not None else note.t


def _is_hold(note: Note) -> bool:
    return note.type == "hold" or note.type == "touch_hold"


def _bisect_left_t(notes: list[Note], t: float) -> int:
    lo, hi = 0, len(notes)
    while lo < hi:
        mid = (lo + hi) // 2
        if notes[mid].t < t:
            lo = mid + 1
        else:
            hi = mid
    return lo


def _bisect_right_t(notes: list[Note], t: float) -> int:
    lo, hi = 0, len(notes)
    while lo < hi:
        mid = (lo + hi) // 2
        if notes[mid].t <= t:
            lo = mid + 1
        else:
            hi = mid
    return lo


@dataclass
class Score:
    combo: int = 0
    critical: int = 0
    perfect: int = 0
    great: int = 0
    good: int = 0
    miss: int = 0
    # Pressed mines; not a DX judgment. Extra to_dict key; protocol.py still
    # forwards the dict unmodified.
    mine: int = 0
    base_points: int = 0
    bonus_points: int = 0
    dx_points: int = 0
    max_base: int = 0
    max_bonus: int = 0
    max_dx: int = 0

    @property
    def judged(self) -> int:
        return self.critical + self.perfect + self.great + self.good + self.miss

    @property
    def accuracy(self) -> float:
        """DX score ratio (CP=3, P=2, Gr=1) against the chart max.

        Default 1.0 when max_dx is 0 (empty chart or mines-only): nothing to miss.
        """
        if self.max_dx <= 0:
            return 1.0
        return self.dx_points / self.max_dx

    @property
    def achievement(self) -> float:
        """maimai DX achievement in 0..1.01 (101% when every break is CP).

        Default 1.0 when max_base is 0 (empty chart or mines-only): nothing to miss.
        """
        if self.max_base <= 0:
            return 1.0
        base = self.base_points / self.max_base
        bonus = (
            (self.bonus_points / self.max_bonus) * 0.01 if self.max_bonus > 0 else 0.0
        )
        return base + bonus

    def to_dict(self) -> dict:
        return {
            "combo": self.combo,
            "critical": self.critical,
            "perfect": self.perfect,
            "great": self.great,
            "good": self.good,
            "miss": self.miss,
            "mine": self.mine,
            "accuracy": float(self.accuracy),
            "achievement": float(self.achievement),
            "dx_score": self.dx_points,
            "dx_max": self.max_dx,
        }


@dataclass
class HitEvent:
    t: float
    button: int | None
    judgment: Judgment
    note_index: int
    sensor: str
    timing: Timing | None = None
    # press minus note, milliseconds; negative is FAST/early.
    error_ms: float | None = None


@dataclass
class Judge:
    """Match presses to sensors; slides advance through path before end_t.

    Hold / touch_hold tails: press() accepts the head and does not score yet.
    Each play-loop step should call auto_miss(now, contacted) with the sensors
    the fly currently occupies. If contacted is omitted, in-progress holds keep
    the head judgment at end and are not mass-missed.
    """

    notes: list[Note]
    matched: list[bool] = field(init=False)
    # Next path index required for slides (0 = waiting for head / path[0]).
    slide_next: list[int] = field(init=False)
    head_judgment: list[Judgment | None] = field(init=False)
    head_timing: list[Timing | None] = field(init=False)
    hold_started: list[bool] = field(init=False)
    hold_dropped: list[bool] = field(init=False)
    hold_held_ticks: list[int] = field(init=False)
    hold_total_ticks: list[int] = field(init=False)
    hold_first_drop_t: list[float | None] = field(init=False)
    score: Score = field(default_factory=Score)

    def __post_init__(self) -> None:
        n = len(self.notes)
        self.matched = [False] * n
        self.slide_next = [0] * n
        self.head_judgment = [None] * n
        self.head_timing = [None] * n
        self.hold_started = [False] * n
        self.hold_dropped = [False] * n
        self.hold_held_ticks = [0] * n
        self.hold_total_ticks = [0] * n
        self.hold_first_drop_t = [None] * n
        self.score.max_base = sum(_base_max(note) for note in self.notes)
        self.score.max_bonus = sum(_bonus_max(note) for note in self.notes)
        self.score.max_dx = sum(_dx_max(note) for note in self.notes)
        self._cursor_now: float | None = None
        self._miss_scan_i = 0
        self._live: set[int] = set()

    def _sync_time_cursor(self, now: float) -> None:
        if self._cursor_now is not None and now < self._cursor_now:
            self._miss_scan_i = 0
            self._live.clear()
        self._cursor_now = now

    def _advance_miss_scan(self) -> None:
        while self._miss_scan_i < len(self.notes) and self.matched[self._miss_scan_i]:
            self._miss_scan_i += 1

    def _mark_live(self, index: int) -> None:
        self._live.add(index)

    def _clear_live(self, index: int) -> None:
        self._live.discard(index)

    def _auto_miss_indices(self, now: float) -> list[int]:
        self._sync_time_cursor(now)
        self._advance_miss_scan()
        out: list[int] = []
        seen: set[int] = set()
        for i in sorted(self._live):
            if not self.matched[i]:
                out.append(i)
                seen.add(i)
        for i in range(self._miss_scan_i, len(self.notes)):
            if self.matched[i]:
                continue
            note = self.notes[i]
            if note.t > now:
                break
            if i not in seen:
                out.append(i)
                seen.add(i)
        return out

    def _active_note_indices(self, now: float, look_ahead_s: float) -> list[int]:
        self._sync_time_cursor(now)
        self._advance_miss_scan()
        t_early = now - look_ahead_s
        i0 = _bisect_left_t(self.notes, t_early)
        i1 = _bisect_right_t(self.notes, now + look_ahead_s)
        out: list[int] = []
        seen: set[int] = set()
        for i in sorted(self._live):
            if not self.matched[i]:
                out.append(i)
                seen.add(i)
        for i in range(i0, i1):
            if self.matched[i] or i in seen:
                continue
            out.append(i)
            seen.add(i)
        for i in range(i0):
            if self.matched[i] or i in seen:
                continue
            note = self.notes[i]
            if not _is_hold(note) or note.end is None:
                continue
            late = _late_window(note)
            if now > note.end + late:
                continue
            if now < note.t - look_ahead_s:
                continue
            out.append(i)
            seen.add(i)
        return out

    def press(self, sensor_or_button: str | int, t: float) -> HitEvent | None:
        """On press, match by sensor id (slides advance path order).

        Accepts a sensor string ('A1', 'C') or button int 1..8 (maps to A{n}).
        """
        if isinstance(sensor_or_button, int):
            sensor = button_to_sensor(sensor_or_button)
        else:
            sensor = sensor_or_button.strip().upper()
            if sensor.startswith("C"):
                sensor = "C"

        # Prefer advancing an in-progress slide inside the waypoint window.
        for i, note in enumerate(self.notes):
            if self.matched[i] or note.type != "slide" or note.slide is None:
                continue
            if self.slide_next[i] <= 0:
                continue
            path = note.slide.path
            nxt = self.slide_next[i]
            if nxt >= len(path):
                continue
            if path[nxt] != sensor:
                continue
            if not _slide_waypoint_in_window(note, nxt, t):
                continue
            return self._advance_slide(i, t)

        # Match head / single-hit notes by sensor within the per-type window.
        best_i: int | None = None
        best_abs = float("inf")
        for i, note in enumerate(self.notes):
            if self.matched[i]:
                continue
            if _is_hold(note) and self.hold_started[i]:
                continue
            target = self._head_sensor(note)
            if target != sensor:
                continue
            if note.type == "slide" and self.slide_next[i] > 0:
                continue
            err = _match_error(note, t)
            if err is not None and err < best_abs:
                best_abs = err
                best_i = i
        if best_i is None:
            return None

        note = self.notes[best_i]
        if note.is_mine:
            return self._hit_mine(best_i, t, sensor)

        judgment, timing = _judge_hit(note, t)
        if note.type == "slide" and note.slide is not None:
            self.slide_next[best_i] = 1
            self._mark_live(best_i)
            self.head_judgment[best_i] = judgment
            self.head_timing[best_i] = timing
            if len(note.slide.path) <= 1:
                self._apply(best_i, judgment, err=abs(note.t - t))
                return HitEvent(
                    t=t,
                    button=note.button,
                    judgment=judgment,
                    note_index=best_i,
                    sensor=sensor,
                    timing=timing,
                    error_ms=_error_ms(note.t, t),
                )
            # Head accepted; body still in progress (not a final score event yet).
            return HitEvent(
                t=t,
                button=note.button,
                judgment=judgment,
                note_index=best_i,
                sensor=sensor,
                timing=timing,
                error_ms=_error_ms(note.t, t),
            )

        if _is_hold(note) and _hold_end(note) > note.t:
            self.hold_started[best_i] = True
            self._mark_live(best_i)
            self.head_judgment[best_i] = judgment
            self.head_timing[best_i] = timing
            return HitEvent(
                t=t,
                button=note.button,
                judgment=judgment,
                note_index=best_i,
                sensor=sensor,
                timing=timing,
                error_ms=_error_ms(note.t, t),
            )

        self._apply(best_i, judgment, err=abs(note.t - t))
        return HitEvent(
            t=t,
            button=note.button,
            judgment=judgment,
            note_index=best_i,
            sensor=sensor,
            timing=timing,
            error_ms=_error_ms(note.t, t),
        )

    def press_button(self, button: int, t: float) -> HitEvent | None:
        """Compatibility helper: press A{button}."""
        return self.press(button_to_sensor(button), t)

    def auto_miss(
        self,
        now: float,
        contacted: AbstractSet[str] | None = None,
    ) -> list[HitEvent]:
        """Miss notes past windows / incomplete slides past the body window.

        ``contacted`` is the set of sensors currently occupied (play-loop
        occupancy, not the intended hold pads). Call each step:

            judge.auto_miss(sim_t, {s for s in (occupancy_l, occupancy_r) if s})

        If ``contacted`` is None, hold tails are not sampled and in-progress
        holds keep their head judgment at end (so an unwired play loop does
        not mass-miss holds).
        """
        events: list[HitEvent] = []
        for i in self._auto_miss_indices(now):
            note = self.notes[i]
            if note.is_mine:
                if now - note.t > _late_window(note):
                    self.matched[i] = True
                    self._clear_live(i)
                continue
            if note.type == "slide" and note.slide is not None:
                if self.slide_next[i] > 0:
                    if now > note.slide.end_t + SLIDE_GOOD:
                        self._apply(i, "miss")
                        events.append(
                            HitEvent(
                                t=note.slide.end_t,
                                button=note.button,
                                judgment="miss",
                                note_index=i,
                                sensor=note.slide.end_sensor,
                                timing=None,
                                error_ms=_error_ms(note.slide.end_t, now),
                            )
                        )
                    continue
                if now - note.t > GOOD:
                    self._apply(i, "miss")
                    events.append(
                        HitEvent(
                            t=note.t,
                            button=note.button,
                            judgment="miss",
                            note_index=i,
                            sensor=note.sensor,
                            timing=None,
                            error_ms=_error_ms(note.t, now),
                        )
                    )
                continue

            if _is_hold(note):
                end = _hold_end(note)
                late = _late_window(note)
                if self.hold_started[i]:
                    self._sample_hold(i, now, contacted)
                    if now > end:
                        events.append(self._finalize_hold(i, now))
                    continue
                if contacted is None:
                    if now - note.t > late:
                        self._apply(i, "miss")
                        events.append(
                            HitEvent(
                                t=note.t,
                                button=note.button,
                                judgment="miss",
                                note_index=i,
                                sensor=note.sensor,
                                timing=None,
                                error_ms=_error_ms(note.t, now),
                            )
                        )
                    continue
                if now > end:
                    events.append(self._finalize_hold(i, now))
                    continue
                if now - note.t > late:
                    self._mark_live(i)
                    if note.sensor in contacted:
                        self.hold_started[i] = True
                        self.head_judgment[i] = "miss"
                        self.head_timing[i] = None
                        self._sample_hold(i, now, contacted)
                    continue
                continue

            if now - note.t > _late_window(note):
                self._apply(i, "miss")
                events.append(
                    HitEvent(
                        t=note.t,
                        button=note.button,
                        judgment="miss",
                        note_index=i,
                        sensor=note.sensor,
                        timing=None,
                        error_ms=_error_ms(note.t, now),
                    )
                )
        return events

    def active_notes(self, now: float, look_ahead_s: float) -> list[dict]:
        """Notes still approaching / in-progress for the state payload."""
        active: list[dict] = []
        for i in self._active_note_indices(now, look_ahead_s):
            note = self.notes[i]
            if note.type == "slide" and note.slide is not None:
                slide = note.slide
                wait_t = float(slide.wait_t)
                end_t = float(slide.end_t)
                # Stay visible through the slide window (approach + travel).
                if now > end_t + GOOD:
                    continue
                if now < note.t - look_ahead_s and self.slide_next[i] == 0:
                    continue
                if now < wait_t:
                    # progress 0..0.5 = approach head from center
                    if look_ahead_s <= 0:
                        approach = 1.0
                    else:
                        approach = max(
                            0.0,
                            min(1.0, 1.0 - (wait_t - now) / look_ahead_s),
                        )
                    progress = 0.5 * approach
                else:
                    # progress 0.5..1.0 = travel along path
                    span = max(end_t - wait_t, 1e-6)
                    travel = max(0.0, min(1.0, (now - wait_t) / span))
                    progress = 0.5 + 0.5 * travel
                # Highlight / aim use the next required path node for judging.
                sensor = self._current_sensor(note, i)
                active.append(self._note_payload(note, sensor, float(progress)))
                continue

            tth = note.t - now
            late = _late_window(note)
            # Holds stay visible until release end.
            if _is_hold(note) and note.end is not None:
                if now > note.end + late:
                    continue
                if now < note.t - look_ahead_s:
                    continue
                if now < note.t:
                    progress = (
                        0.0
                        if look_ahead_s <= 0
                        else max(0.0, min(1.0, 1.0 - (note.t - now) / look_ahead_s))
                    )
                    hold_phase = "approach"
                else:
                    span = max(note.end - note.t, 1e-6)
                    progress = max(0.0, min(1.0, (now - note.t) / span))
                    hold_phase = "sustain"
                active.append(
                    self._note_payload(
                        note, note.sensor, progress, hold_phase=hold_phase
                    )
                )
                continue

            if tth < -late or tth > look_ahead_s:
                continue
            if look_ahead_s <= 0:
                progress = 1.0
            else:
                progress = max(0.0, min(1.0, 1.0 - tth / look_ahead_s))
            active.append(
                self._note_payload(note, self._current_sensor(note, i), progress)
            )
        return active

    def _note_payload(
        self,
        note: Note,
        sensor: str,
        progress: float,
        hold_phase: str | None = None,
    ) -> dict:
        row: dict = {
            "t": note.t,
            "button": note.button,
            "sensor": sensor,
            "progress": float(progress),
            "type": note.type,
            "is_break": note.is_break,
            "is_ex": note.is_ex,
            "is_mine": note.is_mine,
            "is_hanabi": note.is_hanabi,
            "is_star": note.is_star,
            "is_each": note.is_each,
            "head_style": note.head_style,
        }
        if note.end is not None:
            row["end"] = note.end
        if hold_phase is not None:
            row["hold_phase"] = hold_phase
        if note.slide is not None:
            row["path"] = list(note.slide.path)
            row["slide"] = note.slide.to_dict()
        return row

    def active_sensors(self, now: float, look_ahead_s: float) -> list[str]:
        """Distinct sensors currently targeted (next slide node or note sensor)."""
        seen: list[str] = []
        for row in self.active_notes(now, look_ahead_s):
            s = str(row["sensor"])
            if s not in seen:
                seen.append(s)
        return seen

    def current_target_sensor(self, note: Note, index: int) -> str:
        return self._current_sensor(note, index)

    def done(self) -> bool:
        return all(self.matched)

    def _head_sensor(self, note: Note) -> str:
        if note.type == "slide" and note.slide is not None and note.slide.path:
            return note.slide.path[0]
        return note.sensor

    def _current_sensor(self, note: Note, index: int) -> str:
        if note.type == "slide" and note.slide is not None and note.slide.path:
            nxt = self.slide_next[index]
            if nxt >= len(note.slide.path):
                return note.slide.path[-1]
            return note.slide.path[nxt]
        return note.sensor

    def _hit_mine(self, index: int, t: float, sensor: str) -> HitEvent:
        note = self.notes[index]
        self.matched[index] = True
        self.score.combo = 0
        self.score.mine += 1
        return HitEvent(
            t=t,
            button=note.button,
            judgment="miss",
            note_index=index,
            sensor=sensor,
            timing=None,
            error_ms=_error_ms(note.t, t),
        )

    def _sample_hold(
        self,
        index: int,
        now: float,
        contacted: AbstractSet[str] | None,
    ) -> None:
        if contacted is None:
            return
        note = self.notes[index]
        end = _hold_end(note)
        if now <= note.t or now > end:
            return
        if not self.hold_started[index]:
            return
        self.hold_total_ticks[index] += 1
        if note.sensor in contacted:
            self.hold_held_ticks[index] += 1
            return
        if not self.hold_dropped[index]:
            self.hold_first_drop_t[index] = now
        self.hold_dropped[index] = True

    def _finalize_hold(self, index: int, now: float) -> HitEvent:
        note = self.notes[index]
        stored = self.head_judgment[index]
        timing = self.head_timing[index]
        judgment, timing = _hold_drop_judgment(
            note,
            stored,
            timing,
            duration=_hold_end(note) - note.t,
            held_ticks=self.hold_held_ticks[index],
            total_ticks=self.hold_total_ticks[index],
            dropped=self.hold_dropped[index],
            first_drop_t=self.hold_first_drop_t[index],
        )
        self._apply(index, judgment)
        return HitEvent(
            t=now,
            button=note.button,
            judgment=judgment,
            note_index=index,
            sensor=note.sensor,
            timing=timing,
            error_ms=_error_ms(_hold_end(note), now),
        )

    def _advance_slide(self, index: int, t: float) -> HitEvent:
        note = self.notes[index]
        assert note.slide is not None
        path = note.slide.path
        nxt = self.slide_next[index]
        expected = _slide_node_t(note, nxt)
        body_j, body_timing = _judge_slide_body(
            expected - t,
            critical_window=_slide_critical_window(note, nxt),
        )
        stored = self.head_judgment[index] or "critical"
        combined = _worse(stored, body_j)
        self.head_judgment[index] = combined
        if body_j != "critical":
            self.head_timing[index] = body_timing
        self.slide_next[index] += 1
        sensor = path[nxt]
        if self.slide_next[index] >= len(path):
            timing: Timing | None = self.head_timing[index]
            if combined == "critical":
                timing = None
            self._apply(index, combined, err=abs(expected - t))
            return HitEvent(
                t=t,
                button=note.button,
                judgment=combined,
                note_index=index,
                sensor=sensor,
                timing=timing,
                error_ms=_error_ms(expected, t),
            )
        return HitEvent(
            t=t,
            button=note.button,
            judgment=body_j,
            note_index=index,
            sensor=sensor,
            timing=body_timing,
            error_ms=_error_ms(expected, t),
        )

    def _apply(
        self, index: int, judgment: Judgment, *, err: float | None = None
    ) -> None:
        self.matched[index] = True
        self._clear_live(index)
        base, bonus, dx = _judgment_points(self.notes[index], judgment, err=err)
        self.score.base_points += base
        self.score.bonus_points += bonus
        self.score.dx_points += dx
        if judgment == "critical":
            self.score.critical += 1
            self.score.combo += 1
        elif judgment == "perfect":
            self.score.perfect += 1
            self.score.combo += 1
        elif judgment == "great":
            self.score.great += 1
            self.score.combo += 1
        elif judgment == "good":
            self.score.good += 1
            self.score.combo += 1
        elif judgment == "miss":
            self.score.miss += 1
            self.score.combo = 0
        else:
            _exhaustive: Never = judgment
            raise ValueError(f"unknown judgment: {_exhaustive}")


def _error_ms(note_t: float, press_t: float) -> float:
    return (press_t - note_t) * 1000.0


def _late_window(note: Note) -> float:
    if note.is_ex:
        return GOOD
    nt = note.type
    if nt == "touch" or nt == "touch_hold":
        return TOUCH_GOOD
    if nt == "tap" or nt == "hold" or nt == "slide":
        return GOOD
    _exhaustive: Never = nt
    raise ValueError(f"unknown note type: {_exhaustive}")


def _match_error(note: Note, t: float) -> float | None:
    """Absolute error if press at t is inside this note's match window."""
    delta = note.t - t
    if note.is_ex:
        # donmai Ex and ExBreak: [-150, 150] ms Critical, else Miss.
        if abs(delta) > GOOD:
            return None
        return abs(delta)
    nt = note.type
    if nt == "touch" or nt == "touch_hold":
        # Early only to 150ms; late extends to 300ms.
        if delta > TOUCH_CRITICAL or -delta > TOUCH_GOOD:
            return None
        return abs(delta)
    if nt == "tap" or nt == "hold" or nt == "slide":
        if abs(delta) > GOOD:
            return None
        return abs(delta)
    _exhaustive: Never = nt
    raise ValueError(f"unknown note type: {_exhaustive}")


def _judge_hit(note: Note, t: float) -> tuple[Judgment, Timing | None]:
    if _match_error(note, t) is None:
        return "miss", None
    if note.is_ex:
        return "critical", None
    nt = note.type
    delta = note.t - t
    if nt == "tap" or nt == "hold" or nt == "slide":
        return _judge_tap(delta)
    if nt == "touch" or nt == "touch_hold":
        return _judge_touch(delta)
    _exhaustive: Never = nt
    raise ValueError(f"unknown note type: {_exhaustive}")


def _timing_for_delta(delta: float) -> Timing:
    return "fast" if delta > 0 else "late"


def _judge_tap(delta: float) -> tuple[Judgment, Timing | None]:
    err = abs(delta)
    if err <= CRITICAL:
        return "critical", None
    timing = _timing_for_delta(delta)
    if err <= PERFECT:
        return "perfect", timing
    if err <= GREAT:
        return "great", timing
    if err <= GOOD:
        return "good", timing
    return "miss", None


def _judge_touch(delta: float) -> tuple[Judgment, Timing | None]:
    if delta >= 0:
        if delta <= TOUCH_CRITICAL:
            return "critical", None
        return "miss", None
    late = -delta
    if late <= TOUCH_CRITICAL:
        return "critical", None
    timing = _timing_for_delta(delta)
    if late <= TOUCH_PERFECT:
        return "perfect", timing
    if late <= TOUCH_GREAT:
        return "great", timing
    if late <= TOUCH_GOOD:
        return "good", timing
    return "miss", None


def _slide_travel_start(note: Note) -> float:
    assert note.slide is not None
    wait_t = float(note.slide.wait_t)
    return wait_t if wait_t > 0.0 else note.t


def _slide_node_t(note: Note, node_index: int) -> float:
    """Expected time for path[node_index].

    Per-node times are not stored; interpolate wait_t..end_t (or note.t when
    wait_t is unset) across path indices 0..len-1. Head (0) stays at note.t.
    """
    assert note.slide is not None
    if node_index <= 0:
        return note.t
    start = _slide_travel_start(note)
    path = note.slide.path
    denom = max(len(path) - 1, 1)
    return start + (note.slide.end_t - start) * (node_index / denom)


def _slide_waypoint_in_window(note: Note, node_index: int, t: float) -> bool:
    expected = _slide_node_t(note, node_index)
    return abs(expected - t) <= SLIDE_GOOD


def _grand_v_shape(shape: str) -> bool:
    if shape == "V":
        return True
    return len(shape) > 1 and shape[0] == "V" and shape[1:].isdigit()


def _path_ring_clockwise(note: Note) -> bool | None:
    if note.slide is None:
        return None
    prev: int | None = None
    for sensor in note.slide.path:
        area, idx = parse_sensor(sensor)
        if area != "A":
            continue
        if prev is not None:
            step = (idx - prev) % 8
            if step == 1:
                return True
            if step == 7:
                return False
        prev = idx
    return None


def _slide_last_zone_ratio(note: Note) -> float:
    """donmai last-zone dl/dt. Unknown shape or empty cell is 0."""
    if note.slide is None:
        return 0.0
    start = note.button
    if start is None:
        return 0.0
    area, end_idx = parse_sensor(note.slide.end_sensor)
    if area != "A":
        return 0.0
    dist = (end_idx - start) % 8
    shape = note.slide.shape
    if shape == "-":
        return _STRAIGHT_RATIO.get(dist, 0.0)
    if shape == ">" or shape == "<" or shape == "^":
        cw = _path_ring_clockwise(note)
        if cw is None:
            return 0.0
        table = _CIRC_CW_RATIO if cw else _CIRC_CCW_RATIO
        return table.get(dist, 0.0)
    if shape == "p":
        return _P_CCW_RATIO.get(dist, 0.0)
    if shape == "q":
        return _Q_CW_RATIO.get(dist, 0.0)
    if shape == "s" or shape == "z":
        return _ZIGZAG_RATIO.get(dist, 0.0)
    if shape == "v":
        return _V_CENTER_RATIO.get(dist, 0.0)
    if shape == "pp":
        return _PP_RATIO.get(dist, 0.0)
    if shape == "qq":
        return _QQ_RATIO.get(dist, 0.0)
    if shape == "w":
        return _WIFI_RATIO.get(dist, 0.0)
    if _grand_v_shape(shape):
        is_cw: bool | None
        if len(shape) > 1 and shape[1:].isdigit():
            mid = int(shape[1:])
            step = (mid - start) % 8
            is_cw = 0 < step <= 4
        else:
            is_cw = _path_ring_clockwise(note)
        if is_cw is None:
            return 0.0
        table = _GRAND_V_CW_RATIO if is_cw else _GRAND_V_CCW_RATIO
        return table.get(dist, 0.0)
    return 0.0


def _slide_critical_window(note: Note, node_index: int) -> float:
    # donmai https://listed.to/@donmai/44545/how-maimai-dx-judges-slides
    # total leeway = ta * (dl/dt) / 2; CP expands by half of that on each side
    # (ta * ratio / 4). Other windows unmodified. Last path node only.
    if note.slide is None or node_index != len(note.slide.path) - 1:
        return SLIDE_CRITICAL
    ratio = _slide_last_zone_ratio(note)
    if ratio <= 0.0:
        return SLIDE_CRITICAL
    ta = note.slide.end_t - _slide_travel_start(note)
    if ta <= 0.0:
        return SLIDE_CRITICAL
    return SLIDE_CRITICAL + ta * ratio / 4.0


def _judge_slide_body(
    delta: float, *, critical_window: float = SLIDE_CRITICAL
) -> tuple[Judgment, Timing | None]:
    err = abs(delta)
    if err <= critical_window:
        return "critical", None
    timing = _timing_for_delta(delta)
    if err <= SLIDE_GREAT:
        return "great", timing
    if err <= SLIDE_GOOD:
        return "good", timing
    return "miss", None


def _ex_hold_no_good(note: Note, judgment: Judgment) -> Judgment:
    # ARG: EX holds replace Goods with Greats; head hit is already CP.
    if note.is_ex and judgment == "good":
        return "great"
    return judgment


def _hold_drop_judgment(
    note: Note,
    stored: Judgment | None,
    timing: Timing | None,
    *,
    duration: float,
    held_ticks: int,
    total_ticks: int,
    dropped: bool,
    first_drop_t: float | None,
) -> tuple[Judgment, Timing | None]:
    """ARG wiki Hold Notes (https://argw.miraheze.org/wiki/Maimai_DX).

    If the start of the hold was a Critical Perfect:
    and the hold was held to the end -> Critical Perfect
    and the hold note was released right at the end, but the hold didn't turn
    grey -> Critical Perfect (drop only in the last ~1 frame)
    and the hold note was released at the end, but turned grey -> Perfect (Late)
    and the hold note was released for just a moment midhold -> Perfect (Early)
    and the hold note was released for a while -> Good or Great, depending on
    length of hold and amount held

    If the start of the hold was not a CP:
    Perfect, Great or Good on head, held from start to end: Goods become Greats
    Perfect on head, released for just a moment: Great (keep head fast/late)
    Great or Good on head, released for just a moment: same as head
    Miss on head, held for remainder of duration: Good (Late)
    Miss on head, hold untouched: Miss

    NB: some very short holds can be treated as taps.
    """
    head: Judgment = "miss" if stored is None else stored
    if duration < GOOD:
        if head == "critical":
            timing = None
        return _ex_hold_no_good(note, head), timing

    held_frac = 1.0 if total_ticks <= 0 else held_ticks / total_ticks
    end = _hold_end(note)
    last_frame_drop = (
        first_drop_t is not None and (end - first_drop_t) <= CRITICAL
    )
    released_at_end = (
        first_drop_t is not None
        and duration > 0.0
        and (first_drop_t - note.t) / duration >= _HOLD_MOMENT_FRAC
    )

    if head == "miss":
        if held_ticks > 0:
            return _ex_hold_no_good(note, "good"), "late"
        return "miss", None

    if not dropped or last_frame_drop:
        judgment: Judgment = "great" if head == "good" else head
        if judgment == "critical":
            timing = None
        return _ex_hold_no_good(note, judgment), timing

    if head == "critical":
        if released_at_end:
            out: Judgment = "perfect"
            timing = "late"
        elif held_frac >= _HOLD_MOMENT_FRAC:
            out = "perfect"
            timing = "fast"
        elif held_frac >= _HOLD_WHILE_FRAC:
            out = "great"
            timing = "fast"
        else:
            out = "good"
            timing = "fast"
        return _ex_hold_no_good(note, out), timing

    if released_at_end or held_frac >= _HOLD_MOMENT_FRAC:
        if head == "perfect":
            judgment = "great"
        else:
            judgment = head
    elif held_frac >= _HOLD_WHILE_FRAC:
        if head == "perfect" or head == "great":
            judgment = "great"
        else:
            judgment = head
    else:
        judgment = "good"
    return _ex_hold_no_good(note, judgment), timing
