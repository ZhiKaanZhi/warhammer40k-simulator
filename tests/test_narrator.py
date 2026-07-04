"""Tests for the narrator (build phase 6).

The narrator is a pure formatter over `ShootingResult` (ADR 0001), so every
test builds a real record via `resolve_shooting` with a seeded RNG — never a
hand-faked record — and asserts on the words. Branch coverage mirrors the
narrator's own branches: the five wound-chart relations, the four save
shapes (no save / invulnerable wins / armour despite invulnerable / no AP),
and the three damage shapes (one-wound models / big hits with overkill /
multi-wound models soaking).
"""

from __future__ import annotations

import dataclasses
import random

import pytest

from wh40k_tutorial.core.combat import ShootingResult, resolve_shooting
from wh40k_tutorial.core.models import Profile, UnitDatasheet, Weapon, load_faction_by_name
from wh40k_tutorial.narrator import STEP_ORDER, narrate_volley

MARINES = load_faction_by_name("space_marines")["intercessor_squad"]
GANTS = load_faction_by_name("tyranids")["termagants"]
BOLT_RIFLE = next(w for w in MARINES.weapons if w.name == "bolt_rifle")

SEED = 42  # the seed the CLI e2e test uses; keeps the two suites telling one story


def _weapon(
    *,
    attacks: int = 2,
    skill: int = 3,
    strength: int = 4,
    ap: int = 0,
    damage: int = 1,
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
    )


def _attacker(weapon: Weapon) -> UnitDatasheet:
    return UnitDatasheet(
        key="test_attackers",
        display_name="Test Attackers",
        faction="test",
        profile=Profile(6, 4, 3, 2, 6, 2),
        weapons=(weapon,),
        default_model_count=5,
    )


def _defender(
    *,
    toughness: int = 4,
    save: int = 3,
    wounds: int = 1,
    invuln: int | None = None,
) -> UnitDatasheet:
    return UnitDatasheet(
        key="test_defenders",
        display_name="Test Defenders",
        faction="test",
        profile=Profile(6, toughness, save, wounds, 7, 2, invulnerable_save=invuln),
        weapons=(),
        default_model_count=10,
    )


def _volley(
    weapon: Weapon,
    defender: UnitDatasheet,
    *,
    models: int = 5,
    defender_models: int = 10,
    seed: int = SEED,
) -> ShootingResult:
    return resolve_shooting(
        _attacker(weapon),
        models,
        weapon,
        defender,
        defender.profile.wounds,
        defender_models,
        rng=random.Random(seed),
    )


def _inline(result: ShootingResult, step: str) -> str:
    return next(n.inline for n in narrate_volley(result) if n.step == step)


class TestShape:
    def test_five_steps_in_pipeline_order(self) -> None:
        result = resolve_shooting(MARINES, 5, BOLT_RIFLE, GANTS, 1, 10, rng=random.Random(SEED))
        narrations = narrate_volley(result)
        assert tuple(n.step for n in narrations) == STEP_ORDER
        for n in narrations:
            assert n.inline and n.expansion, f"{n.step} narration must never be empty"

    def test_zero_pool_still_narrates(self) -> None:
        # A lone bad shot (6+ to hit, one die): scan seeds for a whiffed volley
        # and check the whole cascade of empty steps still explains itself.
        weapon = _weapon(attacks=1, skill=6)
        for seed in range(50):
            result = _volley(weapon, _defender(), models=1, seed=seed)
            if result.hit.hits == 0:
                break
        else:  # pragma: no cover - one miss in 50 seeds is a statistical certainty
            pytest.fail("no seed in range produced a miss")
        narrations = narrate_volley(result)
        assert tuple(n.step for n in narrations) == STEP_ORDER
        for n in narrations:
            assert n.inline and n.expansion


class TestScenarioOneWords:
    """The exact teaching lines for the volley the first scenario shows."""

    @pytest.fixture()
    def result(self) -> ShootingResult:
        return resolve_shooting(MARINES, 5, BOLT_RIFLE, GANTS, 1, 10, rng=random.Random(SEED))

    def test_attacks_line_shows_the_multiplication(self, result: ShootingResult) -> None:
        line = _inline(result, "attacks")
        assert "Bolt Rifle" in line
        assert "5 x 2 = 10 dice" in line

    def test_hit_line_names_ballistic_skill_and_the_naturals(self, result: ShootingResult) -> None:
        line = _inline(result, "hit")
        assert "roll 3+" in line
        assert "Ballistic Skill" in line
        assert "natural 1 always misses" in line
        assert "natural 6 always hits" in line

    def test_wound_line_reads_the_chart(self, result: ShootingResult) -> None:
        line = _inline(result, "wound")
        assert "Strength 4 beats the target's Toughness 3" in line
        assert "3+ to wound" in line

    def test_save_line_explains_ap(self, result: ShootingResult) -> None:
        line = _inline(result, "save")
        assert "armour save is 5+" in line
        assert "AP -1" in line
        assert "worsens it to 6+" in line

    def test_damage_line_explains_one_wound_models(self, result: ShootingResult) -> None:
        line = _inline(result, "damage")
        assert "1 here" in line
        assert "single wound apiece" in line

    def test_melee_weapon_names_weapon_skill(self) -> None:
        # v1 has no resolve_melee, so the pipeline can't produce a melee record
        # yet — but the narrator's wording branch must be right the day it can.
        # Swap only the weapon on a genuine record; every dice fact stays real.
        ranged = _weapon()
        melee_twin = dataclasses.replace(ranged, type="melee", range=0)
        result = _volley(ranged, _defender())
        result = dataclasses.replace(
            result, attack=dataclasses.replace(result.attack, weapon=melee_twin)
        )
        line = _inline(result, "hit")
        assert "Weapon Skill" in line
        assert "Ballistic Skill" not in line


class TestWoundRelations:
    """One phrasing per wound-chart row, driven by the recorded target."""

    @pytest.mark.parametrize(
        ("strength", "toughness", "phrase", "target"),
        [
            (8, 4, "is at least double", 2),
            (5, 4, "beats", 3),
            (4, 4, "exactly matches", 4),
            (3, 4, "is below", 5),
            (2, 4, "is no more than half of", 6),
        ],
    )
    def test_relation_phrase(self, strength: int, toughness: int, phrase: str, target: int) -> None:
        weapon = _weapon(strength=strength)
        result = _volley(weapon, _defender(toughness=toughness))
        assert result.wound.roll.target == target  # precondition: the chart row we mean
        line = _inline(result, "wound")
        assert phrase in line
        assert f"{target}+ to wound" in line


class TestSaveBranches:
    def test_no_save_possible(self) -> None:
        result = _volley(_weapon(ap=2), _defender(save=5))
        assert not result.save.save_possible  # precondition
        line = _inline(result, "save")
        assert "7+" in line
        assert "No save is possible" in line
        assert "no dice" in line

    def test_invulnerable_wins_over_pierced_armour(self) -> None:
        result = _volley(_weapon(ap=3), _defender(save=3, invuln=4))
        assert result.save.modified_target == 4  # precondition: the 4++ is in use
        line = _inline(result, "save")
        assert "ignores AP entirely" in line
        assert "4++" in line
        assert "saves on 4+" in line

    def test_armour_better_than_invulnerable_mentions_both(self) -> None:
        result = _volley(_weapon(ap=1), _defender(save=2, invuln=5))
        assert result.save.modified_target == 3  # precondition: armour wins
        line = _inline(result, "save")
        assert "worsens it to 3+" in line
        assert "5++" in line
        assert "still the better save" in line

    def test_no_ap_weapon(self) -> None:
        result = _volley(_weapon(ap=0), _defender(save=3))
        line = _inline(result, "save")
        assert "has no AP" in line
        assert "saves need 3+" in line


class TestDamageBranches:
    def test_overkill_is_called_out(self) -> None:
        # Damage 3 into 2-wound models with no save: every failed save wastes
        # 1 point, and the line must teach the no-spillover rule.
        weapon = _weapon(attacks=2, skill=2, strength=8, ap=4, damage=3)
        result = _volley(weapon, _defender(toughness=3, save=5, wounds=2), models=10)
        assert result.damage.wasted_damage > 0  # precondition
        line = _inline(result, "damage")
        assert "takes 3 at once" in line
        assert "never spills" in line
        assert "overkill" in line

    def test_multi_wound_models_soak(self) -> None:
        weapon = _weapon(damage=1)
        result = _volley(weapon, _defender(wounds=3))
        line = _inline(result, "damage")
        assert "3 wounds" in line
        assert "pile onto the same front model" in line


class TestExpansions:
    @pytest.fixture()
    def by_step(self) -> dict[str, str]:
        result = resolve_shooting(MARINES, 5, BOLT_RIFLE, GANTS, 1, 10, rng=random.Random(SEED))
        return {n.step: n.expansion for n in narrate_volley(result)}

    def test_all_present_and_distinct(self, by_step: dict[str, str]) -> None:
        assert set(by_step) == set(STEP_ORDER)
        assert len(set(by_step.values())) == len(STEP_ORDER)

    def test_wound_expansion_spells_out_the_whole_chart(self, by_step: dict[str, str]) -> None:
        chart = by_step["wound"]
        for needed in ("2+", "3+", "4+", "5+", "6+", "double", "half"):
            assert needed in chart

    def test_each_expansion_teaches_its_core_rule(self, by_step: dict[str, str]) -> None:
        assert "Attacks" in by_step["attacks"]
        assert "critical hit" in by_step["hit"]
        assert "invulnerable" in by_step["save"]
        assert "capped" in by_step["hit"]
        assert "overkill" in by_step["damage"]
