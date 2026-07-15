"""Tests for the expected-damage estimator (`core.expected`).

Two layers, per the project's dice-testing template:

- **Exact tests**: hand-computed expectations for real datasheet weapons and
  synthetic keyword combinations, asserted with `pytest.approx`.
- **Monte Carlo agreement**: the estimator's whole reason to exist is
  mirroring `resolve_shooting`, so we run the real pipeline tens of
  thousands of times with a seeded RNG and assert its mean total damage
  lands on the estimate. If the pipeline's keyword semantics ever change,
  these tests drag the estimator along.
"""

from __future__ import annotations

import random

import pytest

from wh40k_tutorial.core.combat import ShootingResult, resolve_shooting
from wh40k_tutorial.core.expected import expected_damage
from wh40k_tutorial.core.models import Profile, UnitDatasheet, Weapon, load_faction_by_name

MARINES = load_faction_by_name("space_marines")["intercessor_squad"]
GANTS = load_faction_by_name("tyranids")["termagants"]
IMMORTALS = load_faction_by_name("necrons")["immortals"]
WARRIORS = load_faction_by_name("necrons")["necron_warriors"]
TAU = load_faction_by_name("tau_empire")["strike_team"]
RANGERS = load_faction_by_name("adeptus_mechanicus")["skitarii_rangers"]


def _weapon_of(sheet: UnitDatasheet, key: str) -> Weapon:
    return next(w for w in sheet.weapons if w.name == key)


def _weapon(
    *,
    attacks: int = 1,
    skill: int = 4,
    strength: int = 4,
    ap: int = 0,
    damage: int = 1,
    keywords: tuple[str, ...] = (),
) -> Weapon:
    return Weapon(
        name="test_gun",
        display_name="Test Gun",
        type="ranged",
        range=24,
        attacks=attacks,
        skill=skill,
        strength=strength,
        ap=ap,
        damage=damage,
        keywords=keywords,
    )


def _profile(
    *, toughness: int = 4, save: int = 4, wounds: int = 1, invuln: int | None = None
) -> Profile:
    return Profile(
        movement=6,
        toughness=toughness,
        save=save,
        wounds=wounds,
        leadership=7,
        objective_control=2,
        invulnerable_save=invuln,
    )


def _sheet(profile: Profile, weapon: Weapon) -> UnitDatasheet:
    return UnitDatasheet(
        key="test_unit",
        display_name="Test Unit",
        faction="test",
        profile=profile,
        weapons=(weapon,),
        default_model_count=5,
    )


# ---------------------------------------------------------------------------
# Exact hand-computed expectations
# ---------------------------------------------------------------------------


class TestExactValues:
    def test_plain_weapon_bolt_rifle_vs_termagants(self) -> None:
        # 10 dice x P(hit 3+)=4/6 x P(wound S4 vs T3 = 3+)=4/6
        #         x P(fail a 6+ save: 5+ armour worsened by AP -1)=5/6
        rifle = _weapon_of(MARINES, "bolt_rifle")
        assert expected_damage(5, rifle, GANTS.profile) == pytest.approx(
            10 * (4 / 6) * (4 / 6) * (5 / 6)
        )

    def test_sustained_hits_2_tesla_vs_termagants(self) -> None:
        # Per die: 4/6 hits + (1/6 crits x 2 extras) = exactly 1 wound die,
        # then 3+ to wound (4/6) and the gants fail a 5+ save 4/6 of the time.
        tesla = _weapon_of(IMMORTALS, "tesla_carbine")
        assert expected_damage(10, tesla, GANTS.profile) == pytest.approx(
            20 * 1.0 * (4 / 6) * (4 / 6)
        )

    def test_lethal_hits_gauss_blaster_vs_marines(self) -> None:
        # Per die: 1/6 auto-wounds skip the roll; the other 3/6 hits wound
        # on 4+ (S5 vs T4 is "beats"? no — 5 > 4 so 3+): recompute exactly.
        blaster = _weapon_of(IMMORTALS, "gauss_blaster")
        p_hit, p_crit = 4 / 6, 1 / 6
        wound_dice = p_hit - p_crit
        wounds = wound_dice * (4 / 6) + p_crit  # S5 > T4 -> 3+
        per_die = wounds * (1 / 2)  # 3+ save worsened by AP -1 -> 4+, fails 3/6
        assert expected_damage(5, blaster, MARINES.profile) == pytest.approx(10 * per_die)

    def test_bare_sustained_hits_defaults_to_one_extra(self) -> None:
        # A hand-built "sustained_hits" without a number mirrors the hook's
        # default of 1 extra hit per critical.
        bare = _weapon(skill=4, keywords=("sustained_hits",))
        numbered = _weapon(skill=4, keywords=("sustained_hits_1",))
        target = _profile()
        assert expected_damage(10, bare, target) == pytest.approx(
            expected_damage(10, numbered, target)
        )

    def test_devastating_wounds_diverts_criticals_into_mortals(self) -> None:
        # A2 4+/S4/AP0/D2 vs T4 3+ save, 5 models = 10 dice. Per die:
        # 3/6 hits roll to wound on 4+ -> 1/4 rolled wounds, of which the
        # 1/12 critical wounds become 2 mortal damage each; the remaining
        # 1/6 savable wounds face a 3+ save (fail 2/6) at Damage 2.
        weapon = _weapon(attacks=2, skill=4, damage=2, keywords=("devastating_wounds",))
        target = _profile(toughness=4, save=3)
        per_die = (1 / 4 - 1 / 12) * (2 / 6) * 2 + (1 / 12) * 2
        assert expected_damage(5, weapon, target) == pytest.approx(10 * per_die)

    def test_lethal_and_devastating_interact_through_the_wound_dice(self) -> None:
        # Lethal pulls criticals out of the wound roll, so Devastating has
        # fewer dice to crit on. A1 3+/S8/AP0/D3 vs T4 4+ works out to
        # exactly 1.0 expected damage per die.
        weapon = _weapon(
            skill=3, strength=8, damage=3, keywords=("lethal_hits", "devastating_wounds")
        )
        target = _profile(toughness=4, save=4)
        assert expected_damage(5, weapon, target) == pytest.approx(5.0)

    def test_no_save_branch_means_every_wound_lands(self) -> None:
        # AP -4 against a bare 4+ save needs an 8+: no save possible.
        weapon = _weapon(skill=4, strength=4, ap=4)
        target = _profile(toughness=4, save=4)
        assert expected_damage(4, weapon, target) == pytest.approx(4 * (3 / 6) * (3 / 6))

    def test_invulnerable_save_is_the_floor(self) -> None:
        # Skitarii: 4+ armour, 5++ invulnerable. AP -2 would push armour to
        # 6+, so the 5++ takes over (fails 4/6).
        weapon = _weapon(skill=4, strength=4, ap=2)
        assert expected_damage(10, weapon, RANGERS.profile) == pytest.approx(
            10 * (3 / 6) * (4 / 6) * (4 / 6)
        )

    def test_scenario_06_numbers_warriors_draw_double(self) -> None:
        # The lesson of 06_return_fire: 10 pulse rifles expect twice the
        # damage into Warriors (T4, 4+) as into Immortals (T5, 3+).
        pulse = _weapon_of(TAU, "pulse_rifle")
        vs_warriors = expected_damage(10, pulse, WARRIORS.profile)
        vs_immortals = expected_damage(10, pulse, IMMORTALS.profile)
        assert vs_warriors == pytest.approx(10 * (3 / 6) * (4 / 6) * (3 / 6))
        assert vs_warriors == pytest.approx(2 * vs_immortals)

    def test_variable_damage_scores_by_its_average(self) -> None:
        # D3 averages 2.0, so a D3 gun must score exactly what a flat-2 gun does.
        d3 = _weapon(skill=4, damage="D3")
        flat = _weapon(skill=4, damage=2)
        target = _profile()
        assert expected_damage(10, d3, target) == pytest.approx(expected_damage(10, flat, target))

    def test_arc_rifle_vs_intercessors_matches_hand_computation(self) -> None:
        # 10 arc rifles: hit 4+ (1/2), wound 2+ (5/6, S8 vs T4), of which
        # 1/6 crit into D3 mortals (avg 2, no save); the rest face a 4+ save
        # (3+ armour, AP -1) and deal D3 on a fail.
        arc = _weapon_of(RANGERS, "arc_rifle")
        hits = 10 * (1 / 2)
        crits = hits * (1 / 6)
        savable = hits * (5 / 6) - crits
        expected = savable * (1 / 2) * 2.0 + crits * 2.0
        assert expected_damage(10, arc, MARINES.profile) == pytest.approx(expected)

    def test_inert_keywords_contribute_nothing(self) -> None:
        # rapid_fire_1 and assault have no hook in v1; the estimator must
        # mirror the engine, not the rulebook.
        plain = _weapon(skill=4)
        decorated = _weapon(skill=4, keywords=("rapid_fire_1", "assault"))
        target = _profile()
        assert expected_damage(10, plain, target) == expected_damage(10, decorated, target)


# ---------------------------------------------------------------------------
# Monte Carlo agreement with the real pipeline
# ---------------------------------------------------------------------------

_RUNS = 20_000
_TOLERANCE = 0.15


def _raw_damage(result: ShootingResult) -> int:
    """Total damage the volley *produced*, overkill included.

    `expected_damage` is documented as a raw-damage estimate: it ignores
    per-model overkill. So the fair comparison is what the pipeline rolled,
    not what the defender actually lost — otherwise a weapon whose Damage
    doesn't divide the target's wounds (D3 into 2-wound Marines) would look
    like estimator drift when it is really the documented approximation.
    `test_raw_estimate_overstates_effective_damage_on_overkill` pins that gap.
    """
    return (
        result.damage.damage_inflicted
        + result.damage.wasted_damage
        + result.mortal.inflicted
        + result.mortal.wasted
    )


def _monte_carlo_mean(
    attacker: UnitDatasheet,
    attacker_models: int,
    weapon: Weapon,
    defender: UnitDatasheet,
    defender_models: int,
) -> float:
    rng = random.Random(2026)
    total = 0
    for _ in range(_RUNS):
        result = resolve_shooting(
            attacker,
            attacker_models,
            weapon,
            defender,
            defender.profile.wounds,
            defender_models,
            rng=rng,
        )
        total += _raw_damage(result)
    return total / _RUNS


def _effective_damage_mean(
    attacker: UnitDatasheet,
    attacker_models: int,
    weapon: Weapon,
    defender: UnitDatasheet,
    defender_models: int,
) -> float:
    """Mean wounds the defender actually lost (overkill excluded)."""
    rng = random.Random(2026)
    wounds_per_model = defender.profile.wounds
    total = 0
    for _ in range(_RUNS):
        result = resolve_shooting(
            attacker,
            attacker_models,
            weapon,
            defender,
            wounds_per_model,
            defender_models,
            rng=rng,
        )
        before = defender_models * wounds_per_model
        if result.models_remaining == 0:
            total += before
        else:
            after = (
                result.models_remaining - 1
            ) * wounds_per_model + result.wounds_remaining_on_lead
            total += before - after
    return total / _RUNS


class TestMonteCarloAgreement:
    """The estimator may not drift from what `resolve_shooting` actually does.

    Defender pools are large enough that a wipe (which would clip the raw
    expectation) is effectively impossible at these expected values.
    """

    def test_sustained_hits_tesla_vs_termagant_horde(self) -> None:
        tesla = _weapon_of(IMMORTALS, "tesla_carbine")
        mean = _monte_carlo_mean(IMMORTALS, 10, tesla, GANTS, 20)
        assert mean == pytest.approx(
            expected_damage(10, tesla, GANTS.profile), abs=_TOLERANCE
        )

    def test_lethal_hits_gauss_flayer_vs_marines(self) -> None:
        flayer = _weapon_of(WARRIORS, "gauss_flayer")
        mean = _monte_carlo_mean(WARRIORS, 10, flayer, MARINES, 10)
        assert mean == pytest.approx(
            expected_damage(10, flayer, MARINES.profile), abs=_TOLERANCE
        )

    def test_arc_rifle_variable_damage_vs_intercessors(self) -> None:
        # The estimator reads D3's average; the pipeline rolls it. They must agree.
        arc = _weapon_of(RANGERS, "arc_rifle")
        mean = _monte_carlo_mean(RANGERS, 10, arc, MARINES, 10)
        assert mean == pytest.approx(
            expected_damage(10, arc, MARINES.profile), abs=_TOLERANCE
        )

    def test_raw_estimate_overstates_effective_damage_on_overkill(self) -> None:
        # The documented approximation, made visible: a D3 arc rifle into
        # 2-wound Marines produces ~5.0 raw damage per volley but strips only
        # ~3.9 wounds, because D3 doesn't divide 2 evenly and the surplus is
        # wasted. The heuristic AI is unaffected — it caps scores at the
        # target's remaining wounds — but nothing here may pretend the raw
        # estimate is effective damage.
        arc = _weapon_of(RANGERS, "arc_rifle")
        raw = expected_damage(10, arc, MARINES.profile)
        effective = _effective_damage_mean(RANGERS, 10, arc, MARINES, 10)
        assert raw == pytest.approx(5.0, abs=_TOLERANCE)
        assert effective < raw - 0.5
        assert effective == pytest.approx(3.85, abs=0.15)

    def test_devastating_wounds_with_multi_damage(self) -> None:
        weapon = _weapon(attacks=2, skill=4, damage=2, keywords=("devastating_wounds",))
        defender = _sheet(_profile(toughness=4, save=3, wounds=2), _weapon())
        attacker = _sheet(_profile(), weapon)
        mean = _monte_carlo_mean(attacker, 5, weapon, defender, 10)
        assert mean == pytest.approx(
            expected_damage(5, weapon, defender.profile), abs=_TOLERANCE
        )
