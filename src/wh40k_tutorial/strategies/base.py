"""The Strategy protocol — the extension point for player input and AI opponents.

A Strategy is anything that, given the current game state, returns the next
action for a side. Three implementations are planned:

- HumanStrategy:     prompts the player via the CLI. The player IS the strategy.
- ScriptedStrategy:  replays a fixed sequence from the scenario file.
                     Used for the opponent in the teaching-ladder tutorials.
- HeuristicStrategy: picks the highest-expected-damage shot using the same
                     combat math the engine uses for dice resolution (the
                     estimator is Monte Carlo-tested against the pipeline).
                     Scenarios opt in with opponent_strategy: "heuristic".

The engine ONLY interacts with strategies through this protocol. Player input
logic does not leak into combat code. AI logic does not need to know how
the player decides things. This separation is what keeps the engine clean.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from wh40k_tutorial.core.models import UnitDatasheet, Weapon, melee_weapons, shootable_weapons
from wh40k_tutorial.core.scenario import in_engagement_range, opposing_side


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
    has_fought: bool = False  # already selected to fight in the current fight phase
    # The scenario's loadout override for this unit; empty means "use the
    # datasheet's default_loadout". Set by the engine from ScenarioUnit.loadout.
    loadout: tuple[str, ...] = ()

    @property
    def destroyed(self) -> bool:
        return self.models == 0

    @property
    def ranged_weapons(self) -> tuple[Weapon, ...]:
        """The weapons this unit may shoot with, in loadout order.

        Defers to `core.models.shootable_weapons` — the scenario's loadout
        override when one exists, otherwise the datasheet's ``default_loadout``
        (or every ranged weapon on a sheet that declares no loadout at all).
        """
        return shootable_weapons(self.datasheet, self.loadout)

    @property
    def melee_weapons(self) -> tuple[Weapon, ...]:
        """The weapons this unit may fight with (see `core.models.melee_weapons`)."""
        return melee_weapons(self.datasheet, self.loadout)


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

    def engaged_enemies(self, unit: UnitSnapshot) -> tuple[UnitSnapshot, ...]:
        """Surviving enemy units within engagement range of ``unit``.

        These are the only legal melee targets for it (04.02: a melee weapon
        must target a unit engaged with its bearer).
        """
        return tuple(
            u
            for u in self.units_on(opposing_side(unit.side))
            if not u.destroyed and in_engagement_range(unit.position, u.position)
        )

    def eligible_fighters(self, side: str) -> tuple[UnitSnapshot, ...]:
        """``side``'s units that can still be selected to fight this phase.

        Alive, engaged with at least one surviving enemy, armed with a melee
        weapon, and not yet selected to fight. The single definition of fight
        eligibility — the engine's alternation loop and the strategies' menus
        rely on it agreeing with itself. (The rulebook also lets a unit whose
        combat ended mid-phase fight via an *overrun* move; without movement
        there is nothing for such a unit to reach, so it is not offered.)
        """
        return tuple(
            u
            for u in self.units_on(side)
            if not u.destroyed
            and not u.has_fought
            and u.melee_weapons
            and self.engaged_enemies(u)
        )


@dataclass(frozen=True)
class Action:
    """An action a strategy can take.

    Two kinds exist: "shoot" (a shooting-phase volley) and "fight" (a
    fight-phase melee activation). Both are "this attacker attacks that
    target with that weapon", so one shape serves — a discriminated union
    earns its keep only once an action needs different fields (movement).
    """

    kind: str  # "shoot" or "fight"
    attacker_unit_id: str
    weapon_key: str
    target_unit_id: str


class Strategy(Protocol):
    """Anything that can choose actions for a side."""

    def choose_action(self, state: GameState) -> Action:
        """Return the next action for the active side, given the current state."""
        ...
