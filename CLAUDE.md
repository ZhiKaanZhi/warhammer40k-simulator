# warhammer40k-simulator

An interactive **terminal tutorial** that teaches Warhammer 40,000 (11th edition) by playing it. The player makes decisions for one side; the other side is currently scripted but the architecture is designed so a heuristic AI can drop in later without changing scenarios.

The goal is **learning**, not rules-accurate simulation. We narrate every dice roll and explain the rule that drove it. Accuracy of the rules we *do* model matters; completeness of the rule set does not.

## Status

Early scaffold. The dice module is implemented; everything else is a typed stub with `TODO:` markers describing what to build next. See "Build order" below.

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

# Run a specific scenario directly
wh40k play 01_first_shots
```

## Repo layout

```
src/wh40k_tutorial/
├── core/           # Pure domain logic, no I/O
│   ├── dice.py     # ✅ Implemented. Dice primitives. Heavily tested.
│   ├── models.py   # Unit, Weapon, Model dataclasses
│   └── combat.py   # The hit → wound → save → damage pipeline
├── strategies/     # How a side picks its actions each turn
│   ├── base.py     # Strategy protocol — extension point for AI
│   ├── human.py    # Prompts the player via CLI
│   └── scripted.py # Reads moves from the scenario file
├── data/
│   ├── factions/   # JSON unit datasheets (one file per faction)
│   └── scenarios/  # JSON scenario definitions
├── ui/             # Rich-based TUI: battlefield grid, log, rules panel
└── cli.py          # Click entry point
tests/              # Mirrors src/ layout
```

## Architecture: the two extension points that matter

Everything else is mechanical. Get these two right.

### 1. Combat as a pipeline

The shooting sequence is `attacks → hits → wounds → saves → damage`. Each step is a pure function taking the previous step's result and returning the next. Special rules (Sustained Hits, Lethal Hits, AP, rerolls, modifiers) are **hooks into the relevant step**, never bare `if/elif` branches in a giant function. The melee sequence reuses the same pipeline with one extra step. Adding an ability means writing a small hook and wiring it in — not modifying core combat code.

### 2. Strategy protocol

A `Strategy` is anything that, given the current game state, returns the next action for a side. We currently have `HumanStrategy` (prompts the player) and `ScriptedStrategy` (replays a fixed sequence from the scenario file, used for the AI side in tutorials). A future `HeuristicStrategy` will score candidate actions using the same combat math the engine uses for dice resolution, and slot in without any other change. **Do not put player-input logic inside the engine.** It goes through this protocol.

## Build order

Each phase is independently shippable. Don't move on until the previous one has tests and works end-to-end.

1. **Dice primitives** ✅ done
2. **Domain model** — `Unit`, `Weapon`, `Model` dataclasses; JSON loader for `data/factions/*.json`
3. **Shooting pipeline** — implement `combat.resolve_shooting(attacker, target, weapon)` returning a structured result that the narrator can describe step by step
4. **Rich UI shell** — a static three-panel layout (battlefield grid, action log, rules panel). Hard-code one scene first; wire it to live state second.
5. **Scenario runner** — load a scenario JSON, run alternating turns, route decisions through `Strategy`. Tutorial scenarios use `HumanStrategy` for the player and `ScriptedStrategy` for the opponent.
6. **Narrator** — for each dice roll, print the rule that determined it. Inline by default; deeper "why?" expansion available on demand.
7. **More scenarios + factions** — once one scenario works end-to-end, add the rest. This is data work, not code work.

Only *after* phase 7 do we consider the heuristic AI opponent. Don't be tempted earlier — `ScriptedStrategy` is enough for tutorials and forces the engine to stay clean.

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

- Movement and charge mechanics (scenarios are pre-positioned)
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
