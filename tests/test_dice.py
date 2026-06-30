"""Tests for the dice primitives.

These tests are the template for how every dice-affecting rule should be
tested in this project:

- exact-outcome tests use a seeded `random.Random` for determinism
- probabilistic tests use 100k rolls and assert the distribution is in range
"""

from __future__ import annotations

import random

import pytest

from wh40k_tutorial.core.dice import (
    RollResult,
    roll_d6,
    save_target,
    wound_target,
)


class TestRollD6:
    def test_count_zero_returns_empty(self) -> None:
        r = roll_d6(0)
        assert r.successes == 0
        assert r.rolls == ()

    def test_count_negative_raises(self) -> None:
        with pytest.raises(ValueError):
            roll_d6(-1)

    def test_target_out_of_range_raises(self) -> None:
        with pytest.raises(ValueError):
            roll_d6(1, target=1)
        with pytest.raises(ValueError):
            roll_d6(1, target=7)

    def test_deterministic_with_seeded_rng(self) -> None:
        rng = random.Random(42)
        r = roll_d6(10, target=4, rng=rng)
        # Same seed should produce the same result every time
        rng2 = random.Random(42)
        r2 = roll_d6(10, target=4, rng=rng2)
        assert r.raw_rolls == r2.raw_rolls

    def test_natural_1_always_fails(self) -> None:
        # Construct a result manually to test the rule
        result = RollResult(
            rolls=(2,),
            raw_rolls=(1,),
            target=2,
            modifier=1,
            reroll="none",
        )
        # Even with a +1 mod meeting the target, a natural 1 fails
        assert result.successes == 0

    def test_natural_6_always_succeeds(self) -> None:
        result = RollResult(
            rolls=(5,),
            raw_rolls=(6,),
            target=7,  # impossible to meet normally
            modifier=-1,
            reroll="none",
        )
        # Even though modified value is below target, natural 6 succeeds
        assert result.successes == 1

    def test_2plus_succeeds_about_5_in_6(self) -> None:
        # Probability test: rolling 2+ should pass ~83.3% of the time
        r = roll_d6(100_000, target=2)
        rate = r.successes / 100_000
        assert 0.825 < rate < 0.842, f"2+ pass rate was {rate:.4f}, expected ~0.833"

    def test_4plus_succeeds_about_half(self) -> None:
        r = roll_d6(100_000, target=4)
        rate = r.successes / 100_000
        assert 0.495 < rate < 0.505, f"4+ pass rate was {rate:.4f}, expected ~0.500"

    def test_reroll_ones_improves_rate(self) -> None:
        # Re-rolling 1s on a 4+ should bump the pass rate from ~50% to ~58.3%
        r = roll_d6(100_000, target=4, reroll="ones")
        rate = r.successes / 100_000
        assert 0.575 < rate < 0.595, f"4+ rerolling 1s gave {rate:.4f}, expected ~0.583"

    def test_critical_hits_counted(self) -> None:
        rng = random.Random(0)
        r = roll_d6(1000, target=4, rng=rng)
        # About 1/6 of rolls should be natural 6s
        assert 130 < r.critical_hits < 200


class TestWoundTarget:
    @pytest.mark.parametrize(
        ("strength", "toughness", "expected"),
        [
            (8, 4, 2),   # S >= 2T: 2+
            (8, 3, 2),
            (5, 4, 3),   # S > T: 3+
            (4, 3, 3),
            (4, 4, 4),   # S == T: 4+
            (3, 4, 5),   # S < T: 5+
            (3, 6, 6),   # S*2 <= T: 6+
            (3, 7, 6),
        ],
    )
    def test_wound_chart(self, strength: int, toughness: int, expected: int) -> None:
        assert wound_target(strength, toughness) == expected


class TestSaveTarget:
    def test_no_ap_returns_armor(self) -> None:
        assert save_target(armor_save=3, ap=0) == 3

    def test_ap_increases_target(self) -> None:
        # AP -1 vs a 3+ save becomes a 4+ save
        assert save_target(armor_save=3, ap=1) == 4

    def test_invuln_used_if_better(self) -> None:
        # 3+ armor, AP -3, would become 6+. 4+ invuln is better.
        assert save_target(armor_save=3, ap=3, invuln=4) == 4

    def test_armor_used_if_better_than_invuln(self) -> None:
        # 2+ armor, AP -1, becomes 3+. 5+ invuln is worse, armor wins.
        assert save_target(armor_save=2, ap=1, invuln=5) == 3
