"""HeuristicStrategy: the rule-based AI opponent (the v2 headliner).

Each activation it enumerates every legal shot — eligible shooter x carried
ranged weapon x surviving enemy — scores each by expected damage, and takes
the best one. The score is `core.expected.expected_damage` capped at the
target's remaining total wounds, so a volley is never "spent" on more unit
than is left standing: ten expected damage into a one-wound survivor scores
one, and the fuller enemy unit wins instead.

Design notes:

- **Same math as the dice.** The estimator mirrors the combat pipeline's
  targets and keyword semantics and is tested against `resolve_shooting`'s
  Monte Carlo mean, honoring the promise in `strategies/base.py` that the AI
  scores actions with the combat math the engine resolves them with.
- **Deterministic.** Candidates are scored in snapshot order (scenario
  order) and only a strictly better score displaces the incumbent, so ties
  keep the earliest candidate and the same battlefield always produces the
  same action — the property every seeded test in this project leans on.
- **Greedy per activation.** Each `choose_action` call optimizes one shot in
  isolation; it does not plan which of its units should fire first. With
  every current weapon locked to a single target per volley that gap is
  cosmetic, but it is the first thing a smarter successor would revisit.
- **Loadout-aware for free.** Candidates come from
  `UnitSnapshot.ranged_weapons`, the same single definition the engine
  validates against, so the AI can never pick a gun a scenario's loadout
  override took away.
"""

from __future__ import annotations

from wh40k_tutorial.core.expected import expected_damage
from wh40k_tutorial.strategies.base import Action, GameState, UnitSnapshot


def _remaining_wounds(unit: UnitSnapshot) -> int:
    """Total wounds the unit can still lose: full trailing models + the lead."""
    if unit.destroyed:
        return 0
    return (unit.models - 1) * unit.datasheet.profile.wounds + unit.wounds_on_lead


class HeuristicStrategy:
    """Picks the legal shot with the highest capped expected damage."""

    def choose_action(self, state: GameState) -> Action:
        best_score = -1.0
        best: Action | None = None
        for shooter in state.eligible_shooters():
            for weapon in shooter.ranged_weapons:
                for target in state.surviving_enemies():
                    score = min(
                        expected_damage(shooter.models, weapon, target.datasheet.profile),
                        float(_remaining_wounds(target)),
                    )
                    if score > best_score:
                        best_score = score
                        best = Action(
                            kind="shoot",
                            attacker_unit_id=shooter.unit_id,
                            weapon_key=weapon.name,
                            target_unit_id=target.unit_id,
                        )
        if best is None:
            raise RuntimeError(
                "no legal shot available — the engine should not have asked "
                "for an action"
            )
        return best
