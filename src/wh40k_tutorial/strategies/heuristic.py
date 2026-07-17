"""HeuristicStrategy: the rule-based AI opponent (the v2 headliner).

Each activation it enumerates every legal action for the phase — in a
shooting phase, eligible shooter x carried ranged weapon x surviving enemy;
in a fight phase, eligible fighter x melee weapon x *engaged* enemy — scores
each by expected damage, and takes the best one. The score is
`core.expected.expected_damage` capped at the target's remaining total
wounds, so an attack is never "spent" on more unit than is left standing:
ten expected damage into a one-wound survivor scores one, and the fuller
enemy unit wins instead. The estimator never reads the weapon's type — WS
and BS are the same `skill` field — so one brain drives both phases.

Design notes:

- **Same math as the dice.** The estimator mirrors the combat pipeline's
  targets and keyword semantics and is tested against `resolve_shooting`'s
  Monte Carlo mean, honoring the promise in `strategies/base.py` that the AI
  scores actions with the combat math the engine resolves them with.
- **Deterministic.** Candidates are scored in snapshot order (scenario
  order) and only a strictly better score displaces the incumbent, so ties
  keep the earliest candidate and the same battlefield always produces the
  same action — the property every seeded test in this project leans on.
- **Greedy per activation.** Each `choose_action` call optimizes one action
  in isolation; it does not plan which of its units should act first. In a
  shooting phase that gap is cosmetic (every weapon locks to one target).
  In a fight phase greedy-per-pick *is* an ordering policy — the AI resolves
  its deadliest available fight first — but it does not anticipate the
  opponent's interleaved picks; that is the first thing a smarter successor
  would revisit.
- **Loadout-aware for free.** Candidates come from
  `UnitSnapshot.ranged_weapons` / `UnitSnapshot.melee_weapons`, the same
  single definitions the engine validates against, so the AI can never pick
  a weapon a scenario's loadout override took away — and it always keeps its
  melee arm, because overrides never disarm a unit in melee.
"""

from __future__ import annotations

from collections.abc import Iterable

from wh40k_tutorial.core.expected import expected_damage
from wh40k_tutorial.core.models import Weapon
from wh40k_tutorial.strategies.base import Action, GameState, UnitSnapshot


def _remaining_wounds(unit: UnitSnapshot) -> int:
    """Total wounds the unit can still lose: full trailing models + the lead."""
    if unit.destroyed:
        return 0
    return (unit.models - 1) * unit.datasheet.profile.wounds + unit.wounds_on_lead


class HeuristicStrategy:
    """Picks the legal action with the highest capped expected damage."""

    def choose_action(self, state: GameState) -> Action:
        if state.phase == "fight":
            candidates = (
                (fighter, weapon, target)
                for fighter in state.eligible_fighters(state.active_side)
                for weapon in fighter.melee_weapons
                for target in state.engaged_enemies(fighter)
            )
            return self._best(candidates, kind="fight")
        candidates = (
            (shooter, weapon, target)
            for shooter in state.eligible_shooters()
            for weapon in shooter.ranged_weapons
            for target in state.surviving_enemies()
        )
        return self._best(candidates, kind="shoot")

    def _best(
        self,
        candidates: Iterable[tuple[UnitSnapshot, Weapon, UnitSnapshot]],
        kind: str,
    ) -> Action:
        """The highest capped-expected-damage candidate, earliest on ties."""
        best_score = -1.0
        best: Action | None = None
        for attacker, weapon, target in candidates:
            score = min(
                expected_damage(attacker.models, weapon, target.datasheet.profile),
                float(_remaining_wounds(target)),
            )
            if score > best_score:
                best_score = score
                best = Action(
                    kind=kind,
                    attacker_unit_id=attacker.unit_id,
                    weapon_key=weapon.name,
                    target_unit_id=target.unit_id,
                )
        if best is None:
            raise RuntimeError(
                f"no legal {kind} available — the engine should not have asked "
                f"for an action"
            )
        return best
