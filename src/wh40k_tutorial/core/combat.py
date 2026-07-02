"""Combat resolution pipeline.

The shooting (and later, melee) sequence is a pipeline:

    attacks -> hits -> wounds -> saves -> damage

Each step is a pure function that consumes the previous step's record and
returns its own frozen record. `resolve_shooting` strings them together and
returns a `ShootingResult`: a structured, step-by-step account carrying the
raw dice faces and the facts that drove every target number, so the narrator
can explain each roll without re-deriving any rules (ADR 0001).

Phase-3 scope: no weapon keywords. The step records already carry the
generic hand-off fields the phase-4 hook framework will fill (e.g.
``HitStep.auto_wounds``), defaulting to "no ability" values so a keywordless
weapon flows through unchanged (ADR 0002).

TODO (later phases): keyword hooks (Sustained Hits, Lethal Hits, ...) and
``resolve_melee``, which will reuse ``_resolve_attack_sequence`` plus
engine-level fight ordering — a new caller, not a new pipeline shape.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from wh40k_tutorial.core.dice import RollResult, roll_d6, save_target, wound_target
from wh40k_tutorial.core.models import Profile, UnitDatasheet, Weapon


@dataclass(frozen=True)
class AttackStep:
    """The attack pool, before any dice are rolled.

    For a weapon with Attacks 2 fired by 5 models this is 10 attacks.
    Variable-attack weapons ("D6") are not supported yet — the loader
    rejects them (see docs/design/shooting-pipeline.md).
    """

    weapon: Weapon
    attacker_models: int
    attacks_per_model: int
    total_attacks: int


@dataclass(frozen=True)
class HitStep:
    """The hit roll. The target number is the weapon's skill (``roll.target``)."""

    roll: RollResult
    hits: int
    critical_hits: int  # natural 6s — the trigger for Sustained/Lethal/Dev Wounds
    # Carry field for phase-4 abilities (Lethal Hits): hits that skip the
    # wound roll and count directly as wounds. Saves still apply to them.
    auto_wounds: int = 0


@dataclass(frozen=True)
class WoundStep:
    """The wound roll. ``strength`` vs ``toughness`` set the target (wound chart)."""

    roll: RollResult
    strength: int
    toughness: int
    wounds: int           # successful wound rolls plus any carried auto-wounds
    critical_wounds: int  # natural 6s — the trigger for Devastating Wounds


@dataclass(frozen=True)
class SaveStep:
    """The saving throw, or the explicit no-save branch (ADR 0003).

    ``modified_target`` is the best save available: armour worsened by AP,
    or the invulnerable save if that is better. If it is 7 or worse, no save
    is possible: every wound fails and **no dice are rolled** — ``roll``
    carries empty tuples so the narrator still has a record to explain.
    """

    roll: RollResult
    armor_save: int
    ap: int
    invulnerable_save: int | None
    modified_target: int
    failed_saves: int

    @property
    def save_possible(self) -> bool:
        return self.modified_target <= 6


@dataclass(frozen=True)
class DamageStep:
    """Damage allocation: each failed save deals Damage to one model.

    A model is filled before the next is touched; excess damage on a slain
    model is lost and recorded as ``wasted_damage`` — the teachable overkill
    signal. Damage never spills between models. (Mortal wounds, which *do*
    spill, arrive with Devastating Wounds in a later phase on their own
    track — see ADR 0002 and CONTEXT.md.)
    """

    damage_per_failed_save: int
    damage_inflicted: int   # damage that actually removed wounds
    wasted_damage: int      # overkill lost on slain models (or a destroyed unit)
    models_slain: int
    models_remaining: int
    wounds_remaining_on_lead: int  # wounds left on the front model; 0 if unit destroyed


@dataclass(frozen=True)
class ShootingResult:
    """One weapon's worth of shooting, as a narratable record of facts."""

    attacker: UnitDatasheet
    defender: UnitDatasheet
    attack: AttackStep
    hit: HitStep
    wound: WoundStep
    save: SaveStep
    damage: DamageStep


def resolve_shooting(
    attacker: UnitDatasheet,
    attacker_model_count: int,
    weapon: Weapon,
    defender: UnitDatasheet,
    defender_wounds_remaining: int,
    defender_model_count: int,
    rng: random.Random | None = None,
) -> ShootingResult:
    """Resolve one ranged weapon profile fired by N identical models at one target unit.

    Mixed-weapon units are several calls made by the engine, so every die in
    a pool shares one target number. ``rng`` is threaded through to
    ``core.dice`` for deterministic tests.

    ``defender_wounds_remaining`` is the current wounds of the defender's
    *lead* model (may be below the profile's W if it was hurt earlier);
    the returned ``DamageStep`` reports the updated defender state so the
    engine can thread several weapons against one unit.
    """
    if weapon.type != "ranged":
        raise ValueError(f"resolve_shooting needs a ranged weapon, got {weapon.name!r} (melee)")
    if attacker_model_count < 0:
        raise ValueError(f"attacker_model_count must be >= 0, got {attacker_model_count}")
    if defender_model_count < 1:
        raise ValueError(f"defender_model_count must be >= 1, got {defender_model_count}")
    if not 1 <= defender_wounds_remaining <= defender.profile.wounds:
        raise ValueError(
            f"defender_wounds_remaining must be in 1..{defender.profile.wounds} "
            f"(the lead model's wounds), got {defender_wounds_remaining}"
        )
    return _resolve_attack_sequence(
        attacker,
        attacker_model_count,
        weapon,
        defender,
        defender_wounds_remaining,
        defender_model_count,
        rng or random.Random(),
    )


def _resolve_attack_sequence(
    attacker: UnitDatasheet,
    attacker_model_count: int,
    weapon: Weapon,
    defender: UnitDatasheet,
    defender_wounds_remaining: int,
    defender_model_count: int,
    rng: random.Random,
) -> ShootingResult:
    """The shared attacks -> hits -> wounds -> saves -> damage sequence.

    ``resolve_shooting`` is a thin wrapper over this; a future
    ``resolve_melee`` will call it too.
    """
    attack = AttackStep(
        weapon=weapon,
        attacker_models=attacker_model_count,
        attacks_per_model=weapon.attacks,
        total_attacks=attacker_model_count * weapon.attacks,
    )
    hit = _roll_hits(attack, rng)
    wound = _roll_wounds(hit, weapon.strength, defender.profile.toughness, rng)
    save = _roll_saves(wound.wounds, defender.profile, weapon.ap, rng)
    damage = _allocate_damage(
        failed_saves=save.failed_saves,
        damage=weapon.damage,
        wounds_per_model=defender.profile.wounds,
        wounds_on_lead=defender_wounds_remaining,
        model_count=defender_model_count,
    )
    return ShootingResult(
        attacker=attacker,
        defender=defender,
        attack=attack,
        hit=hit,
        wound=wound,
        save=save,
        damage=damage,
    )


def _roll_hits(attack: AttackStep, rng: random.Random) -> HitStep:
    roll = roll_d6(attack.total_attacks, target=attack.weapon.skill, rng=rng)
    return HitStep(roll=roll, hits=roll.successes, critical_hits=roll.critical_hits)


def _roll_wounds(hit: HitStep, strength: int, toughness: int, rng: random.Random) -> WoundStep:
    # Normal hits roll to wound; carried auto-wounds (phase 4, Lethal Hits)
    # are added on top without a roll — the step never needs to know which
    # ability sent them (ADR 0002).
    normal_hits = hit.hits - hit.auto_wounds
    roll = roll_d6(normal_hits, target=wound_target(strength, toughness), rng=rng)
    return WoundStep(
        roll=roll,
        strength=strength,
        toughness=toughness,
        wounds=roll.successes + hit.auto_wounds,
        critical_wounds=roll.critical_hits,
    )


def _roll_saves(wounds: int, profile: Profile, ap: int, rng: random.Random) -> SaveStep:
    target = save_target(profile.save, ap, profile.invulnerable_save)
    if target > 6:
        # No save possible (ADR 0003): every wound fails, no dice are rolled.
        empty = RollResult(rolls=(), raw_rolls=(), target=target, modifier=0, reroll="none")
        return SaveStep(
            roll=empty,
            armor_save=profile.save,
            ap=ap,
            invulnerable_save=profile.invulnerable_save,
            modified_target=target,
            failed_saves=wounds,
        )
    roll = roll_d6(wounds, target=target, rng=rng)
    return SaveStep(
        roll=roll,
        armor_save=profile.save,
        ap=ap,
        invulnerable_save=profile.invulnerable_save,
        modified_target=target,
        failed_saves=wounds - roll.successes,
    )


def _allocate_damage(
    *,
    failed_saves: int,
    damage: int,
    wounds_per_model: int,
    wounds_on_lead: int,
    model_count: int,
) -> DamageStep:
    """Allocate damage one failed save at a time, filling a model before the next.

    Excess damage on a model that dies is wasted, never carried to the next
    model. Failed saves against an already-destroyed unit are also recorded
    as wasted — the "your volley was bigger than the target" teaching signal.
    """
    models_left = model_count
    current = wounds_on_lead if models_left > 0 else 0
    inflicted = wasted = slain = 0
    for _ in range(failed_saves):
        if models_left == 0:
            wasted += damage
            continue
        applied = min(damage, current)
        inflicted += applied
        wasted += damage - applied
        current -= applied
        if current == 0:
            slain += 1
            models_left -= 1
            current = wounds_per_model if models_left > 0 else 0
    return DamageStep(
        damage_per_failed_save=damage,
        damage_inflicted=inflicted,
        wasted_damage=wasted,
        models_slain=slain,
        models_remaining=models_left,
        wounds_remaining_on_lead=current,
    )
