# Saving throws: impossible saves auto-fail without rolling; AP is not a die modifier

**Status:** accepted

`core.dice.roll_d6` bakes in the hit/wound-roll rule that an *unmodified 6 always succeeds*, and it rejects targets outside `[2, 6]`. Saving throws share neither property cleanly: a 4+ armour save against AP-3 needs a 7+, which both crashes the primitive and (if we naively clamped to 6) would let a natural 6 "save" a wound that has no save at all.

Decision: the save step computes the modified save — armour worsened by AP, then the better of that and any invulnerable save. If the best available save is **7+ (no save possible)**, every wound fails automatically with **no dice rolled**; the narrator still explains it ("no save: AP-3 against a 4+ armour, no invuln"). Only when a real `2..6` save exists do we roll. **AP** adjusts the save target directly and is **exempt from the ±1 die-modifier cap** — it is a weapon characteristic, not a roll modifier. Invulnerable saves ignore AP; the defender always uses whichever save is better.

## Considered Options

- **Clamp the modified save target to 6.** Rejected: a natural 6 would then "save" an unsavable wound — wrong outcome.
- **Route every save through `roll_d6`.** Rejected: it raises on a target of 7 and would misapply the natural-6 rule to saves.

## Consequences

The save step needs an explicit *no-save* branch that still yields a valid, empty-roll record for narration. Cover and other save *die*-modifiers are out of v1 scope (no terrain); if added later, the save step must stop trusting `roll_d6`'s natural-6 success, because saving throws have no "unmodified 6 always saves" rule.

**Verified 2026-06-30 (rules-researcher):** confirmed against the current rules — an unmodified 1 always fails, there is **no** "unmodified 6 always saves" rule, and a required save of 7+ is simply unmakeable. Also confirmed: AP is uncapped and ignores invulnerable saves, and save *improvements* (e.g. cover) cap at +1 (there is no symmetric −1 cap, since worsening is handled by AP). **Residual resolved 2026-07-03, against the official 11th Core Rules PDF (read visually where the tables print numerals as graphics):** the save table has no critical-save row — an unmodified 1 always fails, and a save succeeds only via the invulnerable value (raw die, never AP-modified) or the AP-modified armour value. "Save Groups" turned out to be **allocation groups**: pure allocation procedure (group models by identical Wounds/save/invulnerable values, resolve save dice lowest to highest against the current group) that collapses to this ADR's model for v1's uniform units. Details in `docs/design/shooting-pipeline.md` → *Primary-source verification*.
