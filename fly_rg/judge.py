"""Judgment windows, combo, and score tracking (sensor-based)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Never

from fly_rg.schema import Note
from fly_rg.sensors import button_to_sensor

Judgment = Literal["critical", "perfect", "great", "good", "miss"]
Timing = Literal["fast", "late"]

# Tap / hold / slide head (seconds). GOOD is the tap-like miss window.
CRITICAL = 0.01667
PERFECT = 0.050
GREAT = 0.100
GOOD = 0.150

# Touch / touch_hold. Late-only Perfect/Great/Good; early within 150ms is Critical.
TOUCH_CRITICAL = 0.150
TOUCH_PERFECT = 0.200
TOUCH_GREAT = 0.250
TOUCH_GOOD = 0.300


# DX achievement tables (donmai / spiritsunite): TAP 1, HOLD 2, SLIDE 3,
# TOUCH 1, BREAK 5 in the 100% pool; extra 1% from break bonus.
# Great uses the high-great row (x0.8). Perfect-break bonus uses low Perfect
# (50) because this judge does not split high/low Perfect.
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
    "great": 2000,
    "good": 1000,
    "miss": 0,
}
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


def _judgment_points(note: Note, judgment: Judgment) -> tuple[int, int, int]:
    dx = _DX_POINTS[judgment]
    if note.is_mine:
        return 0, 0, 0
    if note.is_break:
        return _BREAK_BASE[judgment], _BREAK_BONUS[judgment], dx
    nt = note.type
    if nt == "tap" or nt == "touch":
        return _TAP_BASE[judgment], 0, dx
    if nt == "hold" or nt == "touch_hold":
        return _HOLD_BASE[judgment], 0, dx
    if nt == "slide":
        return _SLIDE_BASE[judgment], 0, dx
    _exhaustive: Never = nt
    raise ValueError(f"unknown note type: {_exhaustive}")


@dataclass
class Score:
    combo: int = 0
    critical: int = 0
    perfect: int = 0
    great: int = 0
    good: int = 0
    miss: int = 0
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
        """DX score ratio (CP=3, P=2, Gr=1) against the chart max."""
        if self.max_dx <= 0:
            return 1.0
        return self.dx_points / self.max_dx

    @property
    def achievement(self) -> float:
        """maimai DX achievement in 0..1.01 (101% when every break is CP)."""
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


@dataclass
class Judge:
    """Match presses to sensors; slides advance through path before end_t."""

    notes: list[Note]
    matched: list[bool] = field(init=False)
    # Next path index required for slides (0 = waiting for head / path[0]).
    slide_next: list[int] = field(init=False)
    head_judgment: list[Judgment | None] = field(init=False)
    head_timing: list[Timing | None] = field(init=False)
    score: Score = field(default_factory=Score)

    def __post_init__(self) -> None:
        n = len(self.notes)
        self.matched = [False] * n
        self.slide_next = [0] * n
        self.head_judgment = [None] * n
        self.head_timing = [None] * n
        self.score.max_base = sum(_base_max(note) for note in self.notes)
        self.score.max_bonus = sum(_bonus_max(note) for note in self.notes)
        self.score.max_dx = sum(_dx_max(note) for note in self.notes)

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

        # Prefer advancing an in-progress slide.
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
            return self._advance_slide(i, t)

        # Match head / single-hit notes by sensor within the per-type window.
        best_i: int | None = None
        best_abs = float("inf")
        for i, note in enumerate(self.notes):
            if self.matched[i]:
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
        judgment, timing = _judge_hit(note, t)
        if note.type == "slide" and note.slide is not None:
            self.slide_next[best_i] = 1
            self.head_judgment[best_i] = judgment
            self.head_timing[best_i] = timing
            if len(note.slide.path) <= 1:
                self._apply(best_i, judgment)
                return HitEvent(
                    t=t,
                    button=note.button,
                    judgment=judgment,
                    note_index=best_i,
                    sensor=sensor,
                    timing=timing,
                )
            # Head accepted; body still in progress (not a final score event yet).
            return HitEvent(
                t=t,
                button=note.button,
                judgment=judgment,
                note_index=best_i,
                sensor=sensor,
                timing=timing,
            )

        self._apply(best_i, judgment)
        return HitEvent(
            t=t,
            button=note.button,
            judgment=judgment,
            note_index=best_i,
            sensor=sensor,
            timing=timing,
        )

    def press_button(self, button: int, t: float) -> HitEvent | None:
        """Compatibility helper: press A{button}."""
        return self.press(button_to_sensor(button), t)

    def auto_miss(self, now: float) -> list[HitEvent]:
        """Miss notes past windows / incomplete slides past end_t."""
        events: list[HitEvent] = []
        for i, note in enumerate(self.notes):
            if self.matched[i]:
                continue
            if note.type == "slide" and note.slide is not None:
                if self.slide_next[i] > 0:
                    if now > note.slide.end_t:
                        self._apply(i, "miss")
                        events.append(
                            HitEvent(
                                t=note.slide.end_t,
                                button=note.button,
                                judgment="miss",
                                note_index=i,
                                sensor=note.slide.end_sensor,
                                timing=None,
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
                        )
                    )
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
                    )
                )
        return events

    def active_notes(self, now: float, look_ahead_s: float) -> list[dict]:
        """Notes still approaching / in-progress for the state payload."""
        active: list[dict] = []
        for i, note in enumerate(self.notes):
            if self.matched[i]:
                continue
            if note.type == "slide" and note.slide is not None:
                slide = note.slide
                path = slide.path
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
            if note.type in ("hold", "touch_hold") and note.end is not None:
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

    def _advance_slide(self, index: int, t: float) -> HitEvent:
        note = self.notes[index]
        assert note.slide is not None
        path = note.slide.path
        self.slide_next[index] += 1
        sensor = path[self.slide_next[index] - 1]
        stored = self.head_judgment[index] or "critical"
        stored_timing = self.head_timing[index]
        if self.slide_next[index] >= len(path):
            judgment: Judgment = stored
            timing: Timing | None = stored_timing
            if t > note.slide.end_t:
                judgment = "miss"
                timing = None
            self._apply(index, judgment)
            return HitEvent(
                t=t,
                button=note.button,
                judgment=judgment,
                note_index=index,
                sensor=sensor,
                timing=timing,
            )
        # Intermediate waypoint: report head judgment echo without scoring again.
        return HitEvent(
            t=t,
            button=note.button,
            judgment=stored,
            note_index=index,
            sensor=sensor,
            timing=None,
        )

    def _apply(self, index: int, judgment: Judgment) -> None:
        self.matched[index] = True
        base, bonus, dx = _judgment_points(self.notes[index], judgment)
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


def _late_window(note: Note) -> float:
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
    if late <= TOUCH_PERFECT:
        return "perfect", "late"
    if late <= TOUCH_GREAT:
        return "great", "late"
    if late <= TOUCH_GOOD:
        return "good", "late"
    return "miss", None
