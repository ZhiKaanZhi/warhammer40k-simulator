# Shooting Pipeline — Resolved Design

Outcome of a grilling session (2026-06-30). Implements **Phase 3** of the build order in `CLAUDE.md`.
Decisions of record: [ADR 0001](../adr/0001-shooting-pipeline-returns-teachable-record.md),
[ADR 0002](../adr/0002-keyword-abilities-as-per-step-hooks.md),
[ADR 0003](../adr/0003-saving-throws-and-the-dice-primitive.md). Vocabulary: [`CONTEXT.md`](../../CONTEXT.md).

## What it is

`resolve_shooting` turns **one weapon's** shooting into a structured, *teachable record*. It is the single
source of truth for the rules; the narrator only formats facts into English (ADR 0001).

## Scope of one call

One weapon profile, fired by N identical models, at one target unit. Mixed-weapon units (e.g. a sergeant
with a different gun) are several calls made by the engine, so every die in a pool shares one target number.

## The pipeline

```
attacks → hits → wounds → saves → damage
```

Each step runs in three beats: **(1)** before-roll hooks adjust how we roll → **(2)** roll via `core.dice`
→ **(3)** after-roll hooks read/split the result. Each step result is a frozen dataclass carrying its
`RollResult`, the facts that drove its target, and any carry buckets for the next step.

| Step | Target driven by | Records (facts) | Carry to next step | Example hooks |
|---|---|---|---|---|
| Attacks | `weapon.attacks` (may be `DiceExpr`) | rolled count, the expression | `total_attacks` | Rapid Fire *(deferred)* |
| Hits | `weapon.skill` (BS/WS) | `RollResult`, hits, `critical_hits` | `normal_hits`, `auto_wounds` | +1 to hit, reroll 1s; Sustained, Lethal |
| Wounds | `wound_target(S,T)` | `RollResult`, S, T, wounds, `critical_wounds` | `savable_wounds`, `no_save_wounds` | +1 to wound; Devastating Wounds; Anti-X *(deferred)* |
| Saves | `save_target(Sv,AP,Inv)` | `RollResult`, Sv, AP, invuln, failed | failed saves → damage | cover *(deferred)*; impossible-save branch |
| Damage | `weapon.damage` (may be `DiceExpr`) | dmg/failed save, models slain, leftover wounds, **wasted** | updated defender state | Melta, Feel No Pain, −1 dmg *(deferred)* |

## Variable values (Attacks / Damage)

`weapon.attacks` and `weapon.damage` may be a fixed `int` *or* a small frozen `DiceExpr` (`"D3"`, `"D6"`,
`"D6+1"`, `"2D6"`). The pipeline rolls them so the random value lands inside the record as its own teaching
moment. Needs a new `core.dice.roll_dice_expr` helper — the existing `roll_d6` only does pools-vs-target.

## Hook framework (ADR 0002)

- One small function per ability, looked up by keyword **name**; parametric abilities (Sustained Hits **1**
  vs **2**) read the keyword's **value**.
- **Two moments per step** (before / after roll). The pipeline owns combination: **sum** modifiers and
  **clamp to ±1**; pick the **single most-generous** re-roll. Both ops commute → hook order is irrelevant.
- Sourced from the attacker's **weapon keywords** *and* the defender's **abilities** (v1 = weapon keywords
  only; defender abilities named but inert).
- **Cross-step abilities** split the pool into normal/shortcut buckets at the trigger step; the later step
  honors the bucket generically (Lethal → `auto_wounds`, Devastating Wounds → `no_save_wounds`).

## Saves & AP (ADR 0003)

- AP worsens the save target, is exempt from the ±1 modifier cap, and does not touch invuln; the defender
  uses the better save.
- Best save **7+** → *no save*: all wounds fail, **no dice rolled** (avoids crashing the primitive and the
  misapplied natural-6 rule).

## Damage allocation

Each failed save deals Damage to **one** model; fill a model before starting the next; **no spillover**
between models; excess on a dying model is **wasted** and recorded. The step returns the updated defender
state (survivors, lead model's remaining wounds) so the engine can thread several weapons against one unit.

## Signature & determinism

```python
resolve_shooting(
    attacker, attacker_model_count, weapon,
    defender, defender_wounds_remaining, defender_model_count,
    rng=None,                      # threaded to core.dice for deterministic tests
) -> ShootingResult
```

Datasheets are passed whole (for narration + future unit-level hooks) even though v1 mechanics read only
`weapon`, the profile stats, and the counts. A shared internal `_resolve_attack_sequence` backs both this
and a future `resolve_melee` — melee adds only engine-level fight ordering, not a new pipeline shape.

## Edge cases

- **Zero counts cascade** (0 hits → roll 0 to wound → …); each step still yields a valid, narratable empty record.
- **Impossible save** → no-save branch (above).
- **Overkill** → `wasted` damage field.

## Deferred past v1 (explicit)

- **Rapid Fire / Melta** — need distance-to-target; v1 is pre-positioned but doesn't feed range bands in.
  (Also settle flat-modifier vs random-attacks ordering when added.)
- **Anti-X** — needs a configurable critical threshold in `core.dice` (currently hardcoded to 6).
- **Feel No Pain & other defender abilities** — defender-side hooks; the framework allows them, v1 leaves them inert.
- **Cover / save die-modifiers** — out of v1 (no terrain). If added, the save step must stop trusting
  `roll_d6`'s natural-6 success.
- **Blast, unit/army auras, stratagems** — out of v1 scope per `CLAUDE.md`.

## Rules verification — findings (researched 2026-06-30)

**Edition: 11th edition is released and current as of 2026-06-30** (launched June 2026, "Armageddon" box; free
Core Rules PDF on Warhammer Community). GW frames it as an *evolution* of 10th — the core hit/wound/save math is
unchanged; the procedural changes are in charges, objectives, terrain, and battleshock (all out of v1 scope).
Wahapedia still hosts only 10th, so it remains authoritative for the unchanged baseline but NOT for current 11th
text. **The project now targets 11th edition (decided 2026-06-30 — see [ADR 0004](../adr/0004-target-11th-edition.md)).**

Legend: ✅ confirmed & matches design · ⚠️ changed/needs design update · 🔎 verify in the 11th Core Rules PDF before coding.

| Item | Result | Design impact |
|---|---|---|
| Sustained + Lethal on one crit | ✅ both fire off the same unmodified 6; Sustained's *extra* hits are **not** crits (only the natural 6 auto-wounds) | Confirms "read immutable `critical_hits`" (ADR 0002); Sustained adds *normal* hits. |
| Lethal Hits | ✅ auto-wounds (skips wound roll); **saves still apply** | Matches the `auto_wounds` bucket. |
| Variable Attacks | 🔎 rolled **per model** (each model rolls its own), not once for the pool — 10th-confirmed, 11th unverified | `AttackStep` must record per-model rolls, not one roll. **Touches Phase 3.** |
| Damage no-spillover | ✅ excess on a slain model is lost; one-at-a-time — **but mortal wounds are the exception (they spill over)** | Matches `wasted`. Mortal-wound path needs a *separate, spilling* allocation. |
| Modifier cap | ✅ ±1 net on hit/wound. Saves: **+1 improvement cap only**, no symmetric −1 (worsening is AP, uncapped) | Clamp save *improvements* to +1; never clamp AP. |
| Re-rolls | ✅ once only; "re-roll failed" ⊃ "re-roll 1s" | Confirms "most generous" combination (ADR 0002). |
| AP | ✅ modifies save, uncapped, ignores invuln | Confirms ADR 0003. |
| No critical-save rule | ✅ **confirmed: no "unmodified 6 always saves"**; unmod 1 always fails; 7+ unsavable | Confirms ADR 0003's core premise. 🔎 11th advertises "Save Groups" — appears procedural, not an auto-6; confirm in PDF. |
| Anti-X | ✅ unmod wound of X+ counts as a Critical Wound vs the keyword; does **not** itself bypass saves | Confirms deferred Anti-X note; needs configurable crit threshold in `core.dice`. |
| **Devastating Wounds** | ⚠️ **11th = MORTAL WOUNDS** (reverted from end-of-10th "no saves of any kind"). 🔎 confirm wording + spillover in PDF | **Material change — see below.** |

### The one material change: Devastating Wounds

History: 10th launch = mortal wounds → autumn-2023 dataslate (what Wahapedia shows today) = "no save of any kind,
normal damage, no spillover" → **11th reverted to mortal wounds.** Since the project now targets 11th (ADR 0004),
**Devastating Wounds = mortal wounds** is the committed behavior:

- a critical wound (unmodified 6, or the Anti-X threshold) is diverted at the wound step into a **separate
  mortal-wound track** that bypasses saves entirely;
- mortal wounds are allocated one at a time and **spill over** between models in the unit (unlike normal damage,
  whose excess on a slain model is wasted), with Feel No Pain still applying;
- so this is **not** the `no_save_wounds` save-step bucket (that was the end-of-10th shape) — it needs its own
  mortal-wound resolution path alongside the normal save/damage steps.

Devastating Wounds is a **Phase-4** ability, so it does **not block Phase 3**. 🔎 Confirm the exact 11th wording
and the mortal-wound spillover/allocation order against the Core Rules PDF before implementing it.

### Sources

- Warhammer Community — new-edition reveal (AdeptiCon 2026) & "Download the free Core Rules now."
- Warhammer Community — "Weapons Rules Are Fun and Flexible" (11th; confirms Dev Wounds = mortal wounds, crit thresholds, Anti-X).
- Wargamer — 11th-edition abilities / full guide (secondary). Wahapedia 10th + datacard.app (10th baseline).
- ⚠️ Researcher could not read the 11th Core Rules PDF (JS/403), so 🔎 items rest on secondary sources and need a one-time PDF check.

## Next steps

1. ✅ **Edition decided: 11th** (2026-06-30, [ADR 0004](../adr/0004-target-11th-edition.md)). Core math is
   unchanged, so the dice module and this design stand; the only affected ability is Devastating Wounds
   (Phase 4, above).
2. **Clear the three 🔎 PDF items** against the 11th Core Rules PDF before coding the affected parts: per-model
   variable Attacks (#3, Phase 3), Devastating Wounds wording + mortal-wound spillover (#9, Phase 4), and confirm
   there's no critical-save rule despite the advertised "Save Groups" (#8).
3. **Start Phase 3:** implement `resolve_shooting` with **no keywords**, threading `rng`, proving the record →
   narrator loop. Per-model variable Attacks (#3) is the only finding that touches Phase 3.
