"""Timed chart JSON schema used by the play loop and WebSocket protocol."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, TypedDict

NoteType = Literal["tap", "hold"]


class NoteDict(TypedDict):
    t: float
    button: int
    type: NoteType
    end: float | None


class ChartDict(TypedDict):
    title: str
    artist: str
    offset: float
    notes: list[NoteDict]


@dataclass(frozen=True)
class Note:
    """A single timed note on buttons 1..8."""

    t: float
    button: int
    type: NoteType = "tap"
    end: float | None = None

    def to_dict(self) -> NoteDict:
        return {
            "t": float(self.t),
            "button": int(self.button),
            "type": self.type,
            "end": None if self.end is None else float(self.end),
        }


@dataclass
class Chart:
    """Timed chart: offset is seconds (Simai &first)."""

    title: str = ""
    artist: str = ""
    offset: float = 0.0
    notes: list[Note] = field(default_factory=list)

    def to_dict(self) -> ChartDict:
        return {
            "title": self.title,
            "artist": self.artist,
            "offset": float(self.offset),
            "notes": [n.to_dict() for n in self.notes],
        }

    @classmethod
    def from_dict(cls, data: ChartDict | dict) -> Chart:
        notes: list[Note] = []
        for raw in data.get("notes", []):
            notes.append(
                Note(
                    t=float(raw["t"]),
                    button=int(raw["button"]),
                    type=raw.get("type", "tap"),
                    end=None if raw.get("end") is None else float(raw["end"]),
                )
            )
        notes.sort(key=lambda n: (n.t, n.button))
        return cls(
            title=str(data.get("title", "")),
            artist=str(data.get("artist", "")),
            offset=float(data.get("offset", 0.0)),
            notes=notes,
        )

