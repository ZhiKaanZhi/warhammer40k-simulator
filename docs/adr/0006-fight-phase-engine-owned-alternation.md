# The engine owns fight-phase alternation; strategies pick units; melee reuses the attack sequence

**Status:** accepted

The Fight phase is the first phase in which **both players act**. We decided the alternation protocol —
who picks first, how the pick passes across the table, that every eligible unit must fight, that
casualties land before the next pick — lives **in the engine** (`engine._run_fight_phase`), while each
`Strategy` is only ever asked the question it can meaningfully answer: *which of your eligible units
fights next, with which melee weapon, at which engaged target*. Within a fight turn the engine sets the
snapshot's `active_side` to whichever side is currently picking, so the existing strategy contract
("act for `state.active_side`") carries over unchanged; the scenario turn's own `active_side` means
"whose turn it is" and seeds who picks first, per the rulebook's Fight-step sequence (12.04).

Melee **resolution** is deliberately not new machinery: `resolve_melee` is a second thin entry point
over the shared `_resolve_attack_sequence` — the hit roll reads WS instead of BS through the same
`skill` field, and everything after is the shooting code. The shared record is renamed `AttackResult`
(from `ShootingResult`) to keep the name honest now that two phases produce it.

Engagement gets one project-wide definition, `core.scenario.in_engagement_range`: one grid square of
separation or less, diagonals included — the pre-positioning convention standing in for the
11th-edition 2" engagement range until movement fixes a squares-to-inches scale. The loader (a fight
turn needs an engaged starting pair), the engine (fight validation and eligibility), and the strategies
(target menus) all defer to it. Unlike weapon range — still an unenforced pre-positioning promise —
engagement **is enforced**, because it is not a distance nicety but the mechanic the whole phase runs on.

## Considered Options

- **Alternation inside strategies** (hand a strategy the whole phase and let it drive). Rejected: the
  ordering rules are game law, not preference; putting them behind the protocol would let a buggy or
  malicious strategy fight twice, skip a unit, or steal the opponent's pick. Strategies decide, engines
  enforce — the same boundary ADR 0005 drew for state.
- **A distinct `resolve_melee` pipeline.** Rejected: the rulebook's attack sequence (05) is one sequence
  for both; a second implementation would be a rules fork waiting to disagree. A test pins the
  equivalence: twin weapons, identical stats, one ranged one melee, identical records from one seed.
- **Explicit `engaged_with` declarations in scenario JSON.** Rejected: a second source of truth that can
  contradict the map the player is looking at. Positions already exist; adjacency is visible, checkable,
  and needs no new schema.
- **Modeling the Fights-First selection step now.** Rejected: no unit in the data has the ability and
  charges (its normal source) are out of scope, so the step is vacuously empty; the engine's entry order
  already matches the rulebook's hand-off for that case, and the docstring marks where the step slots in.

## Consequences

`ScenarioTurn` phases now include `"fight"`; in a fight turn the `actions` array scripts the
*opponent's* picks (both sides act, so a scripted action belongs to whichever side its acting unit is
on; the loader rejects scripts for the player's side). `Action` gains the kind `"fight"` with the same
fields as `"shoot"`. Per-phase activation tracking is per kind (`shot_this_phase` /
`fought_this_phase`), reset per turn entry. `HeuristicStrategy` cannot fight yet, and the loader says so
rather than letting a scenario find out at runtime. *(Amended 2026-07-18: the
heuristic now fights — same capped-expected-damage brain, candidates drawn from engaged targets only —
and the loader's guard became "no scripted fight actions under a heuristic opponent", since fight-turn
scripts always belong to the opponent.)* `core.models.melee_weapons` mirrors
`shootable_weapons` and falls back to the sheet's melee weapons when a loadout override names only guns —
swapping rifles must never disarm a unit in melee (04.01 gives every model one melee pick).
