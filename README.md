# warhammer40k-simulator

An interactive terminal tutorial that teaches Warhammer 40,000 (11th edition) by playing it. You make decisions for one side; the other side is currently scripted. Every dice roll is narrated with the rule that drove it.

This is a learning tool, not a battle simulator. The goal is for a complete beginner to come out of half an hour of playing it actually understanding how 40k combat works.

## Status

**Early scaffold.** The dice engine is implemented and tested; everything else is wired-up stubs with a clear build plan. See `CLAUDE.md` for the architecture and `CLAUDE.md`'s "Build order" section for what to implement next.

## Quick start

```bash
pip install -e ".[dev]"
pytest                       # all tests should pass
wh40k --help                 # CLI help
```

## What's in the box

- **Five factions planned for v1:** Space Marines, Tyranids, Necrons, Orks, T'au — each picked to demonstrate a different playstyle.
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
