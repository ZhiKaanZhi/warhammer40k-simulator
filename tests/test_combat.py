"""Tests for the shooting pipeline (build phase 3).

Follows the project's dice-testing template (see tests/test_dice.py):
exact-outcome tests use a seeded ``random.Random``; probabilistic claims are
tested as distributions over many trials, never single outcomes.

The last class is the "record -> narrator loop" proof from the design doc:
it derives human-readable explanations *purely from the returned record*,
with no game logic — demonstrating ADR 0001 (the record carries every fact
narration needs, including the exact numbers scenario 01's outro quotes).
"""

from __future__ import annotations

import random

import pytest

from wh40k_tutorial.core.combat import (
    ShootingResult,
    _allocate_damage,
    _resolve_mortal_wounds,
    resolve_shooting,
)
from wh40k_tutorial.core.models import (
    Profile,
    UnitDatasheet,
    Weapon,
    load_faction_by_name,
)

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _weapon(**overrides: object) -> Weapon:
    base: dict = {
        "name": "test_gun",
        "display_name": "Test Gun",
        "type": "ranged",
        "range": 12,
        "attacks": 1,
        "skill": 4,
        "strength": 4,
        "ap": 0,
        "damage": 1,
        "keywords": (),
    }
    base.update(overrides)
    return Weapon(**base)


def _sheet(
    key: str = "test_unit",
    *,
    weapon: Weapon | None = None,
    toughness: int = 4,
    save: int = 4,
    wounds: int = 1,
    invuln: int | None = None,
) -> UnitDatasheet:
    w = weapon or _weapon()
    return UnitDatasheet(
        key=key,
        display_name=key.replace("_", " ").title(),
        faction="test",
        profile=Profile(
            movement=6,
            toughness=toughness,
            save=save,
            wounds=wounds,
            leadership=6,
            objective_control=2,
            invulnerable_save=invuln,
        ),
        weapons=(w,),
        default_model_count=5,
        default_loadout=(w.name,),
    )


def _marines_vs_termagants() -> tuple[UnitDatasheet, Weapon, UnitDatasheet]:
    marines = load_faction_by_name("space_marines")["intercessor_squad"]
    termagants = load_faction_by_name("tyranids")["termagants"]
    rifle = {w.name: w for w in marines.weapons}["bolt_rifle"]
    return marines, rifle, termagants


# ---------------------------------------------------------------------------
# Pipeline consistency
# ---------------------------------------------------------------------------


class TestPipelineConsistency:
    def test_steps_chain_consistently(self) -> None:
        marines, rifle, termagants = _marines_vs_termagants()
        result = resolve_shooting(
            marines, 5, rifle, termagants, 1, 10, rng=random.Random(42)
        )
        assert result.attack.total_attacks == 10  # 5 models x 2 attacks
        assert len(result.hit.roll.raw_rolls) == 10
        assert result.hit.hits == result.hit.roll.successes
        # every hit rolls to wound (no keywords in phase 3)
        assert len(result.wound.roll.raw_rolls) == result.hit.hits
        assert result.wound.wounds == result.wound.roll.successes
        # every wound gets a saving throw (a 6+ exists for Termagants)
        assert len(result.save.roll.raw_rolls) == result.wound.wounds
        assert result.save.failed_saves == result.wound.wounds - result.save.roll.successes
        d = result.damage
        # W1 defenders: every point of inflicted damage is a slain model
        assert d.models_slain == d.damage_inflicted
        assert d.models_slain + d.models_remaining == 10
        # each failed save contributes exactly `damage`, split applied/wasted
        assert (
            d.damage_inflicted + d.wasted_damage
            == d.damage_per_failed_save * result.save.failed_saves
        )

    def test_same_seed_reproduces_identical_result(self) -> None:
        marines, rifle, termagants = _marines_vs_termagants()
        first = resolve_shooting(marines, 5, rifle, termagants, 1, 10, rng=random.Random(7))
        second = resolve_shooting(marines, 5, rifle, termagants, 1, 10, rng=random.Random(7))
        assert first == second

    def test_zero_attackers_cascade_to_empty_records(self) -> None:
        marines, rifle, termagants = _marines_vs_termagants()
        result = resolve_shooting(marines, 0, rifle, termagants, 1, 10, rng=random.Random(1))
        assert result.attack.total_attacks == 0
        assert result.hit.roll.raw_rolls == ()
        assert result.wound.wounds == 0
        assert result.save.failed_saves == 0
        assert result.damage.models_slain == 0
        assert result.damage.models_remaining == 10
        assert result.damage.wounds_remaining_on_lead == 1


# ---------------------------------------------------------------------------
# Saving throws (ADR 0003)
# ---------------------------------------------------------------------------


class TestSaves:
    def test_no_save_branch_rolls_no_dice(self) -> None:
        # 5+ armour vs AP -3, no invuln: an 8+ "save" — impossible.
        attacker = _sheet("shooter", weapon=_weapon(ap=3, skill=2, strength=8))
        defender = _sheet("target", toughness=3, save=5, wounds=1)
        result = resolve_shooting(
            attacker, 5, attacker.weapons[0], defender, 1, 10, rng=random.Random(3)
        )
        save = result.save
        assert not save.save_possible
        assert save.modified_target == 8
        assert save.roll.raw_rolls == ()  # no dice were rolled
        assert save.failed_saves == result.wound.wounds  # every wound goes through

    def test_invulnerable_save_ignores_ap(self) -> None:
        # 3+ armour shredded to 6+ by AP -3; the 4++ invuln is better.
        attacker = _sheet("shooter", weapon=_weapon(ap=3))
        defender = _sheet("target", save=3, invuln=4)
        result = resolve_shooting(
            attacker, 5, attacker.weapons[0], defender, 1, 10, rng=random.Random(3)
        )
        assert result.save.save_possible
        assert result.save.modified_target == 4
        assert result.save.roll.target == 4


# ---------------------------------------------------------------------------
# Damage allocation
# ---------------------------------------------------------------------------


class TestDamageAllocation:
    @pytest.mark.parametrize(
        (
            "failed",
            "damage",
            "wounds_per_model",
            "wounds_on_lead",
            "models",
            "expected",  # (inflicted, wasted, slain, remaining, lead_after)
        ),
        [
            # wounded lead dies to first save; overkill wasted on it and the next
            (3, 2, 3, 1, 5, (4, 2, 2, 3, 3)),
            # D3 weapon vs W1 chaff: massive overkill per model
            (2, 3, 1, 1, 10, (2, 4, 2, 8, 1)),
            # exact kills, nothing wasted
            (4, 1, 1, 1, 10, (4, 0, 4, 6, 1)),
            # more failed saves than the unit can absorb: unit destroyed, rest wasted
            (5, 1, 1, 1, 3, (3, 2, 3, 0, 0)),
            # partial damage leaves the lead model wounded but alive
            (1, 1, 2, 2, 3, (1, 0, 0, 3, 1)),
            # zero failed saves: defender untouched
            (0, 2, 3, 3, 4, (0, 0, 0, 4, 3)),
        ],
    )
    def test_allocation_table(
        self,
        failed: int,
        damage: int,
        wounds_per_model: int,
        wounds_on_lead: int,
        models: int,
        expected: tuple[int, int, int, int, int],
    ) -> None:
        step = _allocate_damage(
            failed_saves=failed,
            damage=damage,
            wounds_per_model=wounds_per_model,
            wounds_on_lead=wounds_on_lead,
            model_count=models,
        )
        assert (
            step.damage_inflicted,
            step.wasted_damage,
            step.models_slain,
            step.models_remaining,
            step.wounds_remaining_on_lead,
        ) == expected


# ---------------------------------------------------------------------------
# Scenario 01's math, statistically (the tutorial's promised numbers)
# ---------------------------------------------------------------------------


class TestScenario01Math:
    def test_matchup_matches_the_advertised_probabilities(self) -> None:
        # 10 attacks, hit on 3+ (p=2/3), wound on 3+ (S4>T3, p=2/3),
        # save fails on anything but a 6 (5+ save, AP -1 -> 6+, fail p=5/6).
        # Expected slain per volley = 10 * 2/3 * 2/3 * 5/6 = 3.704.
        marines, rifle, termagants = _marines_vs_termagants()
        rng = random.Random(123)
        trials = 10_000
        total_hits = total_slain = 0
        for _ in range(trials):
            r = resolve_shooting(marines, 5, rifle, termagants, 1, 10, rng=rng)
            total_hits += r.hit.hits
            total_slain += r.damage.models_slain
        mean_hits = total_hits / trials
        mean_slain = total_slain / trials
        assert 6.58 < mean_hits < 6.75, f"mean hits {mean_hits:.3f}, expected ~6.667"
        assert 3.62 < mean_slain < 3.79, f"mean slain {mean_slain:.3f}, expected ~3.704"


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------


class TestValidation:
    def test_melee_weapon_rejected(self) -> None:
        blade = _weapon(name="blade", display_name="Blade", type="melee", range=0)
        attacker = _sheet("shooter", weapon=blade)
        with pytest.raises(ValueError, match="ranged"):
            resolve_shooting(attacker, 5, blade, _sheet("target"), 1, 5)

    @pytest.mark.parametrize("lead_wounds", [0, 3])
    def test_lead_wounds_must_fit_the_profile(self, lead_wounds: int) -> None:
        attacker = _sheet("shooter")
        defender = _sheet("target", wounds=2)
        with pytest.raises(ValueError, match="defender_wounds_remaining"):
            resolve_shooting(attacker, 5, attacker.weapons[0], defender, lead_wounds, 5)

    def test_defender_needs_at_least_one_model(self) -> None:
        attacker = _sheet("shooter")
        with pytest.raises(ValueError, match="defender_model_count"):
            resolve_shooting(attacker, 5, attacker.weapons[0], _sheet("target"), 1, 0)

    def test_attacker_count_cannot_be_negative(self) -> None:
        attacker = _sheet("shooter")
        with pytest.raises(ValueError, match="attacker_model_count"):
            resolve_shooting(attacker, -1, attacker.weapons[0], _sheet("target"), 1, 5)


# ---------------------------------------------------------------------------
# The record -> narrator loop (ADR 0001)
# ---------------------------------------------------------------------------


class TestNarratorSufficiency:
    def test_record_yields_scenario_01_outro_facts_without_game_logic(self) -> None:
        marines, rifle, termagants = _marines_vs_termagants()
        result = resolve_shooting(marines, 5, rifle, termagants, 1, 10, rng=random.Random(9))
        # Everything below is string formatting over the record — zero rules math.
        attack_line = (
            f"{result.attack.attacker_models} models x "
            f"{result.attack.attacks_per_model} attacks = "
            f"{result.attack.total_attacks} shots"
        )
        hit_line = f"hitting on {result.hit.roll.target}+"
        wound_line = (
            f"S{result.wound.strength} vs T{result.wound.toughness} "
            f"wounds on {result.wound.roll.target}+"
        )
        save = result.save
        save_line = f"{save.armor_save}+ save, AP -{save.ap} -> {save.modified_target}+"
        # These are the exact numbers scenario 01's outro promises the player.
        assert attack_line == "5 models x 2 attacks = 10 shots"
        assert hit_line == "hitting on 3+"
        assert wound_line == "S4 vs T3 wounds on 3+"
        assert save.save_possible
        assert save_line == "5+ save, AP -1 -> 6+"

    def test_no_save_situation_is_narratable_from_the_record(self) -> None:
        attacker = _sheet("shooter", weapon=_weapon(ap=3))
        defender = _sheet("target", save=5)
        result = resolve_shooting(
            attacker, 5, attacker.weapons[0], defender, 1, 10, rng=random.Random(9)
        )
        save = result.save
        assert not save.save_possible
        line = (
            f"No save possible: AP -{save.ap} against a {save.armor_save}+ armour"
            f"{' and no invulnerable save' if save.invulnerable_save is None else ''}"
        )
        assert line == "No save possible: AP -3 against a 5+ armour and no invulnerable save"


# ---------------------------------------------------------------------------
# Phase 7: keyword abilities flowing through the pipeline
# ---------------------------------------------------------------------------


class TestKeywordAbilitiesInThePipeline:
    """The three shipped abilities, end to end through resolve_shooting.

    Assertions are relationships read off one seeded record — the same
    invariants that must hold for any roll — with explicit preconditions
    (crits > 0) so an unlucky seed fails loudly instead of passing vacuously.
    """

    SEED = 42

    def _volley(
        self,
        weapon: Weapon,
        defender: UnitDatasheet | None = None,
        *,
        models: int = 10,
    ) -> ShootingResult:
        defender = defender or _sheet("target", toughness=3, save=5)
        return resolve_shooting(
            _sheet("shooter", weapon=weapon),
            models,
            weapon,
            defender,
            defender.profile.wounds,
            10,
            rng=random.Random(self.SEED),
        )

    def test_sustained_hits_adds_per_critical_and_feeds_the_wound_pool(self) -> None:
        result = self._volley(_weapon(attacks=2, skill=2, keywords=("sustained_hits_1",)))
        hit = result.hit
        assert hit.critical_hits > 0  # precondition
        assert hit.sustained_extra_hits == hit.critical_hits  # X = 1
        assert hit.hits == hit.roll.successes + hit.sustained_extra_hits
        # The extras are plain hits: the wound step rolls every one of them.
        assert len(result.wound.roll.raw_rolls) == hit.hits

    def test_sustained_hits_scales_with_its_value(self) -> None:
        one = self._volley(_weapon(attacks=2, skill=2, keywords=("sustained_hits_1",)))
        two = self._volley(_weapon(attacks=2, skill=2, keywords=("sustained_hits_2",)))
        # Same seed, same dice: only the multiplier differs.
        assert one.hit.critical_hits == two.hit.critical_hits > 0
        assert two.hit.sustained_extra_hits == 2 * one.hit.sustained_extra_hits

    def test_lethal_hits_skip_the_wound_roll_but_not_the_save(self) -> None:
        result = self._volley(_weapon(attacks=2, skill=2, keywords=("lethal_hits",)))
        hit, wound = result.hit, result.wound
        assert hit.critical_hits > 0  # precondition
        assert hit.auto_wounds == hit.critical_hits
        # Only the non-critical hits rolled to wound...
        assert len(wound.roll.raw_rolls) == hit.hits - hit.auto_wounds
        # ...the auto-wounds joined the pool afterwards, and all face saves.
        assert wound.wounds == wound.roll.successes + hit.auto_wounds
        assert wound.savable_wounds == wound.wounds
        assert len(result.save.roll.raw_rolls) == wound.wounds

    def test_devastating_wounds_diverts_criticals_into_mortals(self) -> None:
        weapon = _weapon(attacks=2, skill=2, strength=8, damage=2, keywords=("devastating_wounds",))
        defender = _sheet("target", toughness=3, save=5, wounds=2)
        result = self._volley(weapon, defender)
        wound, mortal = result.wound, result.mortal
        assert wound.roll.critical_hits > 0  # precondition
        assert wound.diverted_critical_wounds == wound.roll.critical_hits
        assert wound.savable_wounds == wound.wounds - wound.diverted_critical_wounds
        # Saves were rolled only for the non-diverted wounds.
        assert len(result.save.roll.raw_rolls) == wound.savable_wounds
        # Each diverted critical became Damage-many single-wound packets.
        assert mortal.count == wound.diverted_critical_wounds * weapon.damage
        assert mortal.inflicted + mortal.wasted == mortal.count
        # Mortals landed after normal damage, on the damage step's state.
        assert mortal.models_remaining + mortal.models_slain == result.damage.models_remaining
        assert result.models_remaining == mortal.models_remaining
        assert result.wounds_remaining_on_lead == mortal.wounds_remaining_on_lead

    def test_auto_wounds_never_fuel_devastating_wounds(self) -> None:
        # Lethal's auto-wounds skipped the wound roll, so they can't be
        # critical wounds: only rolled natural 6s divert to mortals.
        weapon = _weapon(attacks=2, skill=2, keywords=("lethal_hits", "devastating_wounds"))
        result = self._volley(weapon)
        assert result.hit.auto_wounds > 0  # precondition
        assert result.wound.diverted_critical_wounds == result.wound.roll.critical_hits
        assert result.wound.savable_wounds == (
            result.wound.wounds - result.wound.roll.critical_hits
        )

    def test_keywordless_volley_records_a_mirroring_zero_mortal_step(self) -> None:
        result = self._volley(_weapon(attacks=2, skill=2))
        assert result.mortal.count == 0
        assert result.mortal.models_remaining == result.damage.models_remaining
        assert result.mortal.wounds_remaining_on_lead == result.damage.wounds_remaining_on_lead

    def test_same_seed_same_outcome_with_abilities(self) -> None:
        weapon = _weapon(attacks=2, skill=2, keywords=("sustained_hits_1", "devastating_wounds"))
        assert self._volley(weapon) == self._volley(weapon)


class TestMortalWoundAllocator:
    def test_packets_walk_across_models_and_excess_dies_with_the_unit(self) -> None:
        # 2 models of 2 wounds, lead already on 1: packet 1 fells the lead,
        # packets 2-3 fell the next, packets 4-5 have nobody left to hurt.
        step = _resolve_mortal_wounds(count=5, wounds_per_model=2, wounds_on_lead=1, model_count=2)
        assert (step.inflicted, step.models_slain, step.wasted) == (3, 2, 2)
        assert step.models_remaining == 0
        assert step.wounds_remaining_on_lead == 0

    def test_partial_packet_leaves_a_wounded_lead(self) -> None:
        step = _resolve_mortal_wounds(count=1, wounds_per_model=3, wounds_on_lead=3, model_count=2)
        assert (step.inflicted, step.models_slain, step.wasted) == (1, 0, 0)
        assert step.models_remaining == 2
        assert step.wounds_remaining_on_lead == 2

    def test_zero_count_passes_state_through(self) -> None:
        step = _resolve_mortal_wounds(count=0, wounds_per_model=2, wounds_on_lead=1, model_count=4)
        assert step.models_remaining == 4
        assert step.wounds_remaining_on_lead == 1
        assert step.count == step.inflicted == step.wasted == 0

    def test_already_destroyed_unit_wastes_everything(self) -> None:
        step = _resolve_mortal_wounds(count=3, wounds_per_model=2, wounds_on_lead=1, model_count=0)
        assert (step.inflicted, step.wasted) == (0, 3)
        assert step.models_remaining == 0
