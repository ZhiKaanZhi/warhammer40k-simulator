"""Expected damage: the analytic mirror of the shooting pipeline.

`expected_damage` answers "how much damage should this shot average?" using
the same targets and the same keyword semantics as `core.combat` — the
wound chart and save math come straight from `core.dice.wound_target` /
`core.dice.save_target`, and the three v1 abilities are re-expressed as
probabilities exactly as their hooks resolve them in `core.abilities`:

- **Sustained Hits X**: each hit die criticals with probability 1/6 and adds
  X *plain* hits; the extras roll to wound like any hit.
- **Lethal Hits**: each critical hit auto-wounds instead of rolling to wound
  (v1 always accepts), so it leaves the wound-dice pool — and, having never
  rolled to wound, can never be a critical wound. Saves still apply.
- **Devastating Wounds**: each critical *wound* (probability 1/6 per wound
  die) is diverted past the saves and instead inflicts mortal wounds equal
  to the weapon's Damage.

Keywords the engine accepts but has no hook for (assault, heavy,
rapid_fire_N, ...) are inert in the pipeline and therefore inert here too:
this module estimates the engine we have, not the rulebook we don't model.
The test suite holds the two together — `tests/test_expected.py` checks the
estimate against the Monte Carlo mean of `resolve_shooting` itself, so the
estimator cannot silently drift from the pipeline.

Two deliberate approximations, documented so nobody trusts this for more
than it is:

- The estimate is **raw damage**, not effective damage: it ignores per-model
  overkill (a Damage-3 hit on a 1-wound model still counts 3 here) and does
  not cap at the target's remaining wounds. Callers that care — the
  heuristic strategy does — apply their own cap. The gap is real for
  weapons whose Damage exceeds (or doesn't divide) the target's wounds: the
  D3 arc rifle raw-scores ~5.0 into 2-wound Intercessors but strips ~3.9
  wounds. For ranking targets that is harmless — it's a monotone
  overstatement the strategy's cap already handles — but nothing may read
  this number as "wounds removed".
- Variable Damage (D3/D6) enters as its **average**; the pipeline rolls it
  per failed save and per critical wound. So the estimate is the mean of a
  distribution, not a value any single volley produces.
- Probabilities assume no die modifiers, matching v1 (no before-roll hook
  exists yet). When modifiers arrive, the hit/wound probabilities here must
  learn the ±1 cap alongside them.
"""

from __future__ import annotations

from wh40k_tutorial.core.dice import save_target, wound_target
from wh40k_tutorial.core.models import Profile, Weapon

# A D6 shows any given face with probability 1/6; an unmodified 6 is the
# critical that Sustained/Lethal/Devastating Wounds all trigger on.
_P_CRITICAL = 1 / 6


def _p_meets(target: int) -> float:
    """Probability an unmodified D6 meets ``target``, per `core.dice` rules.

    Targets arrive clamped to 2..6 (hit skill and the wound chart both live
    there), so the natural-1-fails / natural-6-succeeds rule is already
    inside the plain (7 - target) / 6 count.
    """
    return (7 - target) / 6


def expected_damage(attacker_models: int, weapon: Weapon, target: Profile) -> float:
    """The mean total damage of one volley: ``attacker_models`` firing ``weapon``.

    Mirrors the pipeline stage by stage — attacks, hits (with Sustained and
    Lethal), wounds (with Devastating's diversion), saves (AP, invulnerable,
    and the no-save 7+ branch of ADR 0003), then normal damage plus the
    mortal-wound track. Returns raw expected damage; see the module
    docstring for the two documented approximations.
    """
    keywords = {kw.name: kw.value for kw in weapon.parsed_keywords}
    total_attacks = attacker_models * weapon.attacks

    # Hit step: successes include criticals; Sustained adds plain extras;
    # Lethal pulls the criticals out as auto-wounds that skip the wound roll.
    p_hit = _p_meets(weapon.skill)
    hits = total_attacks * p_hit
    sustained_value = keywords.get("sustained_hits")
    if "sustained_hits" in keywords:
        per_critical = sustained_value if sustained_value is not None else 1
        hits += total_attacks * _P_CRITICAL * per_critical
    auto_wounds = total_attacks * _P_CRITICAL if "lethal_hits" in keywords else 0.0

    # Wound step: only non-auto hits roll; rolled natural 6s are the critical
    # wounds Devastating Wounds diverts into mortal packets.
    wound_dice = hits - auto_wounds
    p_wound = _p_meets(wound_target(weapon.strength, target.toughness))
    wounds = wound_dice * p_wound + auto_wounds
    mean_damage = weapon.damage.average  # mean of a fixed value is itself
    mortal_damage = 0.0
    savable_wounds = wounds
    if "devastating_wounds" in keywords:
        critical_wounds = wound_dice * _P_CRITICAL
        savable_wounds = wounds - critical_wounds
        mortal_damage = critical_wounds * mean_damage

    # Save step: AP-worsened armour vs the invulnerable, whichever is better;
    # a 7+ requirement means no save is possible (ADR 0003).
    save = save_target(target.save, weapon.ap, target.invulnerable_save)
    p_save = _p_meets(save) if save <= 6 else 0.0

    return savable_wounds * (1 - p_save) * mean_damage + mortal_damage
