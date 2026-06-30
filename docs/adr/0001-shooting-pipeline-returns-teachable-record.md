# Shooting pipeline returns a teachable record of facts; the narrator owns all prose

**Status:** accepted

The shooting resolution is the heart of a *teaching* tool, so it must explain every dice roll, not just compute who died. We decided `resolve_shooting` returns a structured, step-by-step record (`AttackStep → HitStep → WoundStep → SaveStep → DamageStep`) that carries the raw dice faces and the *inputs that drove each target* (e.g. Strength and Toughness behind a wound target), not merely the final outcome. The narrator is a pure formatter that turns those structured facts into English; it holds no game logic.

## Considered Options

- **Return only the outcome ("1 model died").** Rejected: the narrator would have to re-derive *why* each step happened, duplicating rules logic outside the tested core.
- **Embed English explanation strings inside the record.** Rejected: it pushes presentation into the pure `core/` domain (violating the "no print / core is pure" rule in CLAUDE.md) and forces edits to combat code whenever wording changes.

## Consequences

Game rules live in exactly one tested place (`core/combat.py`); all teaching prose lives in one editable place (the narrator/UI layer). Each step type must record the few raw inputs (e.g. `strength`, `toughness`) that aren't already on its `RollResult`.
