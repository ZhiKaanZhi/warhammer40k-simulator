# warhammer40k-simulator

An interactive **terminal tutorial** that teaches Warhammer 40,000 (11th edition) by playing it. The player makes decisions for one side; the other side is scripted in the early teaching ladder and, from scenario 06 on, can be the **heuristic AI** — an expected-damage action picker (shots and fights alike) behind the same `Strategy` protocol, so scenarios choose their opponent without any engine change.

The goal is **learning**, not rules-accurate simulation. We narrate every dice roll and explain the rule that drove it. Accuracy of the rules we *do* model matters; completeness of the rule set does not.

## Status

All eight v1 build phases are implemented and tested — **v1 is complete**: dice primitives, the domain model with its validating JSON loader, the full shooting pipeline with the keyword-hook framework (Sustained Hits, Lethal Hits, Devastating Wounds with its mortal-wound track), the Rich UI shell, the scenario runner, the narrator, and the content: six verified factions and a seven-scenario teaching ladder (`01_first_shots` → `02_tougher_targets` → `03_piercing_armour` → `04_lethal_hits` → `05_sustained_hits` → `06_return_fire` → `07_devastating_wounds` → `08_first_blood` → `09_pick_your_fights`). **Phase 9 — the heuristic AI opponent — is in**: `HeuristicStrategy` greedily picks the shot with the highest expected damage (estimator in `core/expected.py`, Monte Carlo-tested against the pipeline), and `06_return_fire` is the first two-sided scenario, with the opponent chosen per scenario via `opponent_strategy`. **Phase 10 — the fight phase, v2's headliner — is in**: scenario turns may be `"fight"` turns, in which both sides act under the engine-owned alternation of the rulebook's Fight step (`resolve_melee` reuses the exact shooting attack sequence; ADR 0006, `docs/design/fight-phase.md`). `08_first_blood` is its teaching scenario: the player's Orks strike first and the Marines answer with survivors only (demo seed 20). The heuristic AI fights too — the same capped expected-damage pick, restricted to engaged targets, deadliest fight first — and `09_pick_your_fights` turns that into the ladder's capstone fight lesson: two combats, the player's first pick against the AI's arithmetic (demo seed 15: the right pick holds the Immortals to 12 dice; the wrong one eats all 20). **Phase 11 — distances & honest ranges — is in**: the grid gained a declared scale (ADR 0007: 1 square = 2", Chebyshev distance, inches-to-squares floors), making the fight phase's adjacency-as-engagement the measured 2" truth, and the shooting rules that need distances are enforced everywhere — a target must be in weapon range and unengaged, a shooter must be unengaged (04.02, 10.04) — by the loader (scripted shots, statically), the engine (live state), the menus and the heuristic, all deferring to the single definitions in `core/scenario.py`. All nine scenarios are byte-identical on their demo seeds. The movement arc it unlocks is designed and researched: `docs/design/movement-and-charges.md`. Adding scenarios or units is pure data work via the `.claude/skills`. See "Build order" below.

## Tech stack

- Python 3.11+
- [Rich](https://rich.readthedocs.io/) for the terminal UI
- [Click](https://click.palletsprojects.com/) for the CLI entry point
- [pytest](https://docs.pytest.org/) for tests
- Standard-library `dataclasses` for the domain model (no Pydantic — overkill here)

No web framework, no LLM, no graphical libraries. Keep it that way until a strong reason to add one appears.

## Commands

```bash
# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Run the CLI
wh40k

# Run the tests
pytest

# List scenarios, then play one (add --seed N for reproducible dice)
wh40k list
wh40k play 01_first_shots
```

## Repo layout

```
src/wh40k_tutorial/
├── core/           # Pure domain logic (loaders read JSON, nothing else does I/O)
│   ├── dice.py     # ✅ Implemented. Dice primitives. Heavily tested.
│   ├── models.py   # ✅ Implemented. Datasheet dataclasses + validating JSON loader.
│   ├── combat.py   # ✅ Implemented. The hit → wound → save → damage → mortals pipeline.
│   ├── abilities.py# ✅ Implemented. Keyword hooks (ADR 0002): Sustained/Lethal/Devastating.
│   ├── expected.py # ✅ Implemented. Expected-damage estimator mirroring the pipeline (Monte Carlo-tested).
│   └── scenario.py # ✅ Implemented. Scenario dataclasses + validating JSON loader.
├── engine.py       # ✅ Implemented. Runtime state, turn loop, fight-phase alternation (ADRs 0005/0006).
├── narrator.py     # ✅ Implemented. Pure formatter: the rule behind each step + "why?" expansions (ADR 0001).
├── strategies/     # How a side picks its actions each turn
│   ├── base.py     # ✅ Strategy protocol + frozen GameState snapshots — extension point for AI
│   ├── human.py    # ✅ Implemented. Prompts the player via Click menus.
│   ├── scripted.py # ✅ Implemented. Replays the scenario's scripted actions.
│   └── heuristic.py# ✅ Implemented. The AI opponent: greedy expected-damage shots and fights.
├── data/
│   ├── factions/   # JSON unit datasheets (one file per faction)
│   └── scenarios/  # JSON scenario definitions
├── ui/             # Rich-based TUI: battlefield grid, log, rules panel
│   ├── shell.py    # ✅ Implemented. Pure three-panel builders.
│   ├── live.py     # ✅ Implemented. Live-state presenters + per-volley report lines.
│   └── demo.py     # ✅ Implemented. Static scene behind `wh40k demo`.
└── cli.py          # ✅ Implemented. Click entry point: list / play / demo / version.
tests/              # Mirrors src/ layout
```

## Architecture: the two extension points that matter

Everything else is mechanical. Get these two right.

### 1. Combat as a pipeline

The attack sequence is `attacks → hits → wounds → saves → damage`. Each step is a pure function taking the previous step's result and returning the next. Special rules (Sustained Hits, Lethal Hits, AP, rerolls, modifiers) are **hooks into the relevant step**, never bare `if/elif` branches in a giant function. Melee proved the promise: `resolve_melee` and `resolve_shooting` are two thin entry points over one shared sequence (the hit roll reads WS or BS through the same field), and everything melee-*specific* — who fights when, engagement, casualty timing — is engine-level fight ordering (ADR 0006), not pipeline code. Adding an ability means writing a small hook and wiring it in — not modifying core combat code.

### 2. Strategy protocol

A `Strategy` is anything that, given the current game state, returns the next action for a side. We have `HumanStrategy` (prompts the player), `ScriptedStrategy` (replays a fixed sequence from the scenario file — the opponent of the early tutorials), and `HeuristicStrategy` (the AI: scores every legal shot by expected damage — `core/expected.py`, the analytic mirror of the combat pipeline, Monte Carlo-tested against it — capped at the target's remaining wounds, deterministic tie-break by scenario order). Scenarios pick their opponent with the `opponent_strategy` field; it slotted in with zero engine change, exactly as this section always promised. **Do not put player-input logic inside the engine.** It goes through this protocol.

## Build order

Each phase is independently shippable. Don't move on until the previous one has tests and works end-to-end.

1. **Dice primitives** ✅ done
2. **Domain model** ✅ done — datasheet dataclasses plus the validating JSON loader for `data/factions/*.json`
3. **Shooting pipeline** ✅ done — `combat.resolve_shooting(...)` returns the structured, step-by-step record the narrator will format (ADR 0001)
4. **Rich UI shell** ✅ done — the static three-panel layout (battlefield grid, action log, rules panel) behind `wh40k demo`
5. **Scenario runner** ✅ done — validating scenario loader, runtime state + turn loop in `engine.py` (ADR 0005), `HumanStrategy` and `ScriptedStrategy` behind the protocol, panels wired to live state; `wh40k list` / `wh40k play` work end to end
6. **Narrator** ✅ done — `narrator.py` turns each `ShootingResult` into five per-step explanations, printed inline under each fact line; a post-volley "deeper rule?" prompt expands any step, and the final shell's rules panel recaps the last volley
7. **Keyword hooks** ✅ done — `core/abilities.py` implements ADR 0002's per-step hook framework (before-roll tweaks with pipeline-owned sum-clamp-and-best-re-roll combination; after-roll pool adjustments) and the first three abilities: Sustained Hits X, Lethal Hits (auto-wound accepted by v1 policy inside the hook), and Devastating Wounds with the full mortal-wound resolution step (each critical wound's mortals applied after normal damage, capped to one model — no spillover, per rule 24.10). Other canonical keywords still load, validate, and stay inert.
8. **More scenarios + factions** ✅ done — six factions (Space Marines, Tyranids, Necrons, Orks, T'au Empire, Adeptus Mechanicus; seven units), every profile verified against the 10th-codex baseline plus the official 11th Faction Pack errata; plus the scenario ladder `02_tougher_targets` (wound chart by contrast), `03_piercing_armour` (AP vs the invulnerable floor), `04_lethal_hits` (the first ability), `05_sustained_hits` (the second critical-hit ability, armed through a per-scenario **loadout override** — scenarios can swap a unit onto its wargear alternative without touching the datasheet's default; see the add-scenario skill). Further content is pure data work via the add-unit / add-scenario skills.

9. **Heuristic AI opponent** ✅ done — held until after phase 8 exactly as planned (`ScriptedStrategy` kept the engine honest first): `core/expected.py` estimates a volley's mean damage with the pipeline's own targets and keyword semantics and is tested against `resolve_shooting`'s Monte Carlo mean; `strategies/heuristic.py` greedily takes the best capped-expected-damage shot; scenarios opt in with `opponent_strategy: "heuristic"`, and `06_return_fire` — the first two-sided scenario — teaches the enemy's target-priority arithmetic by letting the player feel it.

10. **Fight phase (v2)** ✅ done — `resolve_melee` over the shared attack sequence (twin-weapon test pins the equivalence); engine-owned Fight-step alternation per the 11th Core Rules 12.04 (active side picks first, sides alternate, a side with nothing eligible passes, fighting is mandatory, casualties land before the next pick); adjacency-as-engagement convention with one project-wide definition; fight menus and scripted fights behind the same Strategy protocol; the record renamed `AttackResult`. Design + verified findings: `docs/design/fight-phase.md`, ADR 0006. `08_first_blood` teaches it (player Orks vs Marines; the whole exchange, WS hit rolls, and the reduced return swing pinned at demo seed 20).

11. **Distances & honest ranges (v2)** ✅ done — ADR 0007 fixes the scale (1 square = 2"), the metric (Chebyshev) and the conversion (floor — quantization never extends a reach); `core/scenario.py` owns `distance_inches`, `reach_squares`, `in_weapon_range` and the now-derived `in_engagement_range`; the loader rejects out-of-range scripted shots at load time, the engine enforces range and both engaged-shooting rules on live state, and menus/heuristic draw from the same `shootable_targets` definition. Next up, designed and rules-verified: the movement & charges arc (`docs/design/movement-and-charges.md`) — PR #22 the Movement phase, #23 movement-linked weapon abilities ([ASSAULT]/[HEAVY]/[RAPID FIRE X]), #24 the Charge phase (which activates the fight engine's dormant Fights First step).

## Code conventions

- **Type hints on every function.** Use `from __future__ import annotations` at the top of each module.
- **Dataclasses with `frozen=True`** for value objects (`Weapon`, `Profile`). Mutable state lives in the runtime engine, not the data model.
- **Pure functions in `core/`.** No `print`, no file I/O, no `random` directly — dice go through `core.dice`. This is what makes the combat math testable.
- **Tests for every dice-affecting rule.** Use `pytest`'s parametrize. For probabilistic claims, test the distribution over 100k rolls, not single outcomes. See `tests/test_dice.py`.
- **Small functions.** If a function is over ~30 lines, it's probably hiding a missing abstraction.
- **No `Any`** unless genuinely unavoidable. No `**kwargs` shortcuts in domain code.

## Rules accuracy

Warhammer 40k 11th edition (released June 2026) is the reference. It is an evolution of 10th — the core hit/wound/save/damage math is shared — so 10th sources stay useful for unchanged mechanics, but anything edition-sensitive must be confirmed against 11th (see ADR 0004). When implementing a rule:

- If it's a core mechanic (hit roll, wound chart, AP, saves, damage), implement it exactly as written.
- If it's a unit-specific ability we haven't modeled yet, leave a `TODO:` with the rule name — don't fudge it.
- **Never invent rules.** If unsure, use the `rules-researcher` agent (see `.claude/agents/`) to look it up before coding.
- We paraphrase rules in our own words for the narrator. Do not paste GW or Wahapedia text verbatim.

## Scope discipline

This is a teaching tool. Things explicitly *out of scope* for v1:

- Movement and charge mechanics (scenarios are pre-positioned — for melee, pre-positioned *in engagement range*; distances and range enforcement DID land with ADR 0007, and the movement arc itself is designed in `docs/design/movement-and-charges.md`)
- Terrain and line of sight
- Stratagems, command points, detachment rules
- Morale/battle-shock
- Army list building / points costs
- A graphical UI
- An LLM opponent or commentary layer

Each of these is a sensible v2 addition. Resist adding them to v1.

## Skills and agents

`.claude/agents/rules-researcher.md` — Use when adding a unit, weapon, or ability and you need to confirm the actual 11th-edition profile or rule text. Searches the official Core Rules and Warhammer Community; treats Wahapedia as a 10th baseline (not yet updated to 11th). Returns structured data, never invents.

`.claude/skills/add-scenario/` — Walkthrough for writing a new tutorial scenario: what the JSON schema is, how to pick a single concept to teach, how to test it plays correctly.

`.claude/skills/add-unit/` — Walkthrough for adding a unit to a faction file: schema, where to find the data, validation steps.
