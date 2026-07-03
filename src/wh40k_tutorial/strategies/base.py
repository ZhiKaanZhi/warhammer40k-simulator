"""The Strategy protocol — the extension point for player input and AI opponents.

A Strategy is anything that, given the current game state, returns the next
action for a side. Three implementations are planned:

- HumanStrategy:     prompts the player via the CLI. The player IS the strategy.
- ScriptedStrategy:  replays a fixed sequence from the scenario file.
                     Used for the AI side in v1 tutorials.
- HeuristicStrategy: (v2) picks the highest-EV action using the same combat
                     math the engine uses for dice resolution.

The engine ONLY interacts with strategies through this protocol. Player input
logic does not leak into combat code. AI logic does not need to know how
the player decides things. This separation is what keeps the engine clean.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from wh40k_tutorial.core.models import UnitDatasheet, Weapon
from wh40k_tutorial.core.scenario import opposing_side


@dataclass(frozen=True)
class UnitSnapshot:
    """One unit's battlefield state, frozen at decision time.

    The engine builds these from its mutable runtime state; strategies only
    ever see (and can never corrupt) an immutable snapshot.
    """

    unit_id: str
    side: str  # "attacker" or "defender"
    datasheet: UnitDatasheet
    position: tuple[int, int]
    models: int              # models still standing
    wounds_on_lead: int      # wounds left on the front model; 0 once destroyed
    has_shot: bool = False   # already activated in the current shooting phase

    @property
    def destroyed(self) -> bool:
        return self.models == 0

    @property
    def ranged_weapons(self) -> tuple[Weapon, ...]:
        """The weapons this unit may shoot with, default loadout first.

        v1 loadouts cover the whole unit, so the shootable weapons are the
        ranged entries of ``default_loadout`` — or every ranged weapon if the
        datasheet declares no loadout.
        """
        by_key = {w.name: w for w in self.datasheet.weapons}
        chosen = [
            by_key[key]
            for key in self.datasheet.default_loadout
            if by_key[key].type == "ranged"
        ]
        if chosen:
            return tuple(chosen)
        return tuple(w for w in self.datasheet.weapons if w.type == "ranged")


@dataclass(frozen=True)
class GameState:
    """Snapshot of the battlefield at decision time."""

    turn: int
    phase: str
    active_side: str  # "attacker" or "defender"
    units: tuple[UnitSnapshot, ...] = ()

    def unit(self, unit_id: str) -> UnitSnapshot:
        for u in self.units:
            if u.unit_id == unit_id:
                return u
        raise KeyError(f"no unit {unit_id!r} on the battlefield")

    def units_on(self, side: str) -> tuple[UnitSnapshot, ...]:
        return tuple(u for u in self.units if u.side == side)

    def eligible_shooters(self) -> tuple[UnitSnapshot, ...]:
        """Active-side units that can still shoot this phase.

        Alive, armed with at least one ranged weapon, and not yet activated.
        This is the single definition of shooting eligibility — the engine's
        turn loop and both strategies rely on it agreeing with itself.
        """
        return tuple(
            u
            for u in self.units_on(self.active_side)
            if not u.destroyed and not u.has_shot and u.ranged_weapons
        )

    def surviving_enemies(self) -> tuple[UnitSnapshot, ...]:
        """Units of the non-active side that are still on the table."""
        return tuple(
            u for u in self.units_on(opposing_side(self.active_side)) if not u.destroyed
        )


@dataclass(frozen=True)
class Action:
    """An action a strategy can take.

    v1 only models the shooting phase, so for now an Action is "this attacker
    shoots that target with that weapon". Future phases (movement, charge,
    fight) will add Action subclasses or a discriminated union.

    TODO: replace with a proper discriminated union once we have more actions.
    """

    kind: str  # "shoot" for v1
    attacker_unit_id: str
    weapon_key: str
    target_unit_id: str


class Strategy(Protocol):
    """Anything that can choose actions for a side."""

    def choose_action(self, state: GameState) -> Action:
        """Return the next action for the active side, given the current state."""
        ...
