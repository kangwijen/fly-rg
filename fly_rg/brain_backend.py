"""Real flybrain backend and a deterministic mock for demos without the connectome."""

from __future__ import annotations

from typing import Any, Protocol

from fly_rg.decoder import STEER_TYPES, TAP_TYPES
from fly_rg.encoder import CHASE_TYPES, DRIVE_KEYS, LOOM_TYPES, THREAT_TYPES


class BrainBackend(Protocol):
    def cells(self, types: list[str], side: str) -> Any: ...

    def step(self, inject: list | None = None) -> Any: ...


class RealBrain:
    """Thin wrapper around flybrain.FlyBrain."""

    def __init__(self, device: str = "auto"):
        from flybrain import FlyBrain

        self._brain = FlyBrain(device=device)
        self.dt = float(getattr(self._brain, "dt", 0.02))

    def cells(self, types: list[str], side: str) -> Any:
        return self._brain.cells(types, side=side)

    def step(self, inject: list | None = None) -> Any:
        return self._brain.step(inject=inject or [])


class MockBrain:
    """Deterministic pseudo-dynamics with the same cells/step surface.

    Stores last inject drive amounts for the mock decoder path. Spike indices
    are synthetic integers keyed by (type, side).
    """

    def __init__(self, seed: int = 0):
        self.dt = 0.02
        self.seed = seed
        self.last_inject: dict[str, float] = {}
        self._step_i = 0
        self._cell_ids: dict[tuple[str, str], list[int]] = {}
        self._next_id = 1
        # Pre-register readout / inject populations used by encoder/decoder.
        for side in ("L", "R"):
            for t in (*LOOM_TYPES, *THREAT_TYPES, *CHASE_TYPES, *STEER_TYPES, *TAP_TYPES):
                self.cells([t], side)

    def cells(self, types: list[str], side: str) -> list[int]:
        side_u = side.upper()
        out: list[int] = []
        for t in types:
            key = (t, side_u)
            if key not in self._cell_ids:
                # A few fake units per population.
                ids = [self._next_id + i for i in range(3)]
                self._next_id += 3
                self._cell_ids[key] = ids
            out.extend(self._cell_ids[key])
        return out

    def step(self, inject: list | None = None, drive: dict[str, float] | None = None) -> list[int]:
        """Return fake spike indices; stronger inject -> more spikes on that side."""
        self._step_i += 1
        if drive is not None:
            parsed = {k: float(drive.get(k, 0.0)) for k in DRIVE_KEYS}
        else:
            parsed = self._inject_to_drive(inject or [])
        self.last_inject = parsed
        drive = parsed
        fired: list[int] = []

        def maybe_fire(types: list[str], side: str, amount: float, rate: float) -> None:
            if amount <= 0:
                return
            idx = self.cells(types, side)
            # Deterministic: fire first k cells from amount.
            k = min(len(idx), max(1, int(amount * rate * len(idx))))
            fired.extend(idx[:k])

        maybe_fire(list(LOOM_TYPES), "L", drive.get("loomL", 0.0), 2.0)
        maybe_fire(list(LOOM_TYPES), "R", drive.get("loomR", 0.0), 2.0)
        maybe_fire(list(THREAT_TYPES), "L", drive.get("threatL", 0.0), 2.0)
        maybe_fire(list(THREAT_TYPES), "R", drive.get("threatR", 0.0), 2.0)
        maybe_fire(list(CHASE_TYPES), "L", drive.get("chaseL", 0.0), 2.0)
        maybe_fire(list(CHASE_TYPES), "R", drive.get("chaseR", 0.0), 2.0)

        def fire_dn_pool(types: tuple[str, ...], side: str, amount: float) -> None:
            if amount <= 0.05:
                return
            k = 1 + int(amount > 0.4)
            for t in types:
                fired.extend(self.cells([t], side)[:k])

        # Descending readout: steer and tap pools follow L/R visual drive.
        left = drive.get("loomL", 0.0) + drive.get("chaseL", 0.0) + drive.get("threatL", 0.0)
        right = drive.get("loomR", 0.0) + drive.get("chaseR", 0.0) + drive.get("threatR", 0.0)
        fire_dn_pool(STEER_TYPES, "L", left)
        fire_dn_pool(STEER_TYPES, "R", right)
        fire_dn_pool(TAP_TYPES, "L", left)
        fire_dn_pool(TAP_TYPES, "R", right)

        # Tiny spontaneous noise keyed by step for determinism.
        if (self._step_i + self.seed) % 17 == 0:
            fired.extend(self.cells(["DNa02"], "L")[:1])
        return fired

    def _inject_to_drive(self, inject: list) -> dict[str, float]:
        """Map inject list or a bare drive dict into loom/chase/threat L/R."""
        if not inject:
            return {k: 0.0 for k in DRIVE_KEYS}
        # Encoder mock path may pass nothing; play loop can set last_inject directly.
        if isinstance(inject, dict):
            return {k: float(inject.get(k, 0.0)) for k in DRIVE_KEYS}

        drive = {k: 0.0 for k in DRIVE_KEYS}
        # Real inject is [(cell_indices, amount), ...]. Recover channel by membership.
        for item in inject:
            if not isinstance(item, (tuple, list)) or len(item) != 2:
                continue
            indices, amount = item
            amount_f = float(amount)
            idx_set = set(int(x) for x in indices) if not isinstance(indices, (int, float)) else {int(indices)}
            for side in ("L", "R"):
                if idx_set & set(self.cells(list(LOOM_TYPES), side)):
                    drive[f"loom{side}"] = max(drive[f"loom{side}"], amount_f)
                if idx_set & set(self.cells(list(THREAT_TYPES), side)):
                    drive[f"threat{side}"] = max(drive[f"threat{side}"], amount_f)
                if idx_set & set(self.cells(list(CHASE_TYPES), side)):
                    drive[f"chase{side}"] = max(drive[f"chase{side}"], amount_f)
        return drive


def flybrain_available() -> bool:
    try:
        import flybrain  # noqa: F401

        return True
    except ImportError:
        return False


def make_brain(mock: bool = False, device: str = "auto") -> tuple[BrainBackend, bool]:
    """Return (brain, is_mock). Falls back to MockBrain if flybrain is missing."""
    if mock or not flybrain_available():
        return MockBrain(), True
    return RealBrain(device=device), False
