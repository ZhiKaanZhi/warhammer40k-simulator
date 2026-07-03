"""Tests for the scenario runner (build phase 5).

Follows the project's dice-testing template: exact-outcome tests use a
seeded ``random.Random``. The headline test is a scripted-vs-scripted run of
the packaged scenario 01: with the same seed, the engine's volley must equal
a direct `resolve_shooting` call, and the battlefield state must update to
exactly what the returned `DamageStep` says.
"""

from __future__ import annotations

import random

import pytest

from wh40k_tutorial.core.combat import resolve_shooting
from wh40k_tutorial.core.models import Profile, UnitDatasheet, Weapon, load_faction_by_name
from wh40k_tutorial.core.scenario import (
    Scenario,
    ScenarioSide,
    ScenarioTurn,
    ScenarioUnit,
    load_scenario_by_id,
)
from wh40k_tutorial.engine import BattleState, EngineError, VolleyEvent, run_scenario
from wh40k_tutorial.strategies.base import Action
from wh40k_tutorial.strategies.scripted import ScriptedStrategy

MARINES = load_faction_by_name("space_marines")["intercessor_squad"]
GANTS = load_faction_by_name("tyranids")["termagants"]
BOLT_RIFLE = next(w for w in MARINES.weapons if w.name == "bolt_rifle")

SHOOT = "shoot"


def _scenario(
    attacker_units: tuple[ScenarioUnit, ...],
    defender_units: tuple[ScenarioUnit, ...],
    turns: tuple[ScenarioTurn, ...],
) -> Scenario:
    """Hand-built scenario for engine tests (bypasses the JSON loader on purpose)."""
    return Scenario(
        scenario_id="engine_test",
        title="Engine Test",
        teaches="engine behavior.",
        intro="i",
        player_side="attacker",
        attacker=ScenarioSide("attacker", "space_marines", attacker_units),
        defender=ScenarioSide("defender", "tyranids", defender_units),
        turns=turns,
        outro="o",
    )


def _marines(unit_id: str, x: int, *, models: int = 5) -> ScenarioUnit:
    return ScenarioUnit(unit_id, MARINES, (x, 0), models)


def _gants(unit_id: str, x: int, *, models: int = 10) -> ScenarioUnit:
    return ScenarioUnit(unit_id, GANTS, (x, 4), models)


ONE_ATTACKER_TURN = (ScenarioTurn("shooting", "attacker"),)


# ---------------------------------------------------------------------------
# The headline end-to-end run: scripted vs scripted, seeded
# ---------------------------------------------------------------------------


class TestScriptedVsScriptedEndToEnd:
    SEED = 1234

    def test_first_shots_resolves_and_updates_state(self) -> None:
        scenario = load_scenario_by_id("01_first_shots")
        strategies = {
            "attacker": ScriptedStrategy(
                [Action(SHOOT, "marines_1", "bolt_rifle", "termagants_1")]
            ),
            "defender": ScriptedStrategy([]),  # never consulted: 01 has one attacker turn
        }
        events: list[VolleyEvent] = []
        turn_starts: list[int] = []
        state = run_scenario(
            scenario,
            strategies,
            rng=random.Random(self.SEED),
            on_turn_start=lambda n, turn: turn_starts.append(n),
            on_volley=events.append,
        )

        # The engine's volley must equal a direct pipeline call with the same seed.
        expected = resolve_shooting(
            MARINES, 5, BOLT_RIFLE, GANTS, 1, 10, rng=random.Random(self.SEED)
        )
        assert turn_starts == [1]
        (event,) = events
        assert event.turn == 1
        assert event.phase == "shooting"
        assert event.action.attacker_unit_id == "marines_1"
        assert event.result == expected

        # State updated from the DamageStep, and only for the target.
        gants = state.units["termagants_1"]
        assert gants.models == expected.damage.models_remaining
        assert gants.wounds_on_lead == expected.damage.wounds_remaining_on_lead
        marines = state.units["marines_1"]
        assert marines.models == 5
        assert marines.wounds_on_lead == MARINES.profile.wounds
        assert "marines_1" in state.shot_this_phase

    def test_two_volleys_thread_defender_state(self) -> None:
        """The second volley must see the first one's DamageStep output.

        A 2-wound defender makes the threading visible: the lead model can be
        left mid-wound by volley one, and volley two must start from there.
        """
        tough_sheet = UnitDatasheet(
            key="warriors",
            display_name="Test Warriors",
            faction="tyranids",
            profile=Profile(
                movement=5, toughness=4, save=4, wounds=2, leadership=7, objective_control=2
            ),
            weapons=(BOLT_RIFLE,),
            default_model_count=10,
        )
        defender = ScenarioUnit("warriors_1", tough_sheet, (9, 0), 10)
        scenario = _scenario(
            (_marines("m1", 0), _marines("m2", 1)), (defender,), ONE_ATTACKER_TURN
        )
        strategies = {
            "attacker": ScriptedStrategy(
                [
                    Action(SHOOT, "m1", "bolt_rifle", "warriors_1"),
                    Action(SHOOT, "m2", "bolt_rifle", "warriors_1"),
                ]
            ),
            "defender": ScriptedStrategy([]),
        }
        events: list[VolleyEvent] = []
        seed = 7
        state = run_scenario(
            scenario, strategies, rng=random.Random(seed), on_volley=events.append
        )

        # Replay both volleys off one rng stream, exactly as the engine does.
        rng = random.Random(seed)
        first = resolve_shooting(MARINES, 5, BOLT_RIFLE, tough_sheet, 2, 10, rng=rng)
        assert first.damage.models_remaining > 0, "seed 7 must leave survivors"
        second = resolve_shooting(
            MARINES,
            5,
            BOLT_RIFLE,
            tough_sheet,
            first.damage.wounds_remaining_on_lead,
            first.damage.models_remaining,
            rng=rng,
        )
        assert [e.result for e in events] == [first, second]
        warriors = state.units["warriors_1"]
        assert warriors.models == second.damage.models_remaining
        assert warriors.wounds_on_lead == second.damage.wounds_remaining_on_lead


# ---------------------------------------------------------------------------
# Loop behavior
# ---------------------------------------------------------------------------


class TestTurnLoop:
    def test_battle_ends_when_a_side_is_wiped(self) -> None:
        """Turn 2 never starts once the defender is tabled in turn 1.

        Seed 3 is verified below: five Marines' 10 shots kill the lone
        1-wound Termagant. The defender's empty script would raise if the
        engine wrongly asked it for a turn-2 action.
        """
        scenario = _scenario(
            (_marines("m1", 0),),
            (_gants("g1", 9, models=1),),
            (
                ScenarioTurn("shooting", "attacker"),
                ScenarioTurn("shooting", "defender"),
            ),
        )
        strategies = {
            "attacker": ScriptedStrategy([Action(SHOOT, "m1", "bolt_rifle", "g1")]),
            "defender": ScriptedStrategy([]),
        }
        turn_starts: list[int] = []
        state = run_scenario(
            scenario,
            strategies,
            rng=random.Random(3),
            on_turn_start=lambda n, turn: turn_starts.append(n),
        )
        assert state.units["g1"].destroyed, "seed 3 must table the lone Termagant"
        assert turn_starts == [1]
        assert state.side_wiped("defender")
        assert state.battle_over

    def test_melee_only_side_skips_its_shooting_phase(self) -> None:
        melee_sheet = UnitDatasheet(
            key="boys",
            display_name="Melee Boys",
            faction="orks",
            profile=Profile(
                movement=6, toughness=5, save=5, wounds=1, leadership=7, objective_control=2
            ),
            weapons=(
                Weapon(
                    name="choppa",
                    display_name="Choppa",
                    type="melee",
                    range=0,
                    attacks=2,
                    skill=3,
                    strength=4,
                    ap=0,
                    damage=1,
                ),
            ),
            default_model_count=10,
        )
        scenario = _scenario(
            (ScenarioUnit("boys_1", melee_sheet, (0, 0), 10),),
            (_gants("g1", 9),),
            ONE_ATTACKER_TURN,
        )
        # An empty script would raise if the engine wrongly asked for an action.
        strategies = {
            "attacker": ScriptedStrategy([]),
            "defender": ScriptedStrategy([]),
        }
        events: list[VolleyEvent] = []
        state = run_scenario(scenario, strategies, on_volley=events.append)
        assert events == []
        assert state.units["g1"].models == 10

    def test_missing_strategy_is_an_engine_error(self) -> None:
        scenario = _scenario((_marines("m1", 0),), (_gants("g1", 9),), ONE_ATTACKER_TURN)
        with pytest.raises(EngineError, match="defender"):
            run_scenario(scenario, {"attacker": ScriptedStrategy([])})

    def test_battle_state_from_scenario_snapshot(self) -> None:
        scenario = _scenario((_marines("m1", 0),), (_gants("g1", 9),), ONE_ATTACKER_TURN)
        state = BattleState.from_scenario(scenario)
        assert state.units["m1"].wounds_on_lead == MARINES.profile.wounds
        snap = state.snapshot()
        assert snap.unit("g1").models == 10
        assert not snap.unit("m1").has_shot


# ---------------------------------------------------------------------------
# Illegal actions from a strategy fail loudly
# ---------------------------------------------------------------------------


class TestActionValidation:
    def _run(self, *actions: Action, defenders: tuple[ScenarioUnit, ...] | None = None):
        scenario = _scenario(
            (_marines("m1", 0), _marines("m2", 1)),
            defenders or (_gants("g1", 9), _gants("g2", 10)),
            ONE_ATTACKER_TURN,
        )
        strategies = {
            "attacker": ScriptedStrategy(list(actions)),
            "defender": ScriptedStrategy([]),
        }
        return run_scenario(scenario, strategies, rng=random.Random(0))

    def test_unknown_action_kind(self) -> None:
        with pytest.raises(EngineError, match="'charge'"):
            self._run(Action("charge", "m1", "bolt_rifle", "g1"))

    def test_unknown_attacker(self) -> None:
        with pytest.raises(EngineError, match="'ghost'"):
            self._run(Action(SHOOT, "ghost", "bolt_rifle", "g1"))

    def test_attacker_on_wrong_side(self) -> None:
        with pytest.raises(EngineError, match="not the active side"):
            self._run(Action(SHOOT, "g1", "fleshborer", "m1"))

    def test_unknown_weapon(self) -> None:
        with pytest.raises(EngineError, match="'plasma_gun'"):
            self._run(Action(SHOOT, "m1", "plasma_gun", "g1"))

    def test_melee_weapon_cannot_shoot(self) -> None:
        with pytest.raises(EngineError, match="melee"):
            self._run(Action(SHOOT, "m1", "close_combat_weapon", "g1"))

    def test_target_on_own_side(self) -> None:
        with pytest.raises(EngineError, match="your own"):
            self._run(Action(SHOOT, "m1", "bolt_rifle", "m2"))

    def test_unknown_target(self) -> None:
        with pytest.raises(EngineError, match="'ghost'"):
            self._run(Action(SHOOT, "m1", "bolt_rifle", "ghost"))

    def test_unit_cannot_shoot_twice_in_a_phase(self) -> None:
        with pytest.raises(EngineError, match="already shot"):
            self._run(
                Action(SHOOT, "m1", "bolt_rifle", "g1"),
                Action(SHOOT, "m1", "bolt_rifle", "g2"),
            )

    def test_destroyed_target_is_rejected(self) -> None:
        """Seed 0 is verified in-test: m1's volley tables the lone Termagant;
        m2's scripted shot at the corpse must then be rejected (g2 survives,
        so the phase is still running)."""
        with pytest.raises(EngineError, match="already destroyed"):
            self._run(
                Action(SHOOT, "m1", "bolt_rifle", "g1"),
                Action(SHOOT, "m2", "bolt_rifle", "g1"),
                defenders=(_gants("g1", 9, models=1), _gants("g2", 10)),
            )

    def test_seed_zero_really_tables_the_lone_termagant(self) -> None:
        result = resolve_shooting(MARINES, 5, BOLT_RIFLE, GANTS, 1, 1, rng=random.Random(0))
        assert result.damage.models_remaining == 0
