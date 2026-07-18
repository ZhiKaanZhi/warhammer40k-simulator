"""Tests for the heuristic AI opponent (`strategies.heuristic`).

Behavioral contract: enumerate legal shots, score each by expected damage
capped at the target's remaining wounds, pick the best, and break ties by
keeping the earliest candidate in snapshot (scenario) order — fully
deterministic, so seeded end-to-end tests stay exact.
"""

from __future__ import annotations

import random

from wh40k_tutorial.core.models import UnitDatasheet, load_faction_by_name
from wh40k_tutorial.core.scenario import load_scenario_by_id
from wh40k_tutorial.engine import VolleyEvent, run_scenario
from wh40k_tutorial.strategies.base import Action, GameState, UnitSnapshot
from wh40k_tutorial.strategies.heuristic import HeuristicStrategy
from wh40k_tutorial.strategies.scripted import ScriptedStrategy

MARINES = load_faction_by_name("space_marines")["intercessor_squad"]
GANTS = load_faction_by_name("tyranids")["termagants"]
WARRIORS = load_faction_by_name("necrons")["necron_warriors"]
IMMORTALS = load_faction_by_name("necrons")["immortals"]
TAU = load_faction_by_name("tau_empire")["strike_team"]


def _snap(
    unit_id: str,
    side: str,
    sheet: UnitDatasheet,
    *,
    models: int | None = None,
    wounds_on_lead: int | None = None,
    has_shot: bool = False,
    has_fought: bool = False,
    loadout: tuple[str, ...] = (),
    position: tuple[int, int] | None = None,
) -> UnitSnapshot:
    resolved = sheet.default_model_count if models is None else models
    # Distances matter now (ADR 0007): unless a test places a unit itself,
    # attackers stand at (2, 4) and defenders at (8, 4) — 6 squares = 12"
    # apart, inside every fixture weapon's range and safely unengaged.
    if position is None:
        position = (2, 4) if side == "attacker" else (8, 4)
    return UnitSnapshot(
        unit_id=unit_id,
        side=side,
        datasheet=sheet,
        position=position,
        models=resolved,
        wounds_on_lead=(
            (sheet.profile.wounds if resolved > 0 else 0)
            if wounds_on_lead is None
            else wounds_on_lead
        ),
        has_shot=has_shot,
        has_fought=has_fought,
        loadout=loadout,
    )


def _state(
    *units: UnitSnapshot, active_side: str = "attacker", phase: str = "shooting"
) -> GameState:
    return GameState(turn=1, phase=phase, active_side=active_side, units=units)


class TestTargetChoice:
    def test_picks_the_softer_of_two_targets(self) -> None:
        # The scenario-06 situation: pulse rifles expect double the damage
        # into Warriors (T4, 4+) versus Immortals (T5, 3+).
        state = _state(
            _snap("tau_1", "attacker", TAU),
            _snap("immortals_1", "defender", IMMORTALS),
            _snap("warriors_1", "defender", WARRIORS),
        )
        action = HeuristicStrategy().choose_action(state)
        assert action.target_unit_id == "warriors_1"
        assert action.weapon_key == "pulse_rifle"

    def test_overkill_cap_prefers_the_fuller_unit(self) -> None:
        # Raw expected damage into any Termagant unit is ~3.7 per marine
        # volley; against a single surviving gant the cap scores it 1, so
        # the full unit draws the fire.
        state = _state(
            _snap("marines_1", "attacker", MARINES),
            _snap("last_gant", "defender", GANTS, models=1),
            _snap("swarm", "defender", GANTS, models=10),
        )
        action = HeuristicStrategy().choose_action(state)
        assert action.target_unit_id == "swarm"

    def test_ties_keep_the_earliest_candidate(self) -> None:
        state = _state(
            _snap("marines_1", "attacker", MARINES),
            _snap("gants_a", "defender", GANTS),
            _snap("gants_b", "defender", GANTS),
        )
        action = HeuristicStrategy().choose_action(state)
        assert action.target_unit_id == "gants_a"

    def test_deterministic_for_the_same_state(self) -> None:
        state = _state(
            _snap("tau_1", "attacker", TAU),
            _snap("warriors_1", "defender", WARRIORS),
            _snap("immortals_1", "defender", IMMORTALS),
        )
        strategy = HeuristicStrategy()
        assert strategy.choose_action(state) == strategy.choose_action(state)


class TestWeaponAndShooterChoice:
    def test_picks_the_better_carried_weapon(self) -> None:
        # Both Immortal guns in the loadout, shooting Termagants: the tesla
        # carbine's sustained hits out-damage the gauss blaster's lethal
        # hits against a 5+ save.
        state = _state(
            _snap(
                "immortals_1",
                "attacker",
                IMMORTALS,
                loadout=("gauss_blaster", "tesla_carbine"),
            ),
            _snap("gants_1", "defender", GANTS),
        )
        action = HeuristicStrategy().choose_action(state)
        assert action.weapon_key == "tesla_carbine"

    def test_respects_a_narrowing_loadout_override(self) -> None:
        state = _state(
            _snap("immortals_1", "attacker", IMMORTALS, loadout=("tesla_carbine",)),
            _snap("marines_1", "defender", MARINES),
        )
        action = HeuristicStrategy().choose_action(state)
        assert action.weapon_key == "tesla_carbine"

    def test_units_that_already_shot_are_skipped(self) -> None:
        state = _state(
            _snap("warriors_1", "attacker", WARRIORS, has_shot=True),
            _snap("immortals_1", "attacker", IMMORTALS),
            _snap("gants_1", "defender", GANTS),
        )
        action = HeuristicStrategy().choose_action(state)
        assert action.attacker_unit_id == "immortals_1"

    def test_out_of_range_targets_are_not_candidates(self) -> None:
        """04.02 via ADR 0007: a Shoota (18" = 9 squares) cannot reach 11.

        The far swarm is the higher-EV target (more wounds left to cap
        against) — but it is out of reach, so the near handful gets shot."""
        state = _state(
            _snap("boyz", "attacker", ORKS, position=(0, 0)),
            _snap("near_few", "defender", GANTS, position=(5, 4), models=5),
            _snap("far_swarm", "defender", GANTS, position=(11, 7), models=20),
        )
        action = HeuristicStrategy().choose_action(state)
        assert action.target_unit_id == "near_few"


class TestEndToEnd:
    def test_scenario_06_ai_fires_at_the_warriors(self) -> None:
        # Heuristic vs heuristic on the packaged scenario, seeded: every
        # T'au volley must land on the Warriors while they stand — the
        # scenario's whole lesson.
        scenario = load_scenario_by_id("06_return_fire")
        events: list[VolleyEvent] = []
        run_scenario(
            scenario,
            {"attacker": HeuristicStrategy(), "defender": HeuristicStrategy()},
            rng=random.Random(11),
            on_volley=events.append,
        )
        tau_volleys = [e for e in events if e.action.attacker_unit_id == "strike_team_1"]
        assert tau_volleys, "the T'au never got to return fire"
        assert all(e.action.target_unit_id == "warriors_1" for e in tau_volleys)


ORKS = load_faction_by_name("orks")["boyz"]


class TestFightChoice:
    """The same brain, asked in a fight phase: fighter x melee weapon x
    ENGAGED enemy, scored by capped expected damage."""

    def test_returns_a_fight_action_with_the_melee_weapon(self) -> None:
        state = _state(
            _snap("boyz", "attacker", ORKS, position=(4, 4)),
            _snap("marines", "defender", MARINES, position=(5, 4)),
            phase="fight",
        )
        action = HeuristicStrategy().choose_action(state)
        assert action == Action("fight", "boyz", "choppa", "marines")

    def test_only_engaged_enemies_are_candidates(self) -> None:
        # Termagants score higher for choppas (T3, Sv5+) than Marines — but
        # they are out of reach, so the engaged Marines must win.
        state = _state(
            _snap("boyz", "attacker", ORKS, position=(4, 4)),
            _snap("marines", "defender", MARINES, position=(5, 4)),
            _snap("gants", "defender", GANTS, position=(9, 4), models=20),
            phase="fight",
        )
        action = HeuristicStrategy().choose_action(state)
        assert action.target_unit_id == "marines"

    def test_picks_the_softer_of_two_engaged_targets(self) -> None:
        # Both in reach: choppas expect far more damage into T3/Sv5+ gants
        # than into T4/Sv3+ marines, and 20 gants leave headroom for the cap.
        state = _state(
            _snap("boyz", "attacker", ORKS, position=(4, 4)),
            _snap("marines", "defender", MARINES, position=(4, 3)),
            _snap("gants", "defender", GANTS, position=(4, 5), models=20),
            phase="fight",
        )
        action = HeuristicStrategy().choose_action(state)
        assert action.target_unit_id == "gants"

    def test_greedy_pick_orders_its_own_fights_deadliest_first(self) -> None:
        # Two eligible fighters in separate combats: the pick with the higher
        # capped expected damage goes first — 10 Boyz into gants beats 5
        # Marines into gants, whatever the order they appear in.
        state = _state(
            _snap("marines", "attacker", MARINES, position=(2, 2)),
            _snap("boyz", "attacker", ORKS, position=(6, 6)),
            _snap("gants_a", "defender", GANTS, position=(2, 3), models=20),
            _snap("gants_b", "defender", GANTS, position=(6, 7), models=20),
            phase="fight",
        )
        action = HeuristicStrategy().choose_action(state)
        assert action.attacker_unit_id == "boyz"

    def test_units_that_already_fought_are_skipped(self) -> None:
        state = _state(
            _snap("boyz", "attacker", ORKS, position=(4, 4), has_fought=True),
            _snap("marines", "attacker", MARINES, position=(6, 4)),
            _snap("gants", "defender", GANTS, position=(5, 4), models=20),
            phase="fight",
        )
        action = HeuristicStrategy().choose_action(state)
        assert action.attacker_unit_id == "marines"

    def test_fight_phase_scores_by_the_asked_side(self) -> None:
        # In a fight phase the engine asks each side in turn; eligibility is
        # read from active_side, not hardcoded to the attacker.
        state = _state(
            _snap("boyz", "attacker", ORKS, position=(4, 4)),
            _snap("marines", "defender", MARINES, position=(5, 4)),
            active_side="defender",
            phase="fight",
        )
        action = HeuristicStrategy().choose_action(state)
        assert action == Action("fight", "marines", "close_combat_weapon", "boyz")


class TestFightEndToEnd:
    def test_heuristic_defender_fights_back_through_the_engine(self) -> None:
        """A hand-built two-combat fight turn: the scripted player fights,
        and the heuristic opponent answers by itself — deadliest fight first,
        counting only its survivors."""
        from wh40k_tutorial.core.scenario import (
            Scenario,
            ScenarioSide,
            ScenarioTurn,
            ScenarioUnit,
        )

        scenario = Scenario(
            scenario_id="fight_ai_test",
            title="t",
            teaches="x.",
            intro="i",
            player_side="attacker",
            attacker=ScenarioSide(
                "attacker", "orks", (ScenarioUnit("boyz", ORKS, (4, 4), 10),)
            ),
            defender=ScenarioSide(
                "defender",
                "space_marines",
                (ScenarioUnit("marines", MARINES, (5, 4), 5),),
            ),
            turns=(ScenarioTurn("fight", "attacker"),),
            outro="o",
            opponent_strategy="heuristic",
        )
        events: list[VolleyEvent] = []
        run_scenario(
            scenario,
            {
                "attacker": ScriptedStrategy(
                    [Action("fight", "boyz", "choppa", "marines")]
                ),
                "defender": HeuristicStrategy(),
            },
            rng=random.Random(20),
            on_volley=events.append,
        )
        boyz_swing, marine_answer = events
        assert marine_answer.action == Action(
            "fight", "marines", "close_combat_weapon", "boyz"
        )
        assert (
            marine_answer.result.attack.attacker_models
            == boyz_swing.result.models_remaining
        )
