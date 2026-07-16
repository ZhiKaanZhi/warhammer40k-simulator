# Fight Phase — Resolved Design

The first v2 mechanic (melee, the headliner). Decision of record: [ADR 0006](../adr/0006-fight-phase-engine-owned-alternation.md).
Rules verified 2026-07-16 against the official 11th-edition Core Rules PDF (see findings below and the
researcher's log in `.claude/agents/rules-researcher.md`). Vocabulary: [`CONTEXT.md`](../../CONTEXT.md).

## What it is

A scenario turn may now be a **fight phase** (`"phase": "fight"`). Unlike a shooting turn, **both players
act in it**: every engaged unit must fight exactly once, the players alternate picking which of their
units fights next, and casualties come off the table fight by fight — so a unit picked later swings with
only its surviving models. That last fact is the phase's central lesson.

Melee *resolution* is not new machinery: `core.combat.resolve_melee` is a second thin entry point over
the same `_resolve_attack_sequence` the shooting pipeline runs on (exactly as the shooting design
promised). The hit roll reads the weapon's WS instead of BS — same field, same dice — and every later
step (wound → save → damage → mortals) is byte-for-byte the shooting code. What *is* new is engine-level
**fight ordering**, which is where all the real rules content of the phase lives.

## Rules verification — findings (researched 2026-07-16, 11th Core Rules PDF)

Legend: ✅ confirmed & modeled · 📋 confirmed & recorded for later · ⚠️ edition change caught by research.

| Item | Result | Design impact |
|---|---|---|
| Fight phase shape (12.01–12.08) | ✅ Start → Pile In → **Fight** → Consolidate → End; both players act | We model the Fight step; Pile In / Consolidate are 3" moves → deferred with movement. |
| Fight step ordering (12.04) | ✅ Fights-First combats resolve first (alternating, **starting with the player whose turn it is**); then remaining combats alternate, starting with the player the sequence handed over to; a player with nothing eligible passes to the other | With no Fights First units anywhere, the active player carries the first pick into remaining combats → **active side picks first, then alternate, pass when empty.** The engine implements exactly this. |
| Fighting is mandatory | ✅ you must fight with every unit that can (pile in / consolidate are the optional parts) | The engine loops until no eligible unit remains; strategies choose *order and targets*, never whether. |
| Fight types (12.05/12.06) | ✅ Normal Fight needs the unit engaged; Overrun Fight is for un-engaged units and grants a pile-in move | Normal Fight only. Overrun needs movement → deferred; this is also why "was engaged at the start of the step" grants eligibility — without movement such a unit has nothing to reach, so we treat only currently-engaged units as eligible. |
| Engagement range (03.04) | ⚠️ **2" horizontally**, 5" vertically (widened in 11th) | On our grid: **adjacent squares (diagonals count)** = engaged, the pre-position convention until movement fixes a squares-to-inches scale. Distances confirmed visually on the rasterized page (numerals-as-graphics check). |
| Select weapons while fighting (04.01) | ✅ each model must pick exactly **one** melee weapon it has | One melee profile per activation. `core.models.melee_weapons` is the single definition of a unit's melee arsenal; a loadout override that names only guns falls back to the sheet's melee weapons — swapping rifles never disarms a unit in melee. |
| Select targets while fighting (04.02) | ✅ a melee weapon may only target units **engaged with its bearer**; several targets allowed, capped at the weapon's A, splitting declared up front | Single target per activation (matches the one-call-one-target pipeline shape); multi-target splitting deferred. Engagement is *enforced* — it is the phase's core mechanic, unlike shooting range which stays a pre-positioning promise. |
| Casualty timing (Destroyed) | ✅ a destroyed model is removed when destroyed; removal is deferred to end-of-attacks only for models with destruction-*triggered* rules | None of our units has such a rule, so casualties come off immediately → **the return swing counts only survivors.** The teaching moment the scenario ladder will build on. |
| Hit roll (05.01) | ✅ same roll either way — the target is the weapon's BS/WS | `resolve_melee` = `resolve_shooting` minus the weapon-type check. Proven by test: twin weapons (same stats, one ranged, one melee) produce identical records from the same seed. |
| Fights First (24.13) | 📋 unit-level ability (every model must have it); charging is what normally grants the effect | Named in the glossary, deferred with charges. No unit in our data carries it, so the Fights-First selection step is vacuously empty today; the engine documents where it slots in. |
| Shooting at engaged units (04.02, while shooting) | 📋 a shooting target must be **unengaged** (with exceptions for big things, 17.03) | Recorded for the future: when a scenario ever mixes shooting and fight phases over the same standing combat, the shooting turn must refuse engaged targets. No current scenario mixes them. |

## The flow

```
fight turn (active_side = whose turn it is)
└─ while any side has an eligible fighter:
     picker starts as active_side; a picker with nothing eligible passes back
     picker's Strategy chooses: unit → melee weapon → engaged target
     engine validates (kind, ownership, once-per-phase, melee & carried, engagement)
     resolve_melee → same AttackResult record → narrator explains WS, wound, save, damage
     casualties applied immediately; unit marked as having fought; pick passes across
```

**Eligibility** (one definition, `GameState.eligible_fighters`): alive, engaged with a surviving enemy,
carrying a melee weapon, not yet selected to fight this phase.

**Strategies.** `Action` gains the kind `"fight"` (same fields as `"shoot"`). `HumanStrategy` grows a
fight menu offering only legal picks; `ScriptedStrategy` replays fight actions from the scenario file. A
fight turn's `actions` array scripts **the opponent's** picks (the loader rejects scripts for the
player's side — the player picks their own fights); since both sides act in the turn, a scripted fight
belongs to whichever side its acting unit is on, regardless of `active_side`. `HeuristicStrategy` does
not fight yet — the loader rejects `opponent_strategy: "heuristic"` in scenarios with fight turns, and
teaching it melee (the estimator already mirrors the pipeline) is a natural follow-up.

**Record & presentation.** The shared record is now honestly named `AttackResult` (was
`ShootingResult`). The narrator was already skill-aware; it now also says *fights/attackers* where it
said *fires/firers*, and its melee attacks-expansion carries the one honesty note the simplification
needs: in the full game only models within engagement range swing — these pre-positioned scenarios put
the whole unit in reach, so every model fights.

## Deliberate simplifications (all documented in-game or in code)

- **Adjacency = engagement.** One grid square of separation or less, diagonals count
  (`core.scenario.in_engagement_range`, the single definition). Loader refuses a fight turn whose
  initial positions contain no engaged pair.
- **Whole units fight.** Real games count only models within engagement range; pre-positioned scenarios
  are staged fully engaged. The narrator's melee expansion says so.
- **Deferred, explicitly:** Pile In / Consolidate (3" moves), Overrun fights, Fights First, multi-target
  attack splitting, shooting-at-engaged enforcement (no mixed-phase scenario exists yet), heuristic
  melee.

## Edge cases

- A unit whose combat partner is wiped mid-phase stops being eligible (nothing in reach; Overrun is the
  rulebook's answer and needs movement).
- The phase ends the instant a side is wiped; unconsumed script entries are never consulted.
- Per-phase activation sets (`shot_this_phase` / `fought_this_phase`) reset per turn entry: the same
  unit may shoot in one turn and fight in the next.

## Verification

- 334 tests: alternation order, pass-back, once-per-phase, casualty timing (the return swing's model
  count equals the first fight's survivors — an identity independent of the dice), engagement
  validation, kind-vs-phase mismatches, loader rules, menus, and the twin-weapon
  shooting-equivalence proof.
- The seven shipped scenarios are **byte-identical** on their demo seeds (01–04 seed 1, 05 seed 5, 06
  seed 11, 07 seed 6): the fight machinery draws no dice in shooting paths.
- Manual end-to-end run of a throwaway two-sided fight scenario through the real CLI: turn banner, fight
  menus, scripted return swing with the reduced model count, WS narration, final shell.

## Next steps

1. **Scenario 08** (next PR): the first fight-phase teaching scenario — Space Marines vs Ork Boyz
   (choppas: A3 WS3+ S4 AP-1 — the faction built for this), one fight turn, demo seed chosen so the
   strike-order lesson is unmistakable.
2. A later scenario can teach the *ordering decision itself* (two combats, the player chooses which
   fight happens first).
3. Heuristic melee, then movement/charges — which unlock Pile In, Overrun, and Fights First.
