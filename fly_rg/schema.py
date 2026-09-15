"""Timed chart JSON schema used by the play loop and WebSocket protocol."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, TypedDict

from fly_rg.sensors import button_to_sensor, format_sensor, parse_sensor

NoteType = Literal["tap", "hold", "touch", "touch_hold", "slide"]


class SlideDict(TypedDict):
    shape: str
    end_sensor: str
    path: list[str]
    end_t: float


class NoteDict(TypedDict, total=False):
    t: float
    type: NoteType
    sensor: str
    button: int | None
    end: float | None
    slide: SlideDict | None


class ChartDict(TypedDict):
    title: str
    artist: str
    offset: float
    notes: list[NoteDict]


@dataclass(frozen=True)
class SlideInfo:
    """Slide body: shape, expanded sensor path, and arrival time."""

    shape: str
    end_sensor: str
    path: tuple[str, ...]
    end_t: float

    def to_dict(self) -> SlideDict:
        return {
            "shape": self.shape,
            "end_sensor": self.end_sensor,
            "path": list(self.path),
            "end_t": float(self.end_t),
        }

    @classmethod
    def from_dict(cls, data: SlideDict | dict) -> SlideInfo:
        path = data.get("path") or []
        return cls(
            shape=str(data["shape"]),
            end_sensor=str(data["end_sensor"]),
            path=tuple(str(s) for s in path),
            end_t=float(data["end_t"]),
        )


def _button_from_sensor(sensor: str) -> int | None:
    area, idx = parse_sensor(sensor)
    if area == "A" and 1 <= idx <= 8:
        return idx
    return None


@dataclass(frozen=True)
class Note:
    """A timed note targeting a DX sensor (taps keep button 1..8)."""

    t: float
    button: int | None = None
    type: NoteType = "tap"
    end: float | None = None
    sensor: str = ""
    slide: SlideInfo | None = None

    def __post_init__(self) -> None:
        sensor = self.sensor.strip() if self.sensor else ""
        button = self.button
        if not sensor:
            if button is None:
                raise ValueError("Note requires sensor or button")
            sensor = button_to_sensor(int(button))
            object.__setattr__(self, "sensor", sensor)
        else:
            # Canonicalize (e.g. c1 -> C).
            area, idx = parse_sensor(sensor)
            sensor = format_sensor(area, idx)
            object.__setattr__(self, "sensor", sensor)
            if button is None:
                object.__setattr__(self, "button", _button_from_sensor(sensor))

    def to_dict(self) -> NoteDict:
        out: NoteDict = {
            "t": float(self.t),
            "type": self.type,
            "sensor": self.sensor,
            "button": None if self.button is None else int(self.button),
            "end": None if self.end is None else float(self.end),
            "slide": None if self.slide is None else self.slide.to_dict(),
        }
        return out


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
            slide_raw = raw.get("slide")
            slide = None if slide_raw is None else SlideInfo.from_dict(slide_raw)
            button_raw = raw.get("button")
            sensor_raw = raw.get("sensor")
            notes.append(
                Note(
                    t=float(raw["t"]),
                    button=None if button_raw is None else int(button_raw),
                    type=raw.get("type", "tap"),
                    end=None if raw.get("end") is None else float(raw["end"]),
                    sensor="" if sensor_raw is None else str(sensor_raw),
                    slide=slide,
                )
            )
        notes.sort(key=lambda n: (n.t, n.sensor, n.button or 0))
        return cls(
            title=str(data.get("title", "")),
            artist=str(data.get("artist", "")),
            offset=float(data.get("offset", 0.0)),
            notes=notes,
        )
