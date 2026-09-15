"""Judgment windows, combo, and score tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Never

from fly_rg.schema import Note

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
    button: int
    judgment: Judgment
    note_index: int


@dataclass
class Judge:
    """Match presses to nearest unmatched notes; auto-miss past the Good window."""

    notes: list[Note]
    matched: list[bool] = field(init=False)
    score: Score = field(default_factory=Score)

    def __post_init__(self) -> None:
        self.matched = [False] * len(self.notes)

    def press(self, button: int, t: float) -> HitEvent | None:
        """On press, match nearest unmatched note on that button within Good."""
        best_i: int | None = None
        best_abs = GOOD + 1.0
        for i, note in enumerate(self.notes):
            if self.matched[i] or note.button != button:
                continue
            dt = abs(note.t - t)
            if dt <= GOOD and dt < best_abs:
                best_abs = dt
                best_i = i
        if best_i is None:
            return None
        judgment = _window_judgment(self.notes[best_i].t - t)
        self._apply(best_i, judgment)
        return HitEvent(t=t, button=button, judgment=judgment, note_index=best_i)

    def auto_miss(self, now: float) -> list[HitEvent]:
        """Mark notes past the Good window as Miss."""
        events: list[HitEvent] = []
        for i, note in enumerate(self.notes):
            if self.matched[i]:
                continue
            if now - note.t > GOOD:
                self._apply(i, "miss")
                events.append(HitEvent(t=note.t, button=note.button, judgment="miss", note_index=i))
        return events

    def active_notes(self, now: float, look_ahead_s: float) -> list[dict]:
        """Notes still approaching for the state payload (progress 0..1 toward hit)."""
        active: list[dict] = []
        for i, note in enumerate(self.notes):
            if self.matched[i]:
                continue
            tth = note.t - now
            if tth < -GOOD or tth > look_ahead_s:
                continue
            if look_ahead_s <= 0:
                progress = 1.0
            else:
                progress = max(0.0, min(1.0, 1.0 - tth / look_ahead_s))
            active.append({"t": note.t, "button": note.button, "progress": progress})
        return active

    def done(self) -> bool:
        return all(self.matched)

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
