"""The narrator: the rule behind every roll, in plain English (build phase 6).

`narrate_volley` turns one `ShootingResult` into five `StepNarration`s — one
per pipeline step, in pipeline order. Each carries:

- ``inline``    — one or two sentences naming the rule that drove the step,
                  shown right under the step's fact line;
- ``expansion`` — the fuller rule, shown on demand when the player asks
                  "why?" about a step.

Per ADR 0001 this module is a **pure formatter**: it reads only the facts the
combat pipeline recorded (targets, stats, counts) and never re-derives game
outcomes. The one mapping it owns is facts → words — e.g. turning a recorded
wound target of 3 into "Strength beats Toughness". All wording here is our
own; rulebook text is never reproduced (see "Rules accuracy" in CLAUDE.md).

Zero pools narrate fine: the inline lines explain targets and stats, which
exist even when no dice were rolled.
"""

from __future__ import annotations

from dataclasses import dataclass

from wh40k_tutorial.core.combat import ShootingResult

STEP_ORDER = ("attacks", "hit", "wound", "save", "damage")


@dataclass(frozen=True)
class StepNarration:
    """The teaching text for one pipeline step of one volley."""

    step: str  # one of STEP_ORDER
    inline: str
    expansion: str


def narrate_volley(result: ShootingResult) -> tuple[StepNarration, ...]:
    """Explain each step of one volley, in pipeline order."""
    return (
        StepNarration("attacks", _attacks_inline(result), _ATTACKS_EXPANSION),
        StepNarration("hit", _hit_inline(result), _HIT_EXPANSION),
        StepNarration("wound", _wound_inline(result), _WOUND_EXPANSION),
        StepNarration("save", _save_inline(result), _SAVE_EXPANSION),
        StepNarration("damage", _damage_inline(result), _DAMAGE_EXPANSION),
    )


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    if count == 1:
        return singular
    return plural if plural is not None else singular + "s"


# ---------------------------------------------------------------------------
# Attacks
# ---------------------------------------------------------------------------


def _attacks_inline(result: ShootingResult) -> str:
    a = result.attack
    dice = _plural(a.total_attacks, "die", "dice")
    return (
        f"{a.weapon.display_name}'s Attacks value is {a.attacks_per_model} and every "
        f"model in the unit fires, so the pool is {a.attacker_models} x "
        f"{a.attacks_per_model} = {a.total_attacks} {dice}."
    )


_ATTACKS_EXPANSION = (
    "Attacks (the A on a weapon profile) is how many dice one model contributes "
    "when it uses that weapon. A unit's pool is simply models x Attacks, because "
    "every model in the unit shoots. Some weapons in the full game roll for their "
    "Attacks value (\"D6 attacks\"); everything in this tutorial uses fixed numbers, "
    "so the pool is known before any dice hit the table."
)


# ---------------------------------------------------------------------------
# Hit
# ---------------------------------------------------------------------------


def _hit_inline(result: ShootingResult) -> str:
    skill_name = "Ballistic Skill" if result.attack.weapon.type == "ranged" else "Weapon Skill"
    return (
        f"To hit, each die must roll {result.hit.roll.target}+ — the firers' "
        f"{skill_name}, printed on the weapon profile. A natural 1 always misses "
        f"and a natural 6 always hits."
    )


_HIT_EXPANSION = (
    "The hit roll is one D6 per attack against the attacker's own accuracy: "
    "Ballistic Skill (BS) when shooting, Weapon Skill (WS) in melee — lower is "
    "better. Two results ignore everything else: an unmodified 1 always fails, and "
    "an unmodified 6 always hits. That unmodified 6 is also a critical hit, the "
    "trigger that abilities like Sustained Hits and Lethal Hits feed on once they "
    "enter the game. When to-hit modifiers exist, their net effect on the roll is "
    "capped at plus or minus 1."
)


# ---------------------------------------------------------------------------
# Wound
# ---------------------------------------------------------------------------

_WOUND_RELATIONS = {
    2: "is at least double",
    3: "beats",
    4: "exactly matches",
    5: "is below",
    6: "is no more than half of",
}


def _wound_inline(result: ShootingResult) -> str:
    w = result.wound
    relation = _WOUND_RELATIONS[w.roll.target]
    return (
        f"The weapon's Strength {w.strength} {relation} the target's Toughness "
        f"{w.toughness}, and the wound chart turns that comparison into a "
        f"{w.roll.target}+ to wound."
    )


_WOUND_EXPANSION = (
    "Wounding weighs the weapon's punch (Strength, S) against the target's "
    "resilience (Toughness, T) on one chart every attack in the game uses: "
    "S at least double T needs 2+ · S higher than T needs 3+ · S equal to T "
    "needs 4+ · S lower than T needs 5+ · S no more than half of T needs 6+. "
    "As with hit rolls, an unmodified 1 always fails and an unmodified 6 always "
    "wounds — a critical wound, which some abilities build on later."
)


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------


def _save_inline(result: ShootingResult) -> str:
    s = result.save
    armour_after_ap = s.armor_save + s.ap
    if not s.save_possible:
        return (
            f"AP -{s.ap} pushes the {s.armor_save}+ armour to {armour_after_ap}+ — "
            f"beyond what a D6 can roll. No save is possible, so no dice: every "
            f"wound goes straight through."
        )
    invuln_wins = (
        s.invulnerable_save is not None
        and s.modified_target == s.invulnerable_save < armour_after_ap
    )
    if invuln_wins:
        return (
            f"AP -{s.ap} would push the {s.armor_save}+ armour to {armour_after_ap}+, "
            f"but an invulnerable save ignores AP entirely — the target falls back "
            f"on its {s.invulnerable_save}++ and saves on {s.invulnerable_save}+."
        )
    if s.ap == 0:
        line = (
            f"The target's armour save is {s.armor_save}+ and this weapon has no "
            f"AP, so saves need {s.modified_target}+."
        )
    else:
        line = (
            f"The target's armour save is {s.armor_save}+, but AP -{s.ap} is "
            f"armour-piercing and worsens it to {s.modified_target}+."
        )
    if s.invulnerable_save is not None:
        line += (
            f" (Their {s.invulnerable_save}++ invulnerable would ignore AP, but "
            f"{s.modified_target}+ is still the better save.)"
        )
    return line


_SAVE_EXPANSION = (
    "The saving throw is the defender's answer: one D6 per wound against the best "
    "save available. AP (Armour Penetration) is a property of the weapon, not a die "
    "modifier — it worsens the armour save's target directly, with no cap. An "
    "invulnerable save (written 4++ and so on) is protection that armour-piercing "
    "cannot touch: it ignores AP completely, and the defender always uses whichever "
    "save is better. Saves have no lucky-six rule — an unmodified 1 always fails, "
    "and a 6 only saves if it actually meets the target. If AP drives the needed "
    "roll past 6, there is simply no save at all."
)


# ---------------------------------------------------------------------------
# Damage
# ---------------------------------------------------------------------------


def _damage_inline(result: ShootingResult) -> str:
    d = result.damage
    per = d.damage_per_failed_save
    wounds_per_model = result.defender.profile.wounds
    defender = result.defender.display_name
    line = f"Each failed save deals the weapon's Damage — {per} here — to one model at a time."
    if wounds_per_model == 1:
        line += f" {defender} have a single wound apiece, so every failed save drops a model."
    elif per >= wounds_per_model:
        line += (
            f" A {defender} model has {wounds_per_model} wounds and takes {per} at "
            f"once, so every failed save drops one."
        )
    else:
        line += (
            f" A {defender} model has {wounds_per_model} wounds, so failed saves "
            f"pile onto the same front model until it falls, then move to the next."
        )
    if d.wasted_damage:
        pts = _plural(d.wasted_damage, "point")
        line += (
            f" Damage never spills from a dying model to the next — {d.wasted_damage} "
            f"{pts} vanished here as overkill."
        )
    return line


_DAMAGE_EXPANSION = (
    "Damage (D) is how many wounds one failed save strips from one model. "
    "Casualties come off one model at a time: the current front model absorbs "
    "failed saves until its wounds reach zero, then the next steps up. Damage "
    "never spills over — if a killing blow deals more than the model had left, "
    "the surplus is wasted, the tell-tale sign of overkill (a weapon heavier than "
    "its target needs). A partially damaged model keeps its missing wounds into "
    "later volleys."
)
