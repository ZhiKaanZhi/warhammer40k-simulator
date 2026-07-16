"""Combat resolution pipeline.

The attack sequence — shared by shooting and melee — is a pipeline:

    attacks -> hits -> wounds -> saves -> damage -> mortal wounds

Each step is a pure function that consumes the previous step's record and
returns its own frozen record. `resolve_shooting` and `resolve_melee` are
thin entry points over the shared `_resolve_attack_sequence`; both return an
`AttackResult`: a structured, step-by-step account carrying the
raw dice faces and the facts that drove every target number, so the narrator
can explain each roll without re-deriving any rules (ADR 0001).

Keyword abilities (build phase 7) hook in via ``core.abilities``: before-roll
tweaks and after-roll pool adjustments per step, handed between steps through
generic carry fields (``HitStep.auto_wounds``,
``WoundStep.diverted_critical_wounds``, ...) that default to "no ability"
values, so a keywordless weapon flows through unchanged (ADR 0002). The
mortal-wound step at the end resolves
Devastating Wounds' per-critical mortal packets after normal damage (each
capped to one model, no spillover — rule 24.10); a weapon without it records
zeros and mirrors the damage step's final state.

The two entry points differ only in the weapon type they accept: the hit
roll reads the weapon's ``skill`` either way (BS when shooting, WS in
melee), and every later step is identical. Fight-phase *ordering* — who
swings first, alternation, casualty timing — is engine work (ADR 0006),
not pipeline work.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from wh40k_tutorial.core import abilities
from wh40k_tutorial.core.dice import RollResult, roll_d6, save_target, wound_target
from wh40k_tutorial.core.models import DiceValue, Profile, UnitDatasheet, Weapon


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
    hits: int  # final total, including any Sustained Hits extras
    critical_hits: int  # natural 6s — the trigger for Sustained/Lethal/Dev Wounds
    # Generic carry fields (ADR 0002) filled by keyword hooks; a weapon with
    # no abilities leaves them at zero and flows through unchanged.
    auto_wounds: int = 0  # hits that skip the wound roll (Lethal Hits); saves still apply
    sustained_extra_hits: int = 0  # plain extra hits added on criticals (Sustained Hits)


@dataclass(frozen=True)
class WoundStep:
    """The wound roll. ``strength`` vs ``toughness`` set the target (wound chart)."""

    roll: RollResult
    strength: int
    toughness: int
    wounds: int           # successful wound rolls plus any carried auto-wounds
    critical_wounds: int  # natural 6s — the trigger for Devastating Wounds
    # Generic carry (ADR 0002): Devastating Wounds pulls critical wounds out of
    # the save/damage path; the mortal-wound step rolls each crit's Damage.
    diverted_critical_wounds: int = 0

    @property
    def savable_wounds(self) -> int:
        """The wounds that proceed to the saving throw."""
        return self.wounds - self.diverted_critical_wounds


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
    signal. Damage never spills between models. (Devastating Wounds mortal
    wounds arrive in a later phase on their own track and share this
    one-model, no-spillover behaviour per rule 24.10 — see ADR 0002 and
    CONTEXT.md.)
    """

    damage: DiceValue       # the weapon's Damage characteristic (fixed or dice)
    rolls: tuple[int, ...]   # Damage rolled per failed save (constant for fixed Damage)
    damage_inflicted: int   # damage that actually removed wounds
    wasted_damage: int      # overkill lost on slain models (or a destroyed unit)
    models_slain: int
    models_remaining: int
    wounds_remaining_on_lead: int  # wounds left on the front model; 0 if unit destroyed


@dataclass(frozen=True)
class MortalWoundsStep:
    """Mortal wounds from Devastating Wounds, resolved after normal damage.

    Per the 11th-edition rules (Devastating Wounds, 24.10, verified against
    the Core Rules PDF 2026-07-05): a critical wound bypasses every saving
    throw and inflicts the weapon's Damage in mortal wounds, but those
    mortals can damage **at most one model per critical wound** — any beyond
    that model's remaining wounds are lost, exactly like normal-damage
    overkill. They do NOT spill to the next model; that is the specific
    Devastating Wounds exception to the general mortal-wound rule (06.02),
    which does spill. (Feel No Pain would roll per mortal wound; not modeled.)
    ``models_remaining``/``wounds_remaining_on_lead`` are the defender's
    final state after BOTH normal damage and mortals — the engine's single
    source of truth. A weapon without Devastating Wounds records a count of
    zero and mirrors the damage step's state.
    """

    count: int
    rolls: tuple[int, ...]  # mortal wounds rolled per critical wound (== count summed)
    inflicted: int
    wasted: int  # packets lost because the unit was already destroyed
    models_slain: int
    models_remaining: int
    wounds_remaining_on_lead: int


@dataclass(frozen=True)
class AttackResult:
    """One weapon's worth of attacks — shooting or melee — as a narratable record of facts."""

    attacker: UnitDatasheet
    defender: UnitDatasheet
    attack: AttackStep
    hit: HitStep
    wound: WoundStep
    save: SaveStep
    damage: DamageStep
    mortal: MortalWoundsStep

    @property
    def models_remaining(self) -> int:
        """Defender models left after the whole volley, mortals included."""
        return self.mortal.models_remaining

    @property
    def wounds_remaining_on_lead(self) -> int:
        """The lead model's wounds after the whole volley, mortals included."""
        return self.mortal.wounds_remaining_on_lead


def resolve_shooting(
    attacker: UnitDatasheet,
    attacker_model_count: int,
    weapon: Weapon,
    defender: UnitDatasheet,
    defender_wounds_remaining: int,
    defender_model_count: int,
    rng: random.Random | None = None,
) -> AttackResult:
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


def resolve_melee(
    attacker: UnitDatasheet,
    attacker_model_count: int,
    weapon: Weapon,
    defender: UnitDatasheet,
    defender_wounds_remaining: int,
    defender_model_count: int,
    rng: random.Random | None = None,
) -> AttackResult:
    """Resolve one melee weapon profile swung by N identical models at one target unit.

    The mirror of `resolve_shooting` for the Fight phase: same shared attack
    sequence, same record shape — the hit roll simply reads the weapon's WS.
    The engine owns everything melee-specific *around* this call (who fights
    when, engagement checks, casualty timing between fights; ADR 0006).
    """
    if weapon.type != "melee":
        raise ValueError(f"resolve_melee needs a melee weapon, got {weapon.name!r} (ranged)")
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
) -> AttackResult:
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
    wound = _roll_wounds(hit, weapon, defender.profile.toughness, rng)
    save = _roll_saves(wound.savable_wounds, defender.profile, weapon.ap, rng)
    damage = _allocate_damage(
        failed_saves=save.failed_saves,
        damage=weapon.damage,
        wounds_per_model=defender.profile.wounds,
        wounds_on_lead=defender_wounds_remaining,
        model_count=defender_model_count,
        rng=rng,
    )
    mortal = _resolve_mortal_wounds(
        critical_wounds=wound.diverted_critical_wounds,
        damage=weapon.damage,
        wounds_per_model=defender.profile.wounds,
        wounds_on_lead=damage.wounds_remaining_on_lead,
        model_count=damage.models_remaining,
        rng=rng,
    )
    return AttackResult(
        attacker=attacker,
        defender=defender,
        attack=attack,
        hit=hit,
        wound=wound,
        save=save,
        damage=damage,
        mortal=mortal,
    )


def _roll_hits(attack: AttackStep, rng: random.Random) -> HitStep:
    tweak = abilities.hit_roll_tweak(attack.weapon)
    roll = roll_d6(
        attack.total_attacks,
        target=attack.weapon.skill,
        modifier=tweak.modifier,
        reroll=tweak.reroll,
        rng=rng,
    )
    adj = abilities.hit_adjustment(roll, attack.weapon)
    return HitStep(
        roll=roll,
        hits=roll.successes + adj.extra_hits,
        critical_hits=roll.critical_hits,
        auto_wounds=adj.auto_wounds,
        sustained_extra_hits=adj.extra_hits,
    )


def _roll_wounds(hit: HitStep, weapon: Weapon, toughness: int, rng: random.Random) -> WoundStep:
    # Normal hits roll to wound; carried auto-wounds (Lethal Hits) are added
    # on top without a roll — the step never needs to know which ability
    # sent them (ADR 0002). Auto-wounds skipped the roll, so they can never
    # be critical wounds; only rolled natural 6s can divert to mortals.
    normal_hits = hit.hits - hit.auto_wounds
    tweak = abilities.wound_roll_tweak(weapon)
    roll = roll_d6(
        normal_hits,
        target=wound_target(weapon.strength, toughness),
        modifier=tweak.modifier,
        reroll=tweak.reroll,
        rng=rng,
    )
    adj = abilities.wound_adjustment(roll, weapon)
    return WoundStep(
        roll=roll,
        strength=weapon.strength,
        toughness=toughness,
        wounds=roll.successes + hit.auto_wounds,
        critical_wounds=roll.critical_hits,
        diverted_critical_wounds=adj.diverted_critical_wounds,
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
    damage: DiceValue,
    wounds_per_model: int,
    wounds_on_lead: int,
    model_count: int,
    rng: random.Random,
) -> DamageStep:
    """Allocate damage one failed save at a time, filling a model before the next.

    Each failed save deals a freshly rolled Damage (a constant for fixed
    Damage — no rng is drawn there, so existing seeds are undisturbed; a new
    D3/D6 sample per save otherwise). Excess damage on a model that dies is
    wasted, never carried to the next model. Failed saves against an
    already-destroyed unit are also recorded as wasted — the "your volley was
    bigger than the target" teaching signal.
    """
    rolls = tuple(damage.roll(rng) for _ in range(failed_saves))
    models_left = model_count
    current = wounds_on_lead if models_left > 0 else 0
    inflicted = wasted = slain = 0
    for dealt in rolls:
        if models_left == 0:
            wasted += dealt
            continue
        applied = min(dealt, current)
        inflicted += applied
        wasted += dealt - applied
        current -= applied
        if current == 0:
            slain += 1
            models_left -= 1
            current = wounds_per_model if models_left > 0 else 0
    return DamageStep(
        damage=damage,
        rolls=rolls,
        damage_inflicted=inflicted,
        wasted_damage=wasted,
        models_slain=slain,
        models_remaining=models_left,
        wounds_remaining_on_lead=current,
    )


def _resolve_mortal_wounds(
    *,
    critical_wounds: int,
    damage: DiceValue,
    wounds_per_model: int,
    wounds_on_lead: int,
    model_count: int,
    rng: random.Random,
) -> MortalWoundsStep:
    """Inflict Devastating Wounds mortal wounds, one critical wound at a time (24.10).

    Each critical wound rolls the weapon's Damage (fixed draws nothing;
    D3/D6 a fresh sample per crit) and inflicts that many mortal wounds
    against a *single* model — the wounded lead model absorbs first, which is
    the lead in our uniform units — and any of that crit's mortals beyond the
    model's remaining wounds are lost. This is the one-model cap from rule
    24.10: unlike the general mortal-wound rule (06.02), Devastating Wounds
    mortals do **not** spill to a second model, so a crit's allocation is
    exactly the normal-damage allocation (fill one model, waste the overkill)
    minus the saving throw. Crits with no model left to strike are wasted whole.
    """
    rolls = tuple(damage.roll(rng) for _ in range(critical_wounds))
    models_left = model_count
    current = wounds_on_lead if models_left > 0 else 0
    inflicted = wasted = slain = 0
    for dealt in rolls:
        if models_left == 0:
            wasted += dealt
            continue
        applied = min(dealt, current)
        inflicted += applied
        wasted += dealt - applied  # overkill: this crit can't spill onward
        current -= applied
        if current == 0:
            slain += 1
            models_left -= 1
            current = wounds_per_model if models_left > 0 else 0
    return MortalWoundsStep(
        count=sum(rolls),
        rolls=rolls,
        inflicted=inflicted,
        wasted=wasted,
        models_slain=slain,
        models_remaining=models_left,
        wounds_remaining_on_lead=current,
    )
