"""Tests for the keyword-ability hook framework (build phase 7, ADR 0002).

Hooks are tested in two layers: the pure hook functions against a directly
constructed `RollResult` (the immutable fact they read), and the pipeline's
own responsibilities — gathering hooks from a weapon's keywords, summing
after-roll adjustments, and combining before-roll tweaks (sum-and-clamp
modifiers, most generous re-roll). The before-roll moment has no shipped
keyword yet, so it is exercised through temporarily registered fakes.
"""

from __future__ import annotations

import random

import pytest

from wh40k_tutorial.core import abilities
from wh40k_tutorial.core.abilities import (
    HitAdjustment,
    RollTweak,
    WoundAdjustment,
    combine_tweaks,
    hit_adjustment,
    wound_adjustment,
)
from wh40k_tutorial.core.combat import resolve_shooting
from wh40k_tutorial.core.dice import RollResult
from wh40k_tutorial.core.models import (
    Profile,
    UnitDatasheet,
    Weapon,
    WeaponKeyword,
    parse_weapon_keyword,
)


def _weapon(**overrides: object) -> Weapon:
    base: dict = {
        "name": "test_gun",
        "display_name": "Test Gun",
        "type": "ranged",
        "range": 12,
        "attacks": 2,
        "skill": 3,
        "strength": 4,
        "ap": 0,
        "damage": 1,
        "keywords": (),
    }
    base.update(overrides)
    return Weapon(**base)


def _sheet(weapon: Weapon) -> UnitDatasheet:
    return UnitDatasheet(
        key="test_unit",
        display_name="Test Unit",
        faction="test",
        profile=Profile(6, 4, 4, 1, 6, 2),
        weapons=(weapon,),
        default_model_count=5,
        default_loadout=(weapon.name,),
    )


def _roll_with_crits(criticals: int, plain_successes: int = 1) -> RollResult:
    """A hand-built RollResult with a known critical count — the one immutable
    fact after-roll hooks are allowed to read."""
    faces = (6,) * criticals + (4,) * plain_successes + (1,)
    return RollResult(rolls=faces, raw_rolls=faces, target=4, modifier=0, reroll="none")


class TestKeywordParsing:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("sustained_hits_1", WeaponKeyword("sustained_hits", 1)),
            ("sustained_hits_2", WeaponKeyword("sustained_hits", 2)),
            ("rapid_fire_1", WeaponKeyword("rapid_fire", 1)),
            ("anti_infantry_4", WeaponKeyword("anti_infantry", 4)),
            ("lethal_hits", WeaponKeyword("lethal_hits", None)),
            ("assault", WeaponKeyword("assault", None)),
            ("devastating_wounds", WeaponKeyword("devastating_wounds", None)),
        ],
    )
    def test_name_and_value_split(self, raw: str, expected: WeaponKeyword) -> None:
        assert parse_weapon_keyword(raw) == expected

    def test_weapon_exposes_parsed_keywords(self) -> None:
        weapon = _weapon(keywords=("sustained_hits_2", "lethal_hits"))
        assert weapon.parsed_keywords == (
            WeaponKeyword("sustained_hits", 2),
            WeaponKeyword("lethal_hits", None),
        )


class TestCombineTweaks:
    def test_empty_is_identity(self) -> None:
        assert combine_tweaks([]) == RollTweak(modifier=0, reroll="none")

    @pytest.mark.parametrize(
        ("modifiers", "expected"),
        [([1, 1], 1), ([-1, -1, -1], -1), ([1, -1], 0), ([1], 1)],
    )
    def test_modifiers_sum_then_clamp_to_net_one(
        self, modifiers: list[int], expected: int
    ) -> None:
        combined = combine_tweaks([RollTweak(modifier=m) for m in modifiers])
        assert combined.modifier == expected

    def test_most_generous_reroll_wins(self) -> None:
        tweaks = [RollTweak(reroll="ones"), RollTweak(reroll="fails"), RollTweak(reroll="all")]
        assert combine_tweaks(tweaks).reroll == "fails"
        assert combine_tweaks([RollTweak(reroll="ones"), RollTweak()]).reroll == "ones"


class TestHooks:
    def test_sustained_hits_adds_plain_hits_per_critical(self) -> None:
        weapon = _weapon(keywords=("sustained_hits_2",))
        adj = hit_adjustment(_roll_with_crits(3), weapon)
        assert adj == HitAdjustment(extra_hits=6, auto_wounds=0)

    def test_lethal_hits_converts_criticals_to_auto_wounds(self) -> None:
        weapon = _weapon(keywords=("lethal_hits",))
        adj = hit_adjustment(_roll_with_crits(2), weapon)
        assert adj == HitAdjustment(extra_hits=0, auto_wounds=2)

    def test_sustained_and_lethal_read_the_same_immutable_criticals(self) -> None:
        # ADR 0002's stacking rule: both fire off the same critical count,
        # never off each other's output — so order can't matter.
        weapon = _weapon(keywords=("sustained_hits_1", "lethal_hits"))
        adj = hit_adjustment(_roll_with_crits(2), weapon)
        assert adj == HitAdjustment(extra_hits=2, auto_wounds=2)

    def test_devastating_wounds_diverts_criticals_as_damage_many_mortals(self) -> None:
        weapon = _weapon(keywords=("devastating_wounds",), damage=3)
        adj = wound_adjustment(_roll_with_crits(2), weapon)
        assert adj == WoundAdjustment(diverted_critical_wounds=2)

    def test_keywordless_weapon_gets_zero_adjustments(self) -> None:
        weapon = _weapon()
        assert hit_adjustment(_roll_with_crits(3), weapon) == HitAdjustment()
        assert wound_adjustment(_roll_with_crits(3), weapon) == WoundAdjustment()

    def test_unimplemented_keywords_are_inert(self) -> None:
        # "assault" is canonical data but has no hook: it must flow through
        # without effect rather than erroring (CLAUDE.md's inert rule).
        weapon = _weapon(keywords=("assault",))
        assert hit_adjustment(_roll_with_crits(1), weapon) == HitAdjustment()


class TestBeforeRollMoment:
    """No shipped keyword uses before-roll tweaks yet; prove the machinery
    with temporarily registered fakes, including that the pipeline threads
    the combined tweak into the actual dice roll."""

    def test_pipeline_threads_modifier_and_reroll_into_the_hit_roll(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setitem(
            abilities.HIT_BEFORE, "test_boost", lambda weapon, value: RollTweak(modifier=1)
        )
        monkeypatch.setitem(
            abilities.HIT_BEFORE,
            "test_reroll",
            lambda weapon, value: RollTweak(reroll="ones"),
        )
        weapon = _weapon(keywords=("test_boost", "test_reroll"))
        result = resolve_shooting(
            _sheet(weapon), 5, weapon, _sheet(_weapon()), 1, 10, rng=random.Random(0)
        )
        assert result.hit.roll.modifier == 1
        assert result.hit.roll.reroll == "ones"

    def test_pipeline_clamps_stacked_modifiers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setitem(
            abilities.HIT_BEFORE, "test_boost", lambda weapon, value: RollTweak(modifier=1)
        )
        monkeypatch.setitem(
            abilities.HIT_BEFORE, "test_boost_two", lambda weapon, value: RollTweak(modifier=1)
        )
        weapon = _weapon(keywords=("test_boost", "test_boost_two"))
        result = resolve_shooting(
            _sheet(weapon), 5, weapon, _sheet(_weapon()), 1, 10, rng=random.Random(0)
        )
        assert result.hit.roll.modifier == 1  # +2 requested, ±1 cap enforced
