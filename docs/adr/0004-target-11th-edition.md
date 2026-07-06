# Target Warhammer 40,000 11th edition (migrated from 10th)

**Status:** accepted — supersedes the 10th-edition assumption in the initial scaffold

The scaffold was written against 10th edition. **11th edition released in June 2026 and is now the current published ruleset**, so the project migrates to target it. 11th is an *evolution* of 10th, not a rewrite: the core hit / wound / save / damage math is unchanged, so the implemented dice module and the Phase-3 shooting-pipeline design carry over as-is. The migration updates edition references across `CLAUDE.md`, the docs, `README.md`, packaging, the `rules-researcher` agent, and the `add-unit` skill.

## Considered Options

- **Stay on 10th for v1, migrate at v2.** Rejected: the longer we wait, the more rules get encoded against 10th and the more expensive the migration becomes — while the cost *now* is near-zero because the math is unchanged.

## Consequences

- The one material rules change is **Devastating Wounds**: 11th reverted it to **mortal wounds** (bypass saves), so its hook is a separate mortal-wound track, not the `no_save_wounds` bucket from end-of-10th. Those mortals are capped at **one model per critical wound** with overkill wasted — they do *not* spill between models (24.10; corrected 2026-07-05, superseding an earlier note that had them spilling). It is a phase-7 ability (keyword hooks), so phase 3 is unaffected. See ADR 0002 and `docs/design/shooting-pipeline.md`.
- **Sourcing caveat:** Wahapedia has not yet updated to 11th (still 10th as of mid-2026). The authoritative 11th source is the official Warhammer Community **Core Rules PDF**; Wahapedia stays useful as a 10th baseline for the many unchanged mechanics, but anything edition-sensitive must be confirmed against the 11th PDF.
- ~~Three details still need a one-time read of the 11th Core Rules PDF~~ **Done 2026-07-03, allocation corrected 2026-07-05:** the free PDF was retrieved directly from GW's asset host and all three details were confirmed — variable Attacks resolve per weapon/model, Devastating Wounds inflicts after-damage mortal wounds, and there is no critical-save rule ("Save Groups" are allocation procedure). The 2026-07-03 note recorded the mortal allocation as "one wound at a time" (the *general* 06.02 rule); a re-read of §24.10 on 2026-07-05 corrected this — Devastating Wounds mortals cap at one model per critical wound and do not spill. One non-blocking residual: re-check *Random Characteristics* when the 11th Rules Commentary publishes. Findings and retrieval recipe: `docs/design/shooting-pipeline.md` and `.claude/agents/rules-researcher.md`.
