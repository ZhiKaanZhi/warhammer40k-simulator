# warhammer40k-simulator

An interactive terminal tutorial that teaches Warhammer 40,000 (11th edition) by playing it. You make decisions for one side; the other side is currently scripted. Every dice roll is narrated with the rule that drove it.

This is a learning tool, not a battle simulator. The goal is for a complete beginner to come out of half an hour of playing it actually understanding how 40k combat works.

## Status

**v1 complete (build phases 1–8).** Engine and content are both in: dice primitives, the validated loaders, the full shooting pipeline with the keyword-ability framework (Sustained Hits, Lethal Hits, Devastating Wounds with true mortal-wound resolution), the Rich interface, the scenario runner, and the narrator — plus six verified factions and a five-scenario teaching ladder. `wh40k play` walks a complete beginner from the bare combat sequence (First Shots) through the wound chart (Tougher Targets) and armour/invulnerable saves (Piercing Armour) to the critical-hit weapon abilities (Lethal Hits, then Sustained Hits via a per-scenario loadout override), with every roll explained and deeper rules on demand. **The v2 headliner is in:** a heuristic AI opponent that picks each shot by expected damage, and `06_return_fire` — the first two-sided scenario, where the T'au shoot back and the player watches target priority happen to them. Further scenarios are pure data work. See `CLAUDE.md` for the architecture and build order.

## Play it on your machine (nothing assumed)

You need **Python 3.11 or newer** and this folder of code. Step by step:

1. **Install Python** from https://www.python.org/downloads/ and run the installer.
   On Windows, tick **"Add python.exe to PATH"** on the first installer screen — it matters.
   (macOS/Linux may already have it: `python3 --version` in a terminal should say 3.11+.)

2. **Get the code.** Either `git clone https://github.com/ZhiKaanZhi/warhammer40k-simulator`,
   or press **Code → Download ZIP** on the GitHub page and unzip it.

3. **Open a terminal in the project folder.**
   Windows: Start menu → type `powershell` → Enter, then `cd` to the folder
   (e.g. `cd C:\Users\you\warhammer40k-simulator`). macOS/Linux: any terminal, then `cd` likewise.

4. **Install the game** (one time).
   - Windows: `py -m pip install -e .`
   - macOS/Linux (the virtual environment avoids the "externally managed environment" error):

     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     pip install -e .
     ```

     Run `source .venv/bin/activate` again whenever you open a new terminal here.

5. **Play.**

   ```bash
   wh40k list                   # see the tutorial scenarios, in order
   wh40k play 01_first_shots    # start at the beginning
   ```

   Menus are numbered — type the number and press Enter. After each volley, the
   `Deeper rule?` prompt accepts a step name (`hit`, `wound`, `save`, ...) to print the
   full rule behind it, or just Enter to carry on. Add `--seed 5` to any `play` command
   for a repeatable battle.

If `wh40k` isn't recognized, run it as `python -m wh40k_tutorial.cli list`
(Windows: `py -m wh40k_tutorial.cli list`). To update later, `git pull` in the folder
(or re-download the ZIP) — the editable install picks changes up automatically; if a
new version won't start, re-run the install command from step 4.

## Quick start (developers)

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
- **Extensible by design.** Scripted opponents, the human player, and the heuristic AI all sit behind one strategy interface; scenarios choose their opponent with a single `opponent_strategy` field.

## Out of scope for v1

Movement, charges, terrain, line of sight, stratagems, morale, list-building, graphical UI, LLM integration. Each is a defensible v2 addition. The point of v1 is to teach the combat loop.

## For contributors (and Claude Code)

Read `CLAUDE.md` first. It describes the architecture, the two extension points that matter, the build order, and the rules-accuracy policy.

The `.claude/` directory ships project-specific Claude Code subagents and skills — notably a `rules-researcher` agent that should be invoked any time you're encoding a 40k rule, and `add-scenario` / `add-unit` skills that walk through the data-authoring workflow.

## License

MIT.
