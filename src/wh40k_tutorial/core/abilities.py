"""Keyword-ability hooks (build phase 7, ADR 0002).

Weapon special rules are small per-step functions looked up by keyword name —
never branches inside the combat pipeline, never classes. Each step of the
attack sequence exposes two moments:

- **before-roll** hooks return a `RollTweak` (die modifier, re-roll policy).
  The *pipeline*, not the hooks, combines them: modifiers are summed and
  clamped to a net ±1 (the 11th-edition cap), and the single most generous
  re-roll wins. Both operations commute, so hook order can never change an
  outcome. No v1 keyword uses this moment yet; the machinery ships now
  because it is the committed architecture and later abilities (+1 to hit,
  re-roll 1s, ...) drop in as one registry entry each.
- **after-roll** hooks read the immutable `RollResult` and return an
  adjustment that splits or extends the pool. Cross-step abilities work by
  writing a generic carry field the later step honors without knowing any
  ability's name (ADR 0002): Lethal Hits fills `auto_wounds`, Devastating
  Wounds fills the mortal-wound track.

The three v1 abilities, as verified against the 11th-edition Core Rules PDF
on 2026-07-03 (see docs/design/shooting-pipeline.md):

- **Sustained Hits X** (24.36): each critical hit adds X additional *plain*
  hits — the extras are hits, not criticals.
- **Lethal Hits** (24.23): each critical hit may skip the wound roll and
  count as a wound automatically; saving throws still apply. In 11th this is
  a per-attack *choice* (declining lets the attack fish for a critical wound
  instead); v1 policy is to always accept, and the hook — not the pipeline —
  owns that policy, so a smarter policy can replace it without touching
  combat code.
- **Devastating Wounds** (24.10): each critical *wound* ends that attack's
  sequence — no save, no normal damage — and the target unit instead
  suffers mortal wounds equal to the weapon's Damage, inflicted after the
  volley's normal damage. Those mortals hit at most one model per critical
  wound (overkill lost, no spillover); the pipeline's mortal-wound step
  applies that cap. This hook only splits the pool (counts the criticals and
  the Damage they carry); the allocation lives in combat.py.

Adding an ability = one small function here + one registry entry. The combat
pipeline never changes.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from wh40k_tutorial.core.dice import RerollPolicy, RollResult
from wh40k_tutorial.core.models import Weapon

# ---------------------------------------------------------------------------
# Before-roll moment: tweaks to how the dice are rolled
# ---------------------------------------------------------------------------

# How much a re-roll policy is worth to the roller, for "most generous wins".
# "fails" strictly contains "ones"; "all" (re-roll everything, even
# successes) sits below "fails" because it can undo successes.
_REROLL_GENEROSITY: dict[RerollPolicy, int] = {"none": 0, "ones": 1, "all": 2, "fails": 3}


@dataclass(frozen=True)
class RollTweak:
    """One hook's requested change to a roll: a die modifier and/or a re-roll."""

    modifier: int = 0
    reroll: RerollPolicy = "none"


def combine_tweaks(tweaks: list[RollTweak]) -> RollTweak:
    """The pipeline's combination rule: sum-and-clamp modifiers, best re-roll.

    The net modifier is clamped to ±1 per the 11th-edition cap on hit and
    wound rolls. Summation and max-by-generosity both commute, which is what
    makes hook order irrelevant (ADR 0002).
    """
    net = sum(t.modifier for t in tweaks)
    modifier = max(-1, min(1, net))
    reroll = max(
        (t.reroll for t in tweaks),
        key=lambda r: _REROLL_GENEROSITY[r],
        default="none",
    )
    return RollTweak(modifier=modifier, reroll=reroll)


# ---------------------------------------------------------------------------
# After-roll moment: adjustments that split or extend the pool
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HitAdjustment:
    """What hit-step after-roll hooks contribute; summed componentwise."""

    extra_hits: int = 0  # plain additional hits (Sustained Hits)
    auto_wounds: int = 0  # hits that skip the wound roll (Lethal Hits)


@dataclass(frozen=True)
class WoundAdjustment:
    """What wound-step after-roll hooks contribute; summed componentwise."""

    diverted_critical_wounds: int = 0  # pulled out before saves (Devastating Wounds)
    mortal_wounds: int = 0  # total mortals (crits x Damage); combat caps each crit to one model


HitHook = Callable[[RollResult, Weapon, int | None], HitAdjustment]
WoundHook = Callable[[RollResult, Weapon, int | None], WoundAdjustment]
TweakHook = Callable[[Weapon, int | None], RollTweak]


def _sustained_hits(roll: RollResult, weapon: Weapon, value: int | None) -> HitAdjustment:
    per_critical = value if value is not None else 1
    return HitAdjustment(extra_hits=per_critical * roll.critical_hits)


def _lethal_hits(roll: RollResult, weapon: Weapon, value: int | None) -> HitAdjustment:
    # v1 policy: always accept the auto-wound. 11th makes it a per-attack
    # choice (declining keeps the chance of a critical wound, which matters
    # on a weapon that also has Devastating Wounds); that policy belongs
    # here, so replacing it never touches the pipeline.
    return HitAdjustment(auto_wounds=roll.critical_hits)


def _devastating_wounds(roll: RollResult, weapon: Weapon, value: int | None) -> WoundAdjustment:
    criticals = roll.critical_hits  # natural 6s on this (wound) roll
    return WoundAdjustment(
        diverted_critical_wounds=criticals,
        mortal_wounds=criticals * weapon.damage,
    )


# Registries: keyword name -> hook, per step and moment. Empty registries are
# the before-roll moments no v1 keyword uses yet.
HIT_BEFORE: dict[str, TweakHook] = {}
WOUND_BEFORE: dict[str, TweakHook] = {}
SAVE_BEFORE: dict[str, TweakHook] = {}
HIT_AFTER: dict[str, HitHook] = {
    "sustained_hits": _sustained_hits,
    "lethal_hits": _lethal_hits,
}
WOUND_AFTER: dict[str, WoundHook] = {
    "devastating_wounds": _devastating_wounds,
}


# ---------------------------------------------------------------------------
# What the pipeline calls
# ---------------------------------------------------------------------------


def hit_roll_tweak(weapon: Weapon) -> RollTweak:
    """The combined before-roll tweak for this weapon's hit roll."""
    return combine_tweaks(
        [
            HIT_BEFORE[kw.name](weapon, kw.value)
            for kw in weapon.parsed_keywords
            if kw.name in HIT_BEFORE
        ]
    )


def wound_roll_tweak(weapon: Weapon) -> RollTweak:
    """The combined before-roll tweak for this weapon's wound roll."""
    return combine_tweaks(
        [
            WOUND_BEFORE[kw.name](weapon, kw.value)
            for kw in weapon.parsed_keywords
            if kw.name in WOUND_BEFORE
        ]
    )


def hit_adjustment(roll: RollResult, weapon: Weapon) -> HitAdjustment:
    """Sum every registered hit-step after-roll hook the weapon's keywords name."""
    extra = auto = 0
    for kw in weapon.parsed_keywords:
        hook = HIT_AFTER.get(kw.name)
        if hook is not None:
            adj = hook(roll, weapon, kw.value)
            extra += adj.extra_hits
            auto += adj.auto_wounds
    return HitAdjustment(extra_hits=extra, auto_wounds=auto)


def wound_adjustment(roll: RollResult, weapon: Weapon) -> WoundAdjustment:
    """Sum every registered wound-step after-roll hook the weapon's keywords name."""
    diverted = mortal = 0
    for kw in weapon.parsed_keywords:
        hook = WOUND_AFTER.get(kw.name)
        if hook is not None:
            adj = hook(roll, weapon, kw.value)
            diverted += adj.diverted_critical_wounds
            mortal += adj.mortal_wounds
    return WoundAdjustment(diverted_critical_wounds=diverted, mortal_wounds=mortal)
