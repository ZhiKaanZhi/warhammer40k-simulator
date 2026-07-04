# Keyword abilities are per-step hooks; cross-step abilities split the pool and carry forward

**Status:** accepted — implemented in build phase 7 (`core/abilities.py`)

Weapon special rules (Sustained Hits, Lethal Hits, Devastating Wounds, etc.) are implemented as **small per-step functions ("hooks") looked up by keyword**, not as branches in the combat function and not as classes. After the pipeline computes a step (e.g. the hit roll), it finds any hooks registered for that step among the weapon's keywords and runs them. Adding an ability means writing one small function and adding one registry entry — the base combat code never changes.

Each step's base logic is **ability-agnostic**. It honors a small set of generic "carry" fields (e.g. `auto_wounds`, `no_save_wounds`) that default to zero, so a weapon with no abilities flows through unchanged.

**Two hook moments per step.** Every step (attacks, hits, wounds, saves, damage) exposes a *before-roll* moment and an *after-roll* moment. Before-roll hooks adjust how the dice are rolled — the die modifier, the re-roll policy, the attack count — and the **pipeline, not the hook, combines them**: it sums modifiers and clamps to ±1 net, and picks the single most-generous re-roll. After-roll hooks read the rolled result and split pools or add results (Sustained, Lethal, Devastating Wounds). Because before-roll combination is summation / most-generous (both commutative) and after-roll hooks read only immutable roll facts, hook order never changes the outcome.

**Hooks are sourced from both sides.** At each moment the pipeline gathers hooks from the attacker's weapon keywords *and* the defender's abilities (e.g. Feel No Pain is a defender-side damage-step hook). v1 models only attacker weapon-keyword hooks; defender abilities are named but inert. The framework gathers from both so defender-side rules drop in later without reshaping the pipeline.

**Keywords carry parameters.** Abilities like *Sustained Hits 1* vs *Sustained Hits 2* differ only by a number, so a keyword is a name plus an optional value, and one hook reads that value — rather than a separate function per number.

**Cross-step abilities** (triggered at one step, effect lands at a later step) are modeled as **pool-splitting at the trigger step plus a carry field the next step reads generically** — never as a hook that reaches forward into another step:

- *Lethal Hits*: a hit-step hook splits hits into `normal_hits` (still roll to wound) and `auto_wounds` (skip the wound roll). The wound step rolls the normal hits, then adds the auto-wounds — without knowing the word "Lethal."
- *Devastating Wounds* (11th edition = mortal wounds, per ADR 0004): the wound-step hook diverts critical wounds into a **separate mortal-wound track** that bypasses the save and damage steps entirely and resolves with its own (spilling) allocation. Same pool-splitting principle as above — the hook splits at the trigger step and a later stage honors the split — but the shortcut is a mortal-wound track, *not* a save-step `no_save_wounds` bucket (that bucket was the end-of-10th "no saves, normal damage" shape, retained only if a future "no-save but normal-damage" ability needs it). See `docs/design/shooting-pipeline.md`.

## Considered Options

- **Classes per ability with a method per step.** Rejected: most abilities touch one step, leaving most methods empty — ceremony with no payoff.
- **`if/elif` branches in `resolve_shooting`.** Rejected explicitly by CLAUDE.md; turns the core into a growing tangle and couples unrelated rules.
- **Hooks that directly mutate a later step.** Rejected: makes step order and data flow implicit and hard to test. Splitting the pool + carrying a data field keeps each hook local and each step's base logic pure.

## Consequences

Every step result type carries a small, ability-agnostic hand-off (normal vs shortcut buckets). Each hook is independently unit-testable against a single step. Effects that stack on the same trigger (e.g. Sustained + Lethal on one critical hit) must be designed to read the immutable `critical_hits` fact rather than each other's output, so hook order does not change the result.

`Weapon.keywords` must carry an optional numeric parameter (structured, not bare names). The dice primitive's natural-6-always-succeeds and hardcoded critical = 6 are hit/wound-roll assumptions; abilities that change the critical threshold (e.g. Anti-X) require adding a configurable crit threshold to `core.dice` and are deferred past v1.

**Primary-source note (2026-07-03, 11th Core Rules):** Sustained Hits and the mortal-wound shape of Devastating Wounds are confirmed as designed. One new wrinkle for the phase-7 hooks: the Lethal Hits auto-wound is a per-attack **choice** in 11th — an attacker may decline it so the attack can still roll for a critical wound and trigger Devastating Wounds. A v1 hook may default to always accepting, but the hook interface should not hard-code the auto-wound as mandatory. See `docs/design/shooting-pipeline.md`.
