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
Damage that bypasses all saving throws (armour and invulnerable), inflicted *after* the volley's normal damage. In 11th edition our only source is **Devastating Wounds** on a critical wound (24.10): each critical wound inflicts the weapon's Damage in mortal wounds against a **single model**, and any beyond that model's remaining wounds are lost — exactly like normal-damage overkill. Devastating Wounds mortals do **not** spill to the next model: the cap is one model per critical wound. (The *general* mortal-wound rule, 06.02, does let mortals cross models one wound at a time, but Devastating Wounds is the explicit exception. If a future non–Devastating-Wounds mortal source is ever modelled, it would follow 06.02's spilling allocation instead.) Feel No Pain would apply to each mortal wound (not modelled yet). (Corrected against the 11th Core Rules PDF §24.10, 2026-07-05 — supersedes an earlier note that read these as spilling one wound at a time, which was the general-rule behaviour, not the Devastating Wounds exception.)
_Avoid_: no-save wound — that was the *end-of-10th* Devastating Wounds (normal damage, no spillover) and is not how 11th resolves; describing Devastating Wounds mortals as "spilling over" — they cap at one model per critical wound.

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

**Grid scale / distance**:
One grid square is 2" (ADR 0007). The distance between two squares is the Chebyshev distance — the number of king's moves, diagonals included — times the scale; converting an inches-long reach into squares rounds DOWN (`reach_squares`), so quantization may shave a weapon's reach but never extends it ("honest ranges"). `core.scenario` owns the scale, the metric and both conversions.
_Avoid_: tiles, cells, Manhattan/Euclidean distance.

**In range**:
A target within a weapon's Range: Chebyshev distance ≤ `reach_squares(weapon.range)` (`core.scenario.in_weapon_range`, the single definition). A shooting target must be in range and unengaged, and the shooter must itself be unengaged (04.02, 10.04); the loader rejects out-of-range scripted shots at load time, the engine enforces all three on live state.
_Avoid_: within reach, close enough.

**Engagement range / engaged**:
The zone in which melee happens: within 2" horizontally (5" vertically in the full game — meaningless on a flat grid) of a model. While opposing models sit inside each other's engagement range, they — and their units — are engaged. On our grid, 2" is exactly one square (ADR 0007), so engaged = adjacent, diagonals included (`core.scenario.in_engagement_range`, the single definition) — a measurement, not a convention.
_Avoid_: melee range, base contact (a different, tighter thing).

**Fight phase**:
The phase in which BOTH players act: every engaged unit must fight exactly once, players alternate picking which of their units fights next — the player whose turn it is picks first (absent Fights First units) — and casualties are applied fight by fight, so a unit picked later swings with only its surviving models.
_Avoid_: melee phase, combat phase.

**Selected to fight**:
The moment a unit is picked in the fight-phase alternation and resolves all its melee attacks. Each unit is selected at most once per fight phase; fighting is mandatory for every unit that can.
_Avoid_: activates in melee (we reserve "activation" for the generic once-per-phase act).

**Fights First**:
A unit-level ability (every model must have it) that puts the unit in the fight phase's priority selection step, before ordinary combats. Charging is what normally grants the effect. Named here for the glossary; deferred with charges — no unit in the project's data carries it.
_Avoid_: strikes first, initiative (an older edition's concept).

