"""The scenario runner: the only place battlefield state mutates.

`run_scenario` walks a scenario's turn entries. Each entry is one shooting
phase for one side: every eligible unit on that side activates once, the
side's `Strategy` chooses each shot, `core.combat.resolve_shooting` resolves
it, and the result's final defender state (normal damage plus any mortal
wounds) updates the target's runtime state.

Boundaries (see ADR 0005):

- Datasheets stay frozen value types; `UnitRuntime` here carries the mutable
  state (models left, wounds on the lead model).
- Strategies see frozen `GameState` snapshots and return `Action`s — they can
  never touch engine state. The engine validates every returned action and
  raises `EngineError` on an illegal one, so a buggy script or AI fails
  loudly instead of corrupting the battle.
- Presentation observes through optional callbacks receiving frozen
  `VolleyEvent`s; the engine itself never prints.

v1 simplifications, on purpose: weapon range is not enforced (scenarios are
pre-positioned in range; range checks arrive with movement, which also fixes
the grid-squares-to-inches convention), and one activation fires one weapon
profile. A unit's shootable weapons are its effective loadout — the
scenario's per-unit loadout override if one is given, else the datasheet's
default_loadout (see `core.models.shootable_weapons`).
"""

from __future__ import annotations

import random
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from wh40k_tutorial.core.combat import ShootingResult, resolve_shooting
from wh40k_tutorial.core.models import UnitDatasheet, Weapon, shootable_weapons
from wh40k_tutorial.core.scenario import Scenario, ScenarioTurn, opposing_side
from wh40k_tutorial.strategies.base import Action, GameState, Strategy, UnitSnapshot


class EngineError(ValueError):
    """A strategy returned an action the rules of the battle don't allow."""


@dataclass
class UnitRuntime:
    """One unit's mutable battlefield state. Everything static lives on the datasheet."""

    unit_id: str
    side: str
    datasheet: UnitDatasheet
    position: tuple[int, int]
    models: int
    wounds_on_lead: int
    # The scenario's loadout override; empty = use the datasheet's default.
    loadout: tuple[str, ...] = ()

    @property
    def destroyed(self) -> bool:
        return self.models == 0

    def snapshot(self, *, has_shot: bool) -> UnitSnapshot:
        return UnitSnapshot(
            unit_id=self.unit_id,
            side=self.side,
            datasheet=self.datasheet,
            position=self.position,
            models=self.models,
            wounds_on_lead=self.wounds_on_lead,
            has_shot=has_shot,
            loadout=self.loadout,
        )


@dataclass
class BattleState:
    """The whole battlefield's mutable state, plus where we are in the scenario."""

    units: dict[str, UnitRuntime]  # insertion order = scenario order
    turn: int = 0
    phase: str = ""
    active_side: str = ""
    shot_this_phase: set[str] = field(default_factory=set)

    @classmethod
    def from_scenario(cls, scenario: Scenario) -> BattleState:
        units = {
            u.unit_id: UnitRuntime(
                unit_id=u.unit_id,
                side=side.name,
                datasheet=u.datasheet,
                position=u.position,
                models=u.models,
                wounds_on_lead=u.datasheet.profile.wounds,
                loadout=u.loadout,
            )
            for side in (scenario.attacker, scenario.defender)
            for u in side.units
        }
        return cls(units=units)

    def survivors(self, side: str) -> list[UnitRuntime]:
        return [u for u in self.units.values() if u.side == side and not u.destroyed]

    def side_wiped(self, side: str) -> bool:
        return not self.survivors(side)

    @property
    def battle_over(self) -> bool:
        return self.side_wiped("attacker") or self.side_wiped("defender")

    def snapshot(self) -> GameState:
        return GameState(
            turn=self.turn,
            phase=self.phase,
            active_side=self.active_side,
            units=tuple(
                u.snapshot(has_shot=u.unit_id in self.shot_this_phase)
                for u in self.units.values()
            ),
        )


@dataclass(frozen=True)
class VolleyEvent:
    """One resolved shooting action, handed to observers for display."""

    turn: int
    phase: str
    action: Action
    result: ShootingResult


def run_scenario(
    scenario: Scenario,
    strategies: Mapping[str, Strategy],
    *,
    rng: random.Random | None = None,
    on_turn_start: Callable[[int, ScenarioTurn], None] | None = None,
    on_volley: Callable[[VolleyEvent], None] | None = None,
) -> BattleState:
    """Play the scenario's turns and return the final battlefield state.

    ``strategies`` maps each side name to the `Strategy` that plays it; both
    "attacker" and "defender" must be present. ``rng`` is threaded into every
    dice roll for deterministic tests. The loop ends early the moment either
    side is wiped out.
    """
    for side in ("attacker", "defender"):
        if side not in strategies:
            raise EngineError(f"no strategy provided for the {side} side")
    dice = rng or random.Random()
    state = BattleState.from_scenario(scenario)

    for turn_number, turn in enumerate(scenario.turns, start=1):
        if state.battle_over:
            break
        state.turn = turn_number
        state.phase = turn.phase
        state.active_side = turn.active_side
        state.shot_this_phase = set()
        if on_turn_start is not None:
            on_turn_start(turn_number, turn)
        strategy = strategies[turn.active_side]

        while True:
            snap = state.snapshot()
            if not snap.eligible_shooters() or not snap.surviving_enemies():
                break
            action = strategy.choose_action(snap)
            attacker, weapon, target = _validate_action(action, state)
            result = resolve_shooting(
                attacker.datasheet,
                attacker.models,
                weapon,
                target.datasheet,
                target.wounds_on_lead,
                target.models,
                rng=dice,
            )
            target.models = result.models_remaining
            target.wounds_on_lead = result.wounds_remaining_on_lead
            state.shot_this_phase.add(attacker.unit_id)
            if on_volley is not None:
                on_volley(
                    VolleyEvent(turn=turn_number, phase=turn.phase, action=action, result=result)
                )
    return state


def _validate_action(
    action: Action, state: BattleState
) -> tuple[UnitRuntime, Weapon, UnitRuntime]:
    """Check a strategy's action against the battle rules; return the resolved pieces."""
    if action.kind != "shoot":
        raise EngineError(f"unknown action kind {action.kind!r} — v1 supports only 'shoot'")
    attacker = state.units.get(action.attacker_unit_id)
    if attacker is None:
        raise EngineError(f"no unit {action.attacker_unit_id!r} on the battlefield")
    if attacker.side != state.active_side:
        raise EngineError(
            f"{attacker.datasheet.display_name} ({attacker.unit_id!r}) belongs to the "
            f"{attacker.side}, who are not the active side"
        )
    if attacker.destroyed:
        raise EngineError(
            f"{attacker.datasheet.display_name} ({attacker.unit_id!r}) is destroyed "
            f"and cannot shoot"
        )
    if attacker.unit_id in state.shot_this_phase:
        raise EngineError(
            f"{attacker.datasheet.display_name} ({attacker.unit_id!r}) already shot "
            f"this phase — each unit shoots once per shooting phase"
        )
    weapon = next((w for w in attacker.datasheet.weapons if w.name == action.weapon_key), None)
    if weapon is None:
        raise EngineError(
            f"{attacker.datasheet.display_name} has no weapon {action.weapon_key!r}"
        )
    if weapon.type != "ranged":
        raise EngineError(
            f"{weapon.display_name} is a melee weapon and cannot be fired in the "
            f"shooting phase"
        )
    carried = {w.name for w in shootable_weapons(attacker.datasheet, attacker.loadout)}
    if weapon.name not in carried:
        raise EngineError(
            f"{attacker.datasheet.display_name} ({attacker.unit_id!r}) is not "
            f"carrying {weapon.display_name} in this scenario — its loadout is "
            f"{', '.join(sorted(carried))}"
        )
    target = state.units.get(action.target_unit_id)
    if target is None:
        raise EngineError(f"no unit {action.target_unit_id!r} on the battlefield")
    if target.side != opposing_side(state.active_side):
        raise EngineError(
            f"{target.datasheet.display_name} ({target.unit_id!r}) is on your own "
            f"side — shooting attacks target enemy units"
        )
    if target.destroyed:
        raise EngineError(
            f"{target.datasheet.display_name} ({target.unit_id!r}) is already "
            f"destroyed — pick a surviving target"
        )
    return attacker, weapon, target
