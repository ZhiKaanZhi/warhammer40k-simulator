"""Combat resolution pipeline.

The shooting (and later, melee) sequence is modeled as a pipeline:

    attacks  ->  hits  ->  wounds  ->  saves  ->  damage  ->  casualties

Each step is a pure function. Each keyword ability hooks into the relevant
step. Adding "Sustained Hits 1" should mean writing a small function that
inspects the hit-roll result and adds extra hits — never editing a giant
match/if-elif tree.

This file is a STUB. The pipeline shape below is the architecture commitment.
Implementations go inside each function as we work through the build phases
in CLAUDE.md.

TODO: implement `resolve_shooting` end-to-end with no keywords (phase 3).
TODO: add `resolve_melee` which reuses the same pipeline plus a fight-first step.
TODO: implement keyword hooks one at a time (phase 4).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from wh40k_tutorial.core.dice import RollResult
    from wh40k_tutorial.core.models import UnitDatasheet, Weapon


@dataclass(frozen=True)
class AttackStep:
    """Result of computing the attack pool (before any dice are rolled).

    For a weapon with Attacks=2 fired by 5 models, this is 10 attacks.
    Variable-attack weapons (D6, D6+1) resolve into a concrete number here.
    """

    weapon: Weapon
    attacker_models: int
    total_attacks: int


@dataclass(frozen=True)
class HitStep:
    """Result of the hit-roll phase."""

    roll: RollResult
    hits: int
    critical_hits: int  # natural 6s, relevant for Sustained/Lethal/DevWounds


@dataclass(frozen=True)
class WoundStep:
    """Result of the wound-roll phase."""

    roll: RollResult
    wounds: int


@dataclass(frozen=True)
class SaveStep:
    """Result of the armor/invuln save phase."""

    roll: RollResult
    failed_saves: int


@dataclass(frozen=True)
class DamageStep:
    """Final outcome: how many models died and any wound spillover."""

    damage_per_failed_save: int
    total_damage: int
    models_slain: int
    leftover_wounds_on_model: int  # damage allocated to a model that survived


@dataclass(frozen=True)
class ShootingResult:
    """The full record of one weapon's worth of shooting, suitable for narration."""

    attack: AttackStep
    hit: HitStep
    wound: WoundStep
    save: SaveStep
    damage: DamageStep


# TODO: implement
def resolve_shooting(
    attacker: UnitDatasheet,
    attacker_model_count: int,
    weapon: Weapon,
    defender: UnitDatasheet,
    defender_wounds_remaining: int,
    defender_model_count: int,
) -> ShootingResult:
    """Run one weapon's shooting attack from attacker to defender.

    This is the function the engine calls for each shooting action.
    The narrator consumes the returned `ShootingResult` to describe what
    happened, step by step, with the rule that determined each step.

    Implementation outline:
      1. compute AttackStep:    attacker_model_count * weapon.attacks
      2. compute HitStep:        dice.roll_d6(total_attacks, target=weapon.skill)
      3. compute WoundStep:      dice.roll_d6(hits, target=dice.wound_target(S, T))
      4. compute SaveStep:       dice.roll_d6(wounds, target=dice.save_target(Sv, AP, Inv))
      5. compute DamageStep:     failed_saves * weapon.damage, allocated to models

    For v1 we ignore keywords — implement those one at a time in phase 4.
    """
    raise NotImplementedError("TODO: implement shooting pipeline")
