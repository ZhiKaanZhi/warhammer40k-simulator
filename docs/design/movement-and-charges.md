# Movement & Charges — Research and Plan

The next big design-first effort after the fight phase: give units the ability to
move, advance, fall back and charge, on the distance model fixed by
[ADR 0007](../adr/0007-grid-scale-chebyshev-distances.md) (1 square = 2",
Chebyshev, floor conversion). Rules verified 2026-07-19 against the official 11th
Core Rules PDF (movement page and both charge pages read on rasterized images per
the researcher recipe — see the findings log in
`.claude/agents/rules-researcher.md`). This document records the verified rules,
the agreed PR sequence, and the design details already pinned.

## The verified rules (11th Core Rules)

**Move types (09.04–09.07).** In the Movement phase the active player moves units
one at a time; each picks one move type it is eligible for:

| Move type | Max distance | Eligible if | Afterwards |
|---|---|---|---|
| Remain Stationary (09.04) | — | any unit | triggers no start/end-of-move rules |
| Normal Move (09.05) | M | on the battlefield, unengaged | must end unengaged |
| Advance Move (09.06) | M + advance roll (one D6) | on the battlefield, unengaged | must end unengaged; until end of turn: no charge, no actions |
| Fall-back Move (09.07) | M | **engaged** | must end unengaged; until end of turn: no shooting, no charge, no actions |

Fall-back has two modes assessed in order: *Ordered Retreat* (allowed when not
battle-shocked) and *Desperate Escape* (mandatory when battle-shocked: hazard roll
per model, may move through enemy models, battle-shock roll after if applicable).
We do not model battle-shock, so **v-next models Ordered Retreat only** and
documents Desperate Escape as deferred with battle-shock.

**Shoot eligibility is where movement bites shooting (10.04–10.07).** Normal
Shooting (10.04) requires *unengaged and did not advance*. An advanced unit may
shoot only via Assault Shooting (10.05): unengaged, advanced, and only with
[ASSAULT] weapons. An engaged unit may shoot only via Close-Quarters Shooting
(10.06), which needs [CLOSE-QUARTERS] weapons (or Monster/Vehicle) — none in our
data, already enforced as "engaged units cannot shoot" since ADR 0007. Indirect
Shooting (10.07) needs [INDIRECT FIRE] — none in our data.

**Movement-linked weapon abilities (24.xx).**

- **[ASSAULT] (24.04):** the unit can use Assault Shooting (above). Already a
  keyword on the bolt rifle and pulse rifle; inert until movement exists.
- **[HEAVY] (24.16):** +1 to hit if the attacking unit is unengaged, was not set
  up this turn, and **no model in it moved more than 3" this turn**. (11th changed
  this from 10th's "remained stationary" — the researcher's read-the-keyword's-own-
  rule discipline applies.) On our grid: moved at most 1 square.
- **[RAPID FIRE X] (24.30):** +X attack dice per weapon when the target was
  **within half range** at Select Targets. Already on several guns; inert today.

**Charges (11.02, 11.04).** Eligible to declare: on the battlefield, within 12" of
an enemy, not engaged, did not advance or fall back this turn. Charge roll = 2D6 =
the **maximum distance** of the charge move. Declaring targets: one or more enemy
units **within 12" and within the maximum distance**. The move must end with the
unit **engaged with ALL charge targets** and engaged with **no non-targets**;
models that can end within 1"/engaged of a target must. After moving, **every
model in the unit has Fights First (24.13) until the end of the turn** — this
activates the fight engine's already-shipped-but-dormant Fights First step.
Failed-charge sidebar (verified verbatim on the rasterized page): absent modifiers,
a roll of 2 (double 1) is never sufficient, because the charging unit cannot
already be within engagement range (2") when it attempts the charge.

## The pinned design details

**1. Charge-roll quantization vs the double-1 sidebar — resolved.** On our grid a
legal charge target starts unengaged, i.e. at Chebyshev distance ≥ 2 squares (>
2"). The declare step requires the target within the roll's distance:
`chebyshev(unit, target) ≤ reach_squares(2D6)`. A roll of 2 gives
`reach_squares(2) = 1` — only engaged squares, which no legal target occupies — so
the double-1 auto-fail is *reproduced by the arithmetic*, no special case needed.
Completion is implied: reaching Chebyshev 1 costs `d − 1 ≤ reach_squares(roll)`
squares of movement, already guaranteed by the declare condition. Net rule the
engine will implement: **a charge against a target d squares away succeeds iff
`d ≤ reach_squares(roll)`** (equivalently `2d ≤ roll`), mirroring the tabletop's
"separation ≤ roll" shape one-for-one.

**2. Movement menu UX — decided direction, final wording at PR #22.** Movement is
the first phase where *doing nothing* is a legal pick, and a tutorial must not
drown beginners in no-ops. Direction: the movement menu is per-unit like shooting
(eligible movers listed; Remain Stationary always offered first and is the
default), a mover picks a destination from the squares its move type reaches
(small boards keep this list short), and scenario turns may omit the movement
phase entirely — scenarios that teach shooting stay exactly as they are. Scripted
opponents get a `"move"` action shape mirroring `"shoot"`/`"fight"`; the loader
validates destinations against move type, occupancy and the end-unengaged rules.

**3. Heuristic movement policy — decided direction, tuned at PR #22/#24.** The AI
must not wander. Policy: score candidate destinations with the same
`core/expected.py` math used for shot-picking — a destination is worth the best
expected damage the unit could deal from it next activation (shooting now; charges
at PR #24 fold in the expected fight swing), minus expected damage taken standing
there, with Remain Stationary the baseline candidate. Deterministic tie-breaks by
scenario order, then reading order of squares, matching the shot-picker's
discipline. Advance/fall-back enter the candidate set only when their aftermath
restrictions (no shooting / assault-only) are priced into the score.

## The PR sequence (each independently mergeable)

- **PR #21 — Distances & honest ranges** *(this one)*: ADR 0007; the distance
  model in `core/scenario.py`; range + engaged-shooting enforcement in loader,
  engine, menus and heuristic; nine scenarios byte-identical.
- **PR #22 — The Movement phase**: `"movement"` scenario turns; Remain
  Stationary / Normal / Advance / Fall Back (Ordered Retreat only); per-turn
  moved/advanced/fell-back flags feeding shoot eligibility (10.04: advanced or
  fallen-back units cannot shoot — Assault Shooting arrives in PR #23); movement
  menu UX above; heuristic movement policy above; a scenario teaching
  position-before-shooting.
- **PR #23 — Movement-linked weapon abilities**: [ASSAULT] (10.05 assault
  shooting), [HEAVY] (+1 to hit under the 3"/1-square condition), [RAPID FIRE X]
  (+X dice within half range — `reach_squares(range/2)`, floor, honest); a
  scenario starring the AdMech arc rifle's Rapid Fire 1 at half range.
- **PR #24 — The Charge phase**: `"charge"` turns; eligibility, 2D6 roll, the
  quantized success rule above, end-engaged-with-all-targets; charging grants
  Fights First — activating the dormant step in the fight engine; an Orks charge
  scenario (get in, hit first).

Out of scope for this arc, unchanged: terrain/visibility (04.02's "visible"
condition stays vacuous), battle-shock and Desperate Escape, [CLOSE-QUARTERS] /
[INDIRECT FIRE] shooting, Pile-in/Consolidate refinements beyond what the fight
engine already does, Overwatch and other out-of-phase shooting.

## Open questions parked for their PR

- Charge-roll teaching: narrate the 2D6 in inches *and* squares so the
  quantization is a lesson, not a mystery (PR #24, narrator).
- Whether the movement scenario grants the opponent a return shooting turn (feel
  the cost of advancing) — scenario design at PR #22.
- Heuristic fall-back willingness: when losing a melee, is escaping worth losing
  the shooting phase? Price it, don't hardcode it (PR #22, revisit at #24).
