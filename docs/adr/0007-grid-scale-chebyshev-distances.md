# One grid square is 2"; distance is Chebyshev; converting inches to squares rounds down

**Status:** accepted

The scenarios position units on a 12×8 grid, but the rules speak in inches: weapon
Range, the 2" engagement range (03.04), and — once movement lands — Move
characteristics, D6 advance rolls and 2D6 charge rolls. Until now the grid had no
declared scale, so range went unenforced (ADR 0005's documented simplification) and
the fight phase's "adjacency = engaged" was a convention rather than a measurement.

Decision, in three parts (`core/scenario.py` is the single home of all of it):

1. **One square is 2 inches** (`INCHES_PER_SQUARE = 2`).
2. **Distance between squares is the Chebyshev distance** — the number of king's
   moves, diagonals costing the same as orthogonals — times the scale
   (`chebyshev_squares`, `distance_inches`).
3. **Converting an inches-long reach into squares rounds DOWN**
   (`reach_squares(inches) = inches // 2`). A 9" reach covers 4 squares (8"),
   never a 5th (10") the tabletop weapon could not touch: ranges stay *honest* —
   quantization may shave reach, but never grants any.

The scale is chosen so that **adjacency IS the engagement range**: 2" converts to
exactly 1 square, so "Chebyshev distance ≤ 1 — neighbours, diagonals count", the
definition the fight phase has enforced since ADR 0006, stops being a stated
convention and becomes the measured truth. No engagement behavior changes; its
justification does.

What the scale immediately enables (this PR): enforcing the shooting rules that
need distances. A shooting target must be within the weapon's range and unengaged,
and the shooter must itself be unengaged (04.02, 10.04; an engaged unit may only
shoot [CLOSE-QUARTERS] weapons per 10.06, and no unit in our data carries one, so
"engaged units cannot shoot" is faithful for our data, not a simplification of it).
The loader rejects out-of-range *scripted* shots at load time — positions are
static, so range is a static fact — while the engaged-shooting rules are enforced
by the engine on live state, because a fight turn that wipes a combat frees its
survivors to shoot legally on a later turn.

What the scale sets up (the movement plan, `docs/design/movement-and-charges.md`):
every distance movement needs is now well-defined. M6" is 3 squares of movement; a
D6" advance roll adds `reach_squares(roll)` squares; the HEAVY ability's "no model
moved more than 3"" threshold is "moved at most 1 square". The charge roll
quantizes cleanly: a charge target must be within the 2D6 roll's distance
(11.02/11.04), i.e. `chebyshev ≤ reach_squares(roll)` — and since any legal charge
target starts unengaged (chebyshev ≥ 2), a roll of 2 can never declare one, which
reproduces the Core Rules' "a double 1 never completes a charge" sidebar exactly,
with no special case.

## Considered Options

- **Euclidean distance (rounded).** Rejected: diagonal adjacency would be 2.83" —
  outside the 2" engagement range — contradicting the shipped fight-phase geometry
  in every scenario and test. Chebyshev is the metric the board already lives by.
- **1 square = 1".** Rejected: engagement range would be 2 squares, breaking
  "adjacency = engaged" (scenarios 08/09 and the fight tests all place engaged
  pairs adjacent), and the 12×8 board would span a mere 11" — inside every gun's
  range, making range enforcement vacuous.
- **Round inches-to-squares to nearest.** Rejected: a 9" weapon would reach
  10" — quantization must never *extend* a reach the real rules deny. Floor errs
  short, which only ever understates a weapon.
- **Keep range unenforced until movement.** Rejected: the movement PRs get
  strictly simpler if distances, range legality, and the engaged-shooting rules
  are already in place and regression-locked; and the loader catching an
  out-of-range scripted shot at authoring time is immediate value.

## Consequences

- `core/scenario.py` owns the scale, the metric, both conversions, and the two
  legality predicates (`in_engagement_range`, `in_weapon_range`); loader, engine
  and strategies all defer to them.
- Shooting eligibility (`GameState.eligible_shooters`) now also requires being
  unengaged and having at least one legal (weapon, target) pair, so the engine's
  phase loop can never deadlock on a unit with nothing legal to do; target menus
  and the heuristic's candidates come from the same `shootable_targets`
  definition the engine validates against.
- All nine shipped scenarios are unchanged (byte-identical transcripts at their
  demo seeds): every scripted and menu-reachable shot was already in range and
  unengaged, so enforcement is invisible until someone breaks a rule.
- The 12×8 board spans at most 11 squares = 22", so every 24"+ gun covers the
  whole battlefield. Range only bites for shorter weapons (Shoota/Fleshborer 18"
  = 9 squares) or once bigger boards arrive — fine for a tutorial, worth
  remembering when authoring range-lesson scenarios.
- Scenario authoring: positions are now rule-bearing. The loader fails fast on a
  scripted shot beyond range, naming the units, the distance and the range.
