# The engine owns all mutable state; strategies see frozen snapshots, observers see frozen events

**Status:** accepted

Build phase 5 introduces the first mutable state in the project. We decided to fence it inside one module: `engine.py` holds `UnitRuntime` / `BattleState` (models left, wounds on the lead model, who has shot this phase) and the turn loop. Everything crossing the engine's boundary is frozen:

- **Strategies get immutable `GameState` snapshots** (built fresh per decision) and return `Action`s. They can never mutate the battle. Shooting *eligibility* (alive, has a ranged weapon, hasn't activated this phase) is defined once, on `GameState`, and the engine's own loop uses that same snapshot method — so the loop, `HumanStrategy`'s menus, and any future AI can't disagree about who may shoot.
- **The engine validates every returned action** (right side, existing ranged weapon, surviving enemy target, one activation per phase) and raises `EngineError` on an illegal one. Strategies are treated as untrusted input: a buggy script or future AI fails loudly instead of corrupting state.
- **Presentation observes via optional callbacks** (`on_turn_start`, `on_volley`) that receive frozen records — a `VolleyEvent` carries the full `ShootingResult`. The engine never prints; the CLI/UI layer formats.
- **Scripted opponents replay data, never improvise.** A scenario turn entry may carry an optional `actions` list, validated eagerly by the scenario loader against the datasheets on the board. `ScriptedStrategy` replays them in order and **raises when the script runs dry** rather than inventing a move, so an under-scripted scenario fails in testing instead of silently drifting from its lesson.

Two v1 simplifications are deliberate and documented in `engine.py`: weapon **range is not enforced** (scenarios are pre-positioned in range; enforcement arrives with movement, which must also fix the grid-squares-to-inches convention), and **one activation fires one weapon profile** (no current unit carries two ranged guns; multi-weapon activations are an engine-loop change, not a pipeline change).

## Considered Options

- **Strategies operate on the live state.** Rejected: one misbehaving strategy could corrupt the battle, and the Strategy protocol's whole point is that the engine trusts nothing behind it.
- **A generator/event-stream runner instead of callbacks.** Rejected: interleaving human prompts (which happen *inside* `choose_action`) with yielded display events complicates the control flow for no gain; two optional callables keep `run_scenario`'s return value the final state.
- **ScriptedStrategy falls back to a default policy when its script runs out.** Rejected: a silent default can quietly change what a tutorial demonstrates; exhaustion is an authoring bug and should fail loudly.

## Consequences

`GameState` (in `strategies/base.py`) grew from a placeholder to real snapshot types; it is the vocabulary strategies and presenters share. The scenario schema gained the optional per-turn `actions` array (documented in the add-scenario skill). Tests can assert exact battles by seeding one `random.Random` and replaying the same calls the engine makes.
