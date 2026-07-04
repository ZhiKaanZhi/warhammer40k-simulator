# warhammer40k-simulator

An interactive terminal tutorial that teaches Warhammer 40,000 (11th edition) by playing it. You make decisions for one side; the other side is currently scripted. Every dice roll is narrated with the rule that drove it.

This is a learning tool, not a battle simulator. The goal is for a complete beginner to come out of half an hour of playing it actually understanding how 40k combat works.

## Status

**v1 complete (build phases 1–8).** Engine and content are both in: dice primitives, the validated loaders, the full shooting pipeline with the keyword-ability framework (Sustained Hits, Lethal Hits, Devastating Wounds with true mortal-wound resolution), the Rich interface, the scenario runner, and the narrator — plus six verified factions and a four-scenario teaching ladder. `wh40k play` walks a complete beginner from the bare combat sequence (First Shots) through the wound chart (Tougher Targets) and armour/invulnerable saves (Piercing Armour) to their first weapon ability (Lethal Hits), with every roll explained and deeper rules on demand. Further scenarios are pure data work; the heuristic AI opponent is the headline v2 feature. See `CLAUDE.md` for the architecture and build order.

## Quick start

```bash
pip install -e ".[dev]"
pytest                       # all tests should pass
wh40k list                   # see the available tutorial scenarios
wh40k play 01_first_shots    # play the first one (add --seed N for fixed dice)
wh40k demo                   # static preview of the tutorial interface
wh40k --help                 # CLI help
```

## What's in the box

- **Six factions, verified against the current rules:** Space Marines, Tyranids, Necrons, Orks, T'au Empire, Adeptus Mechanicus — each picked to demonstrate a different playstyle, every profile checked against the 10th-codex baseline plus the official 11th-edition Faction Pack errata.
- **Scenario-driven tutorials.** Each scenario teaches one concept (hit/wound/save/damage, AP, target priority, etc.).
- **Rich-based TUI.** Battlefield grid, action log, contextual rules panel — all in your terminal.
- **Extensible by design.** The strategy interface that currently drives scripted opponents is the same one a heuristic AI will plug into later.

## Out of scope for v1

Movement, charges, terrain, line of sight, stratagems, morale, list-building, graphical UI, LLM integration. Each is a defensible v2 addition. The point of v1 is to teach the combat loop.

## For contributors (and Claude Code)

Read `CLAUDE.md` first. It describes the architecture, the two extension points that matter, the build order, and the rules-accuracy policy.

The `.claude/` directory ships project-specific Claude Code subagents and skills — notably a `rules-researcher` agent that should be invoked any time you're encoding a 40k rule, and `add-scenario` / `add-unit` skills that walk through the data-authoring workflow.

## License

MIT.
