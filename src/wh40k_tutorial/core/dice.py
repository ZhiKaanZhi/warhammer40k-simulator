"""Dice primitives for the 11th-edition Warhammer 40,000 rules (core dice math unchanged from 10th).

This module is the foundation everything else builds on. It is deliberately
overspecified (more features than v1 needs) because:

1. Dice math is easy to get subtly wrong, so explicit primitives reduce
   mistakes in the combat pipeline.
2. Once these primitives exist and are tested, the rest of the engine
   never touches the random number generator directly.

All randomness in the project goes through this module. Do not import
`random` anywhere else in `core/`.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Literal

# A reroll policy describes which dice may be re-rolled before they're scored.
# - "none": no rerolls
# - "ones": re-roll natural 1s (the most common case in 40k)
# - "fails": re-roll any die that didn't meet the target (full reroll)
# - "all": re-roll every die once (rare; "twin-linked" before it was simplified)
RerollPolicy = Literal["none", "ones", "fails", "all"]


@dataclass(frozen=True)
class RollResult:
    """The full result of rolling a pool of dice against a target.

    Carrying the raw dice through (not just a success count) is what makes
    the narrator work: it can show every die's face and explain which ones
    passed, which failed, and why.
    """

    rolls: tuple[int, ...]  # the final face of each die after any rerolls/modifiers
    raw_rolls: tuple[int, ...]  # pre-modifier, pre-reroll faces (for narration)
    target: int  # the unmodified target (e.g. 3 for a "3+" save)
    modifier: int  # the modifier applied to each die's face
    reroll: RerollPolicy

    @property
    def successes(self) -> int:
        """Count of dice that met or exceeded the target after modifiers.

        Natural 1s always fail and natural 6s always succeed in 40k, regardless
        of modifiers. This is the "critical" rule from the core rulebook.
        """
        return sum(1 for r, raw in zip(self.rolls, self.raw_rolls) if _passes(raw, r, self.target))

    @property
    def critical_hits(self) -> int:
        """Count of natural 6s, which matter for Sustained Hits / Lethal Hits / Dev Wounds."""
        return sum(1 for raw in self.raw_rolls if raw == 6)

    def passing_indices(self) -> list[int]:
        """Indices of the dice that succeeded — useful for narration."""
        return [i for i, (raw, r) in enumerate(zip(self.raw_rolls, self.rolls)) if _passes(raw, r, self.target)]


def _passes(raw: int, modified: int, target: int) -> bool:
    """Apply 40k's natural-1-fails / natural-6-succeeds rule, then compare to target."""
    if raw == 1:
        return False
    if raw == 6:
        return True
    return modified >= target


def roll_d6(
    count: int,
    *,
    target: int = 4,
    modifier: int = 0,
    reroll: RerollPolicy = "none",
    rng: random.Random | None = None,
) -> RollResult:
    """Roll `count` six-sided dice against `target`, optionally with a modifier and rerolls.

    Args:
        count: How many dice to roll. Must be non-negative.
        target: The unmodified target the dice are trying to meet (a "3+" is target=3).
        modifier: Added to each die's face before comparing to target. Capped at +/-1
            per 40k's modifier rule — caller is responsible for clamping.
        reroll: Which dice (if any) may be re-rolled once before being scored.
        rng: Optional `random.Random` instance for deterministic testing.

    Returns:
        A `RollResult` carrying the raw faces, post-reroll faces, and the parameters
        used so callers can both check `.successes` and produce rich narration.

    Raises:
        ValueError: if `count` is negative or `target` is out of [2, 6].
    """
    if count < 0:
        raise ValueError(f"count must be non-negative, got {count}")
    if not 2 <= target <= 6:
        raise ValueError(f"target must be in [2, 6], got {target}")

    r = rng or random.Random()
    raw_rolls: list[int] = [r.randint(1, 6) for _ in range(count)]

    if reroll != "none":
        for i, face in enumerate(raw_rolls):
            should_reroll = (
                (reroll == "ones" and face == 1)
                or (reroll == "fails" and not _passes(face, face + modifier, target))
                or (reroll == "all")
            )
            if should_reroll:
                raw_rolls[i] = r.randint(1, 6)

    modified = tuple(face + modifier for face in raw_rolls)
    return RollResult(
        rolls=modified,
        raw_rolls=tuple(raw_rolls),
        target=target,
        modifier=modifier,
        reroll=reroll,
    )


def wound_target(strength: int, toughness: int) -> int:
    """Return the to-wound target (2..6) for a given strength vs. toughness comparison.

    The 11th-edition wound chart (unchanged from 10th):
        S >= 2*T   -> 2+
        S >  T     -> 3+
        S == T     -> 4+
        S <  T     -> 5+
        S*2 <= T   -> 6+
    """
    if strength >= 2 * toughness:
        return 2
    if strength > toughness:
        return 3
    if strength == toughness:
        return 4
    if strength * 2 <= toughness:
        return 6
    return 5


def save_target(armor_save: int, ap: int, invuln: int | None = None) -> int:
    """Return the to-save target after AP, falling back to invuln if better.

    `ap` is the *magnitude* of the AP modifier (a positive int).
    A weapon with AP -2 is `ap=2` and increases the save target by 2.

    `invuln`, if given, is the unmodified invulnerable save target (e.g. 4 for "4++").
    Invuln saves are not affected by AP. The defender uses whichever is better.
    """
    modified_armor = armor_save + ap
    if invuln is not None:
        return min(modified_armor, invuln)
    return modified_armor
