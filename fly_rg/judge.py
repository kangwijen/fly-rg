"""Judgment windows, combo, and score tracking (sensor-based)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Never

from fly_rg.schema import Note
from fly_rg.sensors import button_to_sensor

Judgment = Literal["perfect", "great", "good", "miss"]

PERFECT = 0.033
GREAT = 0.066
GOOD = 0.1


@dataclass
class Score:
    combo: int = 0
    perfect: int = 0
    great: int = 0
    good: int = 0
    miss: int = 0

    @property
    def judged(self) -> int:
        return self.perfect + self.great + self.good + self.miss

    @property
    def accuracy(self) -> float:
        total = self.judged
        if total == 0:
            return 1.0
        points = self.perfect * 1.0 + self.great * 0.8 + self.good * 0.5
        return points / total

    def to_dict(self) -> dict:
        return {
            "combo": self.combo,
            "perfect": self.perfect,
            "great": self.great,
            "good": self.good,
            "miss": self.miss,
            "accuracy": float(self.accuracy),
        }


@dataclass
class HitEvent:
    t: float
    button: int | None
    judgment: Judgment
    note_index: int
    sensor: str


@dataclass
class Judge:
    """Match presses to sensors; slides advance through path before end_t."""

    notes: list[Note]
    matched: list[bool] = field(init=False)
    # Next path index required for slides (0 = waiting for head / path[0]).
    slide_next: list[int] = field(init=False)
    head_judgment: list[Judgment | None] = field(init=False)
    score: Score = field(default_factory=Score)

    def __post_init__(self) -> None:
        n = len(self.notes)
        self.matched = [False] * n
        self.slide_next = [0] * n
        self.head_judgment = [None] * n

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

        # Match head / single-hit notes by sensor within Good of note.t.
        best_i: int | None = None
        best_abs = GOOD + 1.0
        for i, note in enumerate(self.notes):
            if self.matched[i]:
                continue
            target = self._head_sensor(note)
            if target != sensor:
                continue
            if note.type == "slide" and self.slide_next[i] > 0:
                continue
            dt = abs(note.t - t)
            if dt <= GOOD and dt < best_abs:
                best_abs = dt
                best_i = i
        if best_i is None:
            return None

        note = self.notes[best_i]
        judgment = _window_judgment(note.t - t)
        if note.type == "slide" and note.slide is not None:
            self.slide_next[best_i] = 1
            self.head_judgment[best_i] = judgment
            if len(note.slide.path) <= 1:
                self._apply(best_i, judgment)
                return HitEvent(
                    t=t,
                    button=note.button,
                    judgment=judgment,
                    note_index=best_i,
                    sensor=sensor,
                )
            # Head accepted; body still in progress (not a final score event yet).
            return HitEvent(
                t=t,
                button=note.button,
                judgment=judgment,
                note_index=best_i,
                sensor=sensor,
            )

        self._apply(best_i, judgment)
        return HitEvent(
            t=t,
            button=note.button,
            judgment=judgment,
            note_index=best_i,
            sensor=sensor,
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
            # Holds stay visible until release end.
            if note.type in ("hold", "touch_hold") and note.end is not None:
                if now > note.end + GOOD:
                    continue
                if now < note.t - look_ahead_s:
                    continue
                if now < note.t:
                    progress = (
                        0.0
                        if look_ahead_s <= 0
                        else max(0.0, min(1.0, 1.0 - (note.t - now) / look_ahead_s))
                    )
                else:
                    span = max(note.end - note.t, 1e-6)
                    progress = max(0.0, min(1.0, (now - note.t) / span))
                active.append(self._note_payload(note, note.sensor, progress))
                continue

            if tth < -GOOD or tth > look_ahead_s:
                continue
            if look_ahead_s <= 0:
                progress = 1.0
            else:
                progress = max(0.0, min(1.0, 1.0 - tth / look_ahead_s))
            active.append(
                self._note_payload(note, self._current_sensor(note, i), progress)
            )
        return active

    def _note_payload(self, note: Note, sensor: str, progress: float) -> dict:
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
        if self.slide_next[index] >= len(path):
            judgment = self.head_judgment[index] or "perfect"
            if t > note.slide.end_t:
                judgment = "miss"
            self._apply(index, judgment)
            return HitEvent(
                t=t,
                button=note.button,
                judgment=judgment,
                note_index=index,
                sensor=sensor,
            )
        # Intermediate waypoint: report head judgment echo without scoring again.
        judgment = self.head_judgment[index] or "perfect"
        return HitEvent(
            t=t,
            button=note.button,
            judgment=judgment,
            note_index=index,
            sensor=sensor,
        )

    def _apply(self, index: int, judgment: Judgment) -> None:
        self.matched[index] = True
        if judgment == "perfect":
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


def _window_judgment(delta: float) -> Judgment:
    """delta = note.t - press.t; uses absolute timing error."""
    err = abs(delta)
    if err <= PERFECT:
        return "perfect"
    if err <= GREAT:
        return "great"
    if err <= GOOD:
        return "good"
    return "miss"
