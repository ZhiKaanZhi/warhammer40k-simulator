---
name: add-unit
description: Use this skill whenever adding a new unit datasheet, weapon profile, or faction to the project. Triggers on any mention of adding an Intercessor / Termagant / Necron Warrior / Ork Boy / Fire Warrior or any other 40k unit, on editing files under data/factions/, on creating a new faction JSON file from scratch, or on questions about the unit JSON schema. Covers the schema, the workflow for sourcing real 11th-edition data, and validation.
---

# Adding a Unit Datasheet

Units live in `src/wh40k_tutorial/data/factions/<faction>.json`. One file per faction, multiple units inside.

## Schema

```json
{
  "faction": "space_marines",
  "display_name": "Space Marines",
  "units": {
    "intercessor_squad": {
      "display_name": "Intercessor Squad",
      "profile": {
        "movement": 6,
        "toughness": 4,
        "save": 3,
        "wounds": 2,
        "leadership": 6,
        "objective_control": 2
      },
      "unit_size": { "min": 5, "max": 10, "default": 5 },
      "weapons": {
        "bolt_rifle": {
          "display_name": "Bolt Rifle",
          "type": "ranged",
          "range": 24,
          "attacks": 2,
          "skill": 3,
          "strength": 4,
          "ap": 1,
          "damage": 1,
          "keywords": ["assault"]
        }
      },
      "default_loadout": { "bolt_rifle": "all" },
      "abilities": [],
      "notes": "Plain-line Intercessors. We're not modeling the Sergeant's special weapons in v1."
    }
  }
}
```

Field reference:

- **profile** — the unit-level stats. Match 11th-edition datasheet field names where reasonable: `movement` is M (inches), `toughness` is T, `save` is the armor save target (the "+" is implicit), `wounds` is W per model, `leadership` is the leadership target, `objective_control` is OC. Skip Invulnerable saves for v1 unless a scenario explicitly needs one — then add `invulnerable_save` to the profile.

- **unit_size** — min and max model count, plus a sensible default for tutorials.

- **weapons.*.skill** — WS for melee, BS for ranged. We collapse them into one field because the math is the same — it's the to-hit target. The `type` field disambiguates.

- **weapons.*.ap** — store as a **positive** integer representing the size of the modifier. Code applies it as a subtraction from the save. So AP -2 in the rulebook is `"ap": 2` here. This is the only place we deviate from rulebook notation and it's worth it for type-safety.

- **weapons.*.keywords** — lowercase, underscores for spaces. Use the canonical keyword names: `assault`, `heavy`, `rapid_fire_1`, `sustained_hits_1`, `lethal_hits`, `devastating_wounds`, `twin_linked`, `anti_infantry_4`, `blast`, `torrent`. If you're adding a keyword the engine doesn't yet support, also add a `TODO:` somewhere and don't claim the weapon "works" until the keyword is implemented.

- **abilities** — unit-level abilities. For v1, leave this empty or add `TODO:` entries. We're not modeling Oath of Moment, Reanimation Protocols, Synapse, etc. yet.

- **notes** — free-form. Document anything we deliberately simplified vs. the real datasheet. Future contributors will thank you.

## Workflow for adding a unit

1. **Verify the real profile.** Use the `rules-researcher` agent — pass it the unit name and ask for the current 11th-edition profile. Don't type stats from memory or from a Goonhammer article you skimmed; balance dataslates change profiles.

2. **Identify what to simplify.** Most real datasheets have a Sergeant or unit champion with different weapon options. For v1 tutorials, pick one loadout — usually the basic one — and document the simplification in `notes`. We are teaching mechanics, not list-building.

3. **Translate AP carefully.** Rulebook says "AP -1," our JSON says `"ap": 1`. Easy to get wrong.

4. **Add only the keywords the engine supports.** Check `src/wh40k_tutorial/core/combat.py` for what's implemented. If a unit's signature ability isn't supported yet and removing it would make the unit dishonestly weak, raise that with the user before adding the unit — maybe we should implement the keyword first, or maybe this unit waits for a later scenario.

5. **Run the schema test.** `pytest tests/test_datasheets.py` should validate that every unit JSON parses into our dataclasses without warnings.

## Faction starter set (v1 goal)

Six factions (all ✅ shipped in build phase 8), each chosen to demonstrate a different playstyle:

| Faction | v1 unit(s) | Teaches by example |
|---|---|---|
| Space Marines | Intercessor Squad | The balanced baseline. T4, Sv 3+, S4 AP-1 [ASSAULT, HEAVY] rifles. |
| Tyranids | Termagants | A horde. T3, Sv 5+, S5 [ASSAULT] fleshborers, weak individually. |
| Necrons | Necron Warriors + Immortals | Durable shooty with [LETHAL HITS] gauss — the first ability teachers. Immortals (T5, Sv 3+) are the wound-chart contrast target; their tesla option carries [SUSTAINED HITS 2] for a future lesson. Reanimation stays v2. |
| Orks | Boyz | Bad shooters (BS 5+), surprisingly tough (T5), scary in melee. |
| T'au Empire | Strike Team | Pure shooting (S5 pulse rifles). No melee answer at all. |
| Adeptus Mechanicus | Skitarii Rangers | Fragile but shielded: the first invulnerable save (4+ armour, 5++). |

All six exist with clean JSON, every profile verified 2026-07-04 (10th-codex baseline + official 11th Faction Pack errata scan — recipe in `.claude/agents/rules-researcher.md`), so v1 is content-complete on the data side.

## Anti-patterns

- **Pasting Wahapedia text into `notes`.** Paraphrase in your own words.
- **Inventing keywords.** If 11th edition doesn't have it, we don't have it.
- **"Close enough" stats.** A wound roll target is determined by the strength-to-toughness ratio; getting toughness wrong by 1 changes the whole math. Verify.
- **Mixing AP sign conventions.** Always store AP as a positive integer.
