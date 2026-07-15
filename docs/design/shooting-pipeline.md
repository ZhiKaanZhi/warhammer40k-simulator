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

**Damage: implemented.** `weapon.damage` is a frozen `DiceValue` (`core/models.py`) — a fixed `int` *or* a
small dice value (`"D3"`, `"D6"`, `"D6+1"`, `"2D6"`; only D3/D6 dice accepted by the loader). The JSON accepts
either form and the loader coerces, so `"damage": 1` and `"damage": "D3"` both work and bad notation fails at
load time naming the weapon. The damage step rolls it **per failed save** and the mortal-wound step **per
critical wound**, recording each rolled value in `DamageStep.rolls` / `MortalWoundsStep.rolls` so the random
value lands inside the record as its own teaching moment (the narrator prints "D3 rolled 2"). A fixed value
draws no dice at all, which is what keeps every pre-existing seeded scenario byte-identical. `DiceValue.average`
is what `core/expected.py` reads, so the AI scores a D3 gun as its mean.

No `core.dice` helper was needed: `roll_d6` does pools-vs-target, which is a different job — `DiceValue.roll`
owns "sample this characteristic" and is the only other place a die is drawn.

**Attacks: still deferred.** `weapon.attacks` stays a fixed `int` (the loader rejects `"D6"` attacks). Variable
attacks are rolled *per model* (finding #3 below), so `AttackStep` must record one roll per model rather than
one for the pool — a bigger change than Damage, and no shipped unit needs it yet.

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

Legend: ✅ confirmed & matches design · ⚠️ changed/needs design update. All three former 🔎 items were resolved
against the official 11th Core Rules PDF on **2026-07-03** (see *Primary-source verification* below).

| Item | Result | Design impact |
|---|---|---|
| Sustained + Lethal on one crit | ✅ both fire off the same unmodified 6; Sustained's *extra* hits are **not** crits (only the natural 6 auto-wounds) | Confirms "read immutable `critical_hits`" (ADR 0002); Sustained adds *normal* hits. |
| Lethal Hits | ✅ auto-wounds (skips wound roll); **saves still apply** | Matches the `auto_wounds` bucket. |
| Variable Attacks | ✅ **per weapon/model** at the Core Rules level: attack dice are gathered weapon by weapon (04.03), and the re-roll rules treat the roll that determines a weapon's attack count as belonging to that one weapon. The dedicated *Random Characteristics* entry lives in the Rules Commentary, **which 11th has not published yet** (checked 2026-07-03) — re-check its exact wording when it appears | When variable attacks are implemented, `AttackStep` must record one roll per model. Shipped code deliberately defers dice-valued attacks (loader rejects them), so **no code change today**. Variable *Damage* is implemented (rolled per failed save / per critical wound) — it has no per-model subtlety. |
| Damage no-spillover | ✅ excess on a slain model is lost; one-at-a-time. General mortal wounds (06.02) *do* spill, **but Devastating Wounds mortals (24.10) are capped at one model per critical wound — no spillover** | Matches `wasted`. Mortal-wound path is separate but *non-spilling*: each crit's Damage-many mortals fill one model, overkill wasted. |
| Modifier cap | ✅ ±1 net on hit/wound. Saves: **+1 improvement cap only**, no symmetric −1 (worsening is AP, uncapped) | Clamp save *improvements* to +1; never clamp AP. |
| Re-rolls | ✅ once only; "re-roll failed" ⊃ "re-roll 1s" | Confirms "most generous" combination (ADR 0002). |
| AP | ✅ modifies save, uncapped, ignores invuln | Confirms ADR 0003. |
| No critical-save rule | ✅ **confirmed at the primary source, visually** (save table, 05.04): an unmodified 1 always fails and there is no critical-save row; a save succeeds only via the invulnerable value (raw die, never AP-modified) or the AP-modified armour value | ADR 0003 fully confirmed. "Save Groups" turned out to be **allocation groups** (05.03) — pure allocation procedure, see below; zero v1 impact. |
| Anti-X | ✅ unmod wound of X+ counts as a Critical Wound vs the keyword; does **not** itself bypass saves | Confirms deferred Anti-X note; needs configurable crit threshold in `core.dice`. |
| **Devastating Wounds** | ✅ **confirmed (24.10): mortal wounds.** A critical wound ends that attack's sequence and the target suffers mortal wounds equal to the weapon's Damage, applied *after* the volley's normal damage is resolved | Matches the committed design — see below for the confirmed allocation semantics. |

### The one material change: Devastating Wounds

History: 10th launch = mortal wounds → autumn-2023 dataslate (what Wahapedia shows today) = "no save of any kind,
normal damage, no spillover" → **11th reverted to mortal wounds.** Since the project now targets 11th (ADR 0004),
**Devastating Wounds = mortal wounds** is the committed behavior:

- **Confirmed (24.10):** a critical wound (unmodified 6, or the Anti-X threshold) ends the attack sequence for
  that attack — no save, no normal damage for it — and instead the target *unit* suffers mortal wounds equal to
  the weapon's Damage characteristic, inflicted **after** the normal damage of those attacks has been resolved.
- **Corrected mortal-wound allocation (24.10, re-read 2026-07-05):** Devastating Wounds mortals are **capped at one
  model per critical wound**. Each critical wound's Damage-many mortals are allocated to a single model (the
  already-wounded lead first, which is the lead in our uniform units); if that is more than the model's remaining
  wounds, the model dies and the **overkill is lost** — the mortals do **not** carry to a second model. This is the
  same one-model, waste-the-overkill behaviour as normal damage; the only difference is no save was rolled.
  ⚠️ This corrects the 2026-07-03 note, which described the *general* mortal-wound rule (06.02 — mortals crossing
  models one wound at a time). 06.02 does spill, but §24.10 makes Devastating Wounds (and Hazardous) the explicit
  exception, and Devastating Wounds is our only mortal source. GW's own example: a Damage-3 critical against a
  1-wound (per model) Intercessor Squad kills one model and wastes two — it does not fell three. Feel No Pain
  (24.12) would roll per mortal wound (not modelled yet).
- Unchanged conclusion: this is **not** the `no_save_wounds` save-step bucket (that was the end-of-10th shape) —
  it needs its own mortal-wound resolution path alongside the normal save/damage steps. In code that path is now
  structurally identical to normal-damage allocation (one packet per critical wound, capped to one model), just
  skipping the save roll.

Two phase-7 design notes picked up from the same read: **Lethal Hits (24.23) is now a per-attack *choice*** — the
attacker may decline the auto-wound so the attack can still roll for a critical wound and trigger Devastating
Wounds (a fine v1 default is "always accept", but the hook design should leave room for the choice). And
**Sustained Hits (24.36)** is confirmed as X *additional plain hits* on a critical hit, alongside the explicit
sidebar that critical hits still count as hits — exactly the immutable-`critical_hits` reading ADR 0002 assumed.

Devastating Wounds is a **phase-7** ability (keyword hooks; renumbered from "phase 4" when the build order gained
explicit UI/runner/narrator phases), so it never blocked Phase 3 — and as of 2026-07-03 nothing about it is
unverified.

### Primary-source verification (2026-07-03)

The official, free **11th-edition Core Rules PDF** (published 2026-06-01, 88 pages) was retrieved directly from
Games Workshop's asset host and read — resolving the three items that previously rested on secondary sources:

- **File:** `https://assets.warhammer-community.com/eng_01-06_warhammer40k_new40k_core_rules-was6fbu1ix-hfewhmxyiy.pdf`
  (the downloads page is a JS app whose visible search API serves a stale index; the working retrieval recipe is
  recorded in `.claude/agents/rules-researcher.md`).
- The hit/wound/save tables print their numerals as graphics, so those pages were **read visually**, confirming:
  hit and wound rolls both fail on an unmodified 1 and are critical on an unmodified 6; the wound chart matches
  `core.dice.wound_target` row for row; the save table has **no** critical-save row.
- **Allocation groups (05.03–05.04)** — the "Save Groups" from preview coverage: the defender splits the unit into
  groups (each character alone; everyone else grouped by identical Wounds/save/invulnerable values), declares an
  order under wounded-first / characters-last constraints, then all save dice are rolled and resolved lowest to
  highest against the current group. Damage: the picked model loses Damage-many wounds, is destroyed at zero or
  below (surplus on that model simply gone), and attacks left over when the unit dies are lost — confirming the
  `wasted` overkill semantics. For v1's uniform, character-free units there is exactly **one** group, so the whole
  procedure collapses to our pipeline; it becomes relevant only if mixed-save units or attached characters arrive.
- The core document's ► cross-references (e.g. *Random Characteristics*) point at GW's separate **Rules
  Commentary**, which has **no 11th-edition release yet** as of 2026-07-03 — the one residual to re-check when it
  publishes.

### Sources

- ✅ **Official 11th Core Rules PDF** (2026-06-01, 88 pp) — primary source for every ✅ above; URL and retrieval
  recipe as noted in *Primary-source verification*.
- Warhammer Community — new-edition reveal (AdeptiCon 2026) & "Download the free Core Rules now."
- Warhammer Community — "Weapons Rules Are Fun and Flexible" (11th; secondary corroboration for Dev Wounds, crit thresholds, Anti-X).
- Wargamer — 11th-edition abilities / full guide (secondary). Wahapedia 10th + datacard.app (10th baseline).

## Next steps

1. ✅ **Edition decided: 11th** (2026-06-30, [ADR 0004](../adr/0004-target-11th-edition.md)). Core math is
   unchanged, so the dice module and this design stand; the only affected ability is Devastating Wounds
   (phase 7, above).
2. ✅ **The three PDF items are cleared** (2026-07-03) against the official 11th Core Rules PDF: per-model
   variable Attacks (#3), Devastating Wounds wording + mortal-wound allocation (#9), and no critical-save rule /
   "Save Groups" = allocation groups (#8). **Phase 7 (keyword hooks) is no longer blocked on rules verification.**
3. ✅ **Phase 3 shipped** (PR #5): keyword-free `resolve_shooting` with `rng` threading, record → report proven.
   Variable attacks were deliberately deferred there, so finding #3 changes no shipped code — it binds whoever
   implements `DiceExpr` attacks later (one roll per model, recorded per model).
4. **One residual, non-blocking:** re-check the *Random Characteristics* wording when GW publishes the
   11th-edition Rules Commentary (not out as of 2026-07-03).
