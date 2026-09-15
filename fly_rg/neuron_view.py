"""Display neuron layout and spike packing for the brain viz panel."""

from __future__ import annotations

import math
import random
from typing import Any


# Population regions in normalized brain outline coords (0..1).
_REGIONS: dict[str, tuple[float, float, float, float]] = {
    # name: (cx, cy, rx, ry)
    "loomL": (0.28, 0.32, 0.10, 0.08),
    "loomR": (0.72, 0.32, 0.10, 0.08),
    "threatL": (0.30, 0.42, 0.09, 0.07),
    "threatR": (0.70, 0.42, 0.09, 0.07),
    "chaseL": (0.34, 0.52, 0.09, 0.07),
    "chaseR": (0.66, 0.52, 0.09, 0.07),
    "dna02L": (0.38, 0.72, 0.07, 0.06),
    "dna02R": (0.62, 0.72, 0.07, 0.06),
    "dnp01L": (0.44, 0.82, 0.06, 0.05),
    "dnp01R": (0.56, 0.82, 0.06, 0.05),
    "other": (0.50, 0.48, 0.28, 0.28),
}


class NeuronAtlas:
    """Fixed layout of display neurons + helpers to pick which ones flash."""

    def __init__(self, n: int = 720, seed: int = 7):
        rng = random.Random(seed)
        self.n = n
        self.x: list[float] = []
        self.y: list[float] = []
        self.groups: dict[str, list[int]] = {k: [] for k in _REGIONS}
        # Fill background "other" first, then densify labeled regions.
        for i in range(n):
            if i < int(n * 0.55):
                key = "other"
            else:
                keys = [k for k in _REGIONS if k != "other"]
                key = keys[i % len(keys)]
            cx, cy, rx, ry = _REGIONS[key]
            # Rejection sample inside ellipse / soft brain oval.
            for _ in range(24):
                a = rng.random() * math.tau
                r = math.sqrt(rng.random())
                px = cx + math.cos(a) * rx * r
                py = cy + math.sin(a) * ry * r
                if self._in_brain(px, py):
                    break
            else:
                px, py = cx, cy
            self.x.append(round(px, 4))
            self.y.append(round(py, 4))
            self.groups[key].append(i)

    @staticmethod
    def _in_brain(px: float, py: float) -> bool:
        # Soft oval centered slightly high (optic lobes wide).
        dx = (px - 0.5) / 0.42
        dy = (py - 0.48) / 0.40
        return dx * dx + dy * dy <= 1.0

    def layout_message(self) -> dict[str, Any]:
        return {
            "type": "brain_layout",
            "neurons": self.n,
            "x": self.x,
            "y": self.y,
            "groups": self.groups,
            "labels": {
                "loomL": "LPLC2 L",
                "loomR": "LPLC2 R",
                "threatL": "LC4 L",
                "threatR": "LC4 R",
                "chaseL": "LC10a L",
                "chaseR": "LC10a R",
                "dna02L": "DNa02 L",
                "dna02R": "DNa02 R",
                "dnp01L": "DNp01 L",
                "dnp01R": "DNp01 R",
            },
        }

    def spikes_for(
        self,
        drive: dict[str, float],
        *,
        aim: float = 0.0,
        strike: float = 0.0,
        strike_l: float | None = None,
        strike_r: float | None = None,
        fired_count: int = 0,
        step: int = 0,
    ) -> list[int]:
        """Pick display neurons to flash this frame from drive + motor state."""
        rng = random.Random((step * 9973) ^ fired_count)
        out: list[int] = []
        tap_l = strike if strike_l is None else strike_l
        tap_r = strike if strike_r is None else strike_r

        def take(group: str, amount: float, scale: float = 48.0) -> None:
            ids = self.groups.get(group) or []
            if not ids or amount <= 0:
                return
            k = min(len(ids), max(1, int(amount * scale)))
            # Deterministic sliding window + a few random extras.
            start = (step * 3) % max(1, len(ids))
            for j in range(k):
                out.append(ids[(start + j) % len(ids)])
            extras = 1 + int(amount > 0.4) + int(amount > 0.75)
            if amount > 0.15 and ids:
                for _ in range(extras):
                    out.append(ids[rng.randrange(len(ids))])

        take("loomL", drive.get("loomL", 0.0))
        take("loomR", drive.get("loomR", 0.0))
        take("threatL", drive.get("threatL", 0.0))
        take("threatR", drive.get("threatR", 0.0))
        take("chaseL", drive.get("chaseL", 0.0), scale=52.0)
        take("chaseR", drive.get("chaseR", 0.0), scale=52.0)

        take(
            "dna02L",
            max(-aim, 0.0) + drive.get("chaseL", 0.0) + drive.get("loomL", 0.0),
            scale=52.0,
        )
        take(
            "dna02R",
            max(aim, 0.0) + drive.get("chaseR", 0.0) + drive.get("loomR", 0.0),
            scale=52.0,
        )
        take("dnp01L", tap_l + drive.get("threatL", 0.0), scale=56.0)
        take("dnp01R", tap_r + drive.get("threatR", 0.0), scale=56.0)

        # Background chatter scales with how many real cells fired this step.
        other = self.groups.get("other") or []
        if other:
            chatter = 12 + min(72, max(0, fired_count))
            start = step % len(other)
            for j in range(chatter):
                out.append(other[(start + j * 11) % len(other)])

        # Unique preserve order
        seen: set[int] = set()
        uniq: list[int] = []
        for i in out:
            if i not in seen:
                seen.add(i)
                uniq.append(i)
        return uniq
