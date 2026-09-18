"""Timed chart JSON schema used by the play loop and WebSocket protocol."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, TypedDict

from fly_rg.sensors import button_to_sensor, format_sensor, parse_sensor

NoteType = Literal["tap", "hold", "touch", "touch_hold", "slide"]
HeadStyle = Literal["normal", "star", "tap", "fade", "sudden"]


class SlideDict(TypedDict, total=False):
    shape: str
    end_sensor: str
    path: list[str]
    end_t: float
    wait_t: float
    mid: int | None


class NoteDict(TypedDict, total=False):
    t: float
    type: NoteType
    sensor: str
    button: int | None
    end: float | None
    slide: SlideDict | None
    is_break: bool
    is_ex: bool
    is_mine: bool
    is_hanabi: bool
    is_star: bool
    is_each: bool
    head_style: HeadStyle


class ChartDict(TypedDict):
    title: str
    artist: str
    offset: float
    notes: list[NoteDict]


@dataclass(frozen=True)
class SlideInfo:
    """Slide body: shape, expanded sensor path, wait/arrival times."""

    shape: str
    end_sensor: str
    path: tuple[str, ...]
    end_t: float
    wait_t: float = 0.0
    mid: int | None = None

    def to_dict(self) -> SlideDict:
        out: SlideDict = {
            "shape": self.shape,
            "end_sensor": self.end_sensor,
            "path": list(self.path),
            "end_t": float(self.end_t),
            "wait_t": float(self.wait_t),
        }
        if self.mid is not None:
            out["mid"] = int(self.mid)
        return out

    @classmethod
    def from_dict(cls, data: SlideDict | dict) -> SlideInfo:
        path = data.get("path") or []
        mid_raw = data.get("mid")
        end_raw = data["end_t"]
        if not isinstance(end_raw, (int, float, str)) or isinstance(end_raw, bool):
            raise TypeError("end_t must be numeric")
        wait_raw = data.get("wait_t")
        if wait_raw is None:
            t_raw = data.get("t", 0.0)
            wait_raw = t_raw or 0.0
        if not isinstance(wait_raw, (int, float, str)) or isinstance(wait_raw, bool):
            wait_raw = 0.0
        return cls(
            shape=str(data["shape"]),
            end_sensor=str(data["end_sensor"]),
            path=tuple(str(s) for s in path),
            end_t=float(end_raw),
            wait_t=float(wait_raw),
            mid=None if mid_raw is None else int(mid_raw),
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
    is_break: bool = False
    is_ex: bool = False
    is_mine: bool = False
    is_hanabi: bool = False
    is_star: bool = False
    is_each: bool = False
    head_style: HeadStyle = "normal"

    def __post_init__(self) -> None:
        sensor = self.sensor.strip() if self.sensor else ""
        button = self.button
        if not sensor:
            if button is None:
                raise ValueError("Note requires sensor or button")
            sensor = button_to_sensor(int(button))
            object.__setattr__(self, "sensor", sensor)
        else:
            area, idx = parse_sensor(sensor)
            sensor = format_sensor(area, idx)
            object.__setattr__(self, "sensor", sensor)
            if button is None:
                object.__setattr__(self, "button", _button_from_sensor(sensor))

    def to_dict(self) -> NoteDict:
        return {
            "t": float(self.t),
            "type": self.type,
            "sensor": self.sensor,
            "button": None if self.button is None else int(self.button),
            "end": None if self.end is None else float(self.end),
            "slide": None if self.slide is None else self.slide.to_dict(),
            "is_break": bool(self.is_break),
            "is_ex": bool(self.is_ex),
            "is_mine": bool(self.is_mine),
            "is_hanabi": bool(self.is_hanabi),
            "is_star": bool(self.is_star),
            "is_each": bool(self.is_each),
            "head_style": self.head_style,
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
            slide_raw = raw.get("slide")
            slide = None if slide_raw is None else SlideInfo.from_dict(slide_raw)
            button_raw = raw.get("button")
            sensor_raw = raw.get("sensor")
            head = str(raw.get("head_style") or "normal")
            if head not in ("normal", "star", "tap", "fade", "sudden"):
                head = "normal"
            end_raw = raw.get("end")
            if end_raw is None:
                end = None
            elif isinstance(end_raw, (int, float, str)) and not isinstance(end_raw, bool):
                end = float(end_raw)
            else:
                raise TypeError("end must be numeric")
            notes.append(
                Note(
                    t=float(raw["t"]),
                    button=None if button_raw is None else int(button_raw),
                    type=raw.get("type", "tap"),
                    end=end,
                    sensor="" if sensor_raw is None else str(sensor_raw),
                    slide=slide,
                    is_break=bool(raw.get("is_break", False)),
                    is_ex=bool(raw.get("is_ex", False)),
                    is_mine=bool(raw.get("is_mine", False)),
                    is_hanabi=bool(raw.get("is_hanabi", False)),
                    is_star=bool(raw.get("is_star", False)),
                    is_each=bool(raw.get("is_each", False)),
                    head_style=head,  # type: ignore[arg-type]
                )
            )
        notes.sort(key=lambda n: (n.t, n.sensor, n.button or 0))
        return cls(
            title=str(data.get("title", "")),
            artist=str(data.get("artist", "")),
            offset=float(data.get("offset", 0.0)),
            notes=notes,
        )
