---
name: add-scenario
description: Use this skill whenever adding a new tutorial scenario, creating a new teaching moment, designing a battle for the player to learn from, or writing a JSON file under data/scenarios/. Also use when modifying scenario pedagogy, picking which unit matchups to use for teaching a specific rule, or troubleshooting why a scenario is teaching the wrong thing. Covers the scenario JSON schema, pedagogical principles for this project, and a validation checklist.
---

# Adding a Tutorial Scenario

A scenario is a single teaching moment expressed as a small pre-positioned battle. **One scenario teaches one concept.** That's the whole game design philosophy.

## Pedagogical principles

1. **One new concept per scenario.** If a scenario introduces both AP and Sustained Hits, the player learns neither. Pick one. The next scenario adds the next one.

2. **The concept should be visible in the dice.** "AP cuts through saves" is a great teaching scenario because the player sees `5+ save → AP -2 → 7+ save → fails`. "Strategic positioning" is a bad teaching scenario for a tutorial because the lesson is abstract.

3. **Pick matchups that make the lesson obvious by contrast.** Teaching that Toughness matters? Use Ork Boyz (S4) shooting at Termagants (T3) — they wound on 3+. Then have them shoot Necron Warriors (T4) and wound on 4+, then Terminators (T5) and wound on 5+. The same attacker, three different defenders, the player sees the wound chart click.

4. **Short scenarios.** 1-3 turns. Long enough to demonstrate the concept, short enough to replay.

5. **Player controls the side that has the interesting decision.** If the lesson is "pick the right target," the player must be the one shooting. If the lesson is "AP hurts," the player should be the one being shot at so they feel saves failing.

## Schema

Scenarios live at `src/wh40k_tutorial/data/scenarios/<NN>_<slug>.json`. Number them by intended play order.

```json
{
  "id": "01_first_shots",
  "title": "First Shots",
  "teaches": "the four-step combat sequence: hit → wound → save → damage",
  "intro": "Plain-text intro shown before the battle begins. 2-4 sentences. Tell the player what concept they're about to learn and what to watch for.",
  "player_side": "attacker",
  "sides": {
    "attacker": {
      "faction": "space_marines",
      "units": [
        {
          "datasheet": "intercessor_squad",
          "position": [3, 4],
          "models": 5,
          "loadout": { "bolt_rifle": "all" }
        }
      ]
    },
    "defender": {
      "faction": "tyranids",
      "units": [
        { "datasheet": "termagants", "position": [9, 4], "models": 10 }
      ]
    }
  },
  "turns": [
    {
      "phase": "shooting",
      "active_side": "attacker",
      "narrate_before": "Your Intercessors raise their bolt rifles...",
      "actions": [
        { "attacker": "marines_1", "weapon": "bolt_rifle", "target": "termagants_1" }
      ]
    }
  ],
  "outro": "Shown when the scenario ends. Recap what the player just learned. Point to the next scenario."
}
```

Field reference:

- **id** — file name without extension. Stable identifier used in the CLI (`wh40k play 01_first_shots`).
- **teaches** — one sentence stating the single concept. If you can't say it in one sentence, the scenario is doing too much.
- **player_side** — `"attacker"` or `"defender"`. Determines which side uses `HumanStrategy`; the other uses `ScriptedStrategy`.
- **sides.*.units[].datasheet** — must match a key in the faction's JSON file. If it doesn't exist, add it first using the `add-unit` skill.
- **sides.*.units[].position** — `[x, y]` on the battlefield grid (currently 12 wide × 8 tall, 0-indexed from top-left).
- **sides.*.units[].loadout** — *optional* per-scenario loadout override. Same shape and rules as a datasheet's `default_loadout` (weapon keys that exist on the datasheet, `"all"` coverage only in v1), and it must include at least one ranged weapon. Omit it to use the datasheet's default. This is how a scenario arms a unit's wargear alternative — `05_sustained_hits` swaps the Immortals' gauss blasters for tesla carbines this way. Scripted actions and the player's weapon menu both honor it; a script firing a weapon outside the effective loadout fails at load time.
- **turns** — explicit list of turns. v1 only models the shooting phase, so most scenarios are one or two `"shooting"` entries.
- **turns[].actions** — optional. The fixed shots `ScriptedStrategy` replays, in order, when the *non-player* side acts: `attacker` is a unit id on the active side, `weapon` a ranged-weapon key on its datasheet, `target` a unit id on the other side (the loader validates all three). Omit it on turns the player acts in — the human decides. A scripted side that runs out of actions while it still has eligible shooters fails loudly at runtime, on purpose: script every shot you expect it to take.
- **narrate_before / outro** — write in our own words. Don't quote rulebooks.

## Workflow for adding a scenario

1. **Decide the concept.** Write the `teaches` sentence first. If it's vague, stop and sharpen it.

2. **Pick the matchup.** What units make the concept maximally visible? If the units don't exist yet in `data/factions/`, use the `add-unit` skill to add them. If you need to verify a unit's real profile, use the `rules-researcher` agent. If the lesson needs a unit's *alternative* wargear rather than its default (a keyword only the option carries, say), keep the datasheet's `default_loadout` as-is and equip the option with a per-scenario `loadout` override instead.

3. **Write the JSON.** Use an existing scenario as a template. Position units so the relevant weapons are in range.

4. **Write the intro and outro in plain language.** No jargon the player hasn't seen yet in earlier scenarios. The intro promises a lesson; the outro confirms it landed.

5. **Validate:** run `wh40k play <id>` end-to-end at least once. Verify the dice rolls demonstrate the concept — if you're teaching AP and the saves all happen to pass, the lesson is invisible. Either accept that variance and add narration that calls it out, or rig the scenario so the lesson is reliable (e.g., enough attacks that the expected outcome is overwhelmingly likely).

6. **Add a test.** Add a case to `tests/test_scenario.py` (see `TestPackagedScenarios`) that loads the scenario by id and asserts its key facts. The loader itself already guarantees the structure: referenced datasheets exist, model counts fit the datasheet's unit size, positions are on the 12x8 grid and don't collide, ids are unique, and any scripted `actions` are legal for the units on the board.

## Anti-patterns

- **The kitchen-sink scenario.** "This one teaches AP, rerolls, Lethal Hits, and target priority." No it doesn't, it teaches none of them.
- **The lecture scenario.** A wall of intro text explaining a rule, followed by one die roll. The dice should do the teaching; text should highlight what just happened.
- **The cheat scenario.** Using made-up units or stats to force a lesson. Use real units; if a real-units example doesn't demonstrate the concept cleanly, the concept may not be ready to teach yet.
