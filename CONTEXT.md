# Warhammer 40k Tutorial — Domain Language

The canonical vocabulary for the shooting/combat domain. These are the words the code, the narrator, and the docs must use consistently. This file is a glossary only — design rationale lives in `docs/adr/`.

## Language

**Attacks**:
The number of times a weapon swings or fires; the "A" characteristic. Resolved into a concrete pool of dice, possibly from a random value (e.g. "D6 attacks").
_Avoid_: shots, swings.

**Weapon profile**:
One weapon's complete statline (attacks, skill, strength, AP, damage, keywords). The unit of combat resolution: one `resolve_shooting` call resolves exactly one weapon profile fired by N identical models at one target.
_Avoid_: gun, loadout.

**Critical hit / critical wound**:
A natural, unmodified 6 on a hit roll (critical hit) or wound roll (critical wound). Always succeeds regardless of modifiers, and is the trigger for abilities like Sustained Hits, Lethal Hits, and Devastating Wounds.
_Avoid_: crit (informal only), natural six.

**Auto-wound**:
A hit that skips the wound roll and counts directly as a wound. Granted by Lethal Hits on critical hits.
_Avoid_: auto-hit (a different thing), lethal hit.

**Mortal wound**:
Damage that bypasses all saving throws (armour and invulnerable). Resolved **one at a time as single-wound packets**: each mortal wound picks a model (an already-wounded non-character first) and removes exactly 1 wound, walking across models until all are inflicted or the unit is destroyed — so it naturally crosses model boundaries, unlike normal damage, whose excess on a slain model is wasted. Excess mortal wounds die with the unit. Feel No Pain applies to each one. In 11th edition this is the effect of **Devastating Wounds** on a critical wound, inflicted *after* the volley's normal damage. (Confirmed against the 11th Core Rules PDF, 2026-07-03.)
_Avoid_: no-save wound — that was the *end-of-10th* Devastating Wounds (normal damage, no spillover) and is not how 11th resolves.

**Wasted damage (overkill)**:
Damage lost when a single failed save deals more than a model's remaining wounds. Damage never spills from one model to the next; the excess is simply gone. A teachable signal that a weapon was overkill against this target.
_Avoid_: spillover, carryover.

**Modifier**:
An adjustment to a die roll (e.g. +1 to hit, −1 to wound). The net modifier on a hit or wound roll is capped at ±1. Saving throws are asymmetric: an *improvement* (e.g. cover) caps at +1, but there is no −1 cap because saves are worsened by AP, not by a die modifier. Distinct from AP.
_Avoid_: bonus, buff.

**Armour Penetration (AP)**:
A weapon characteristic that worsens the target of the defender's saving throw (stored as a positive magnitude — "AP −2" is `ap=2`). It is NOT a die modifier: exempt from the ±1 cap, and it does not affect invulnerable saves.
_Avoid_: armour mod, save modifier.

**Invulnerable save**:
An alternative saving throw that ignores AP. The defender uses whichever is better — the AP-modified armour save or the invulnerable save.
_Avoid_: invuln (informal only), ward save.
