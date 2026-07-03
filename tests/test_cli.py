"""End-to-end CLI tests for `wh40k list` and `wh40k play` (build phase 5).

`play` is exercised through Click's `CliRunner`. Scenario 01 offers exactly
one shooter, one weapon, and one target, so `HumanStrategy` announces each
choice instead of prompting — the run needs no stdin. The seeded run's
casualty numbers are checked against the engine itself (same seed), so the
test asserts real behavior without hard-coding platform-independent dice.
"""

from __future__ import annotations

import random

from click.testing import CliRunner

from wh40k_tutorial import __version__
from wh40k_tutorial.cli import main
from wh40k_tutorial.core.scenario import load_scenario_by_id
from wh40k_tutorial.engine import run_scenario
from wh40k_tutorial.strategies.base import Action
from wh40k_tutorial.strategies.scripted import ScriptedStrategy

SEED = 42


class TestList:
    def test_lists_first_shots(self) -> None:
        result = CliRunner().invoke(main, ["list"])
        assert result.exit_code == 0, result.output
        assert "01_first_shots" in result.output
        assert "First Shots" in result.output
        assert "teaches the four-step combat sequence" in result.output


class TestPlay:
    def _expected_survivors(self) -> int:
        scenario = load_scenario_by_id("01_first_shots")
        strategies = {
            "attacker": ScriptedStrategy(
                [Action("shoot", "marines_1", "bolt_rifle", "termagants_1")]
            ),
            "defender": ScriptedStrategy([]),
        }
        state = run_scenario(scenario, strategies, rng=random.Random(SEED))
        return state.units["termagants_1"].models

    def test_plays_first_shots_end_to_end(self) -> None:
        result = CliRunner().invoke(main, ["play", "01_first_shots", "--seed", str(SEED)])
        assert result.exit_code == 0, result.output
        out = result.output

        # Framing: title, teaches, intro, outro.
        assert "=== First Shots ===" in out
        assert "You play the attacker." in out
        assert "swarm of Tyranid Termagants" in out
        assert "Every shooting attack in 40k follows this exact sequence." in out

        # The shell rendered from live state, and the choices were announced.
        assert "Battlefield" in out
        assert "Action Log" in out
        assert "Unit to shoot with: Intercessor Squad (5 models)" in out
        assert "Weapon: Bolt Rifle" in out
        assert "Target: Termagants (10 models)" in out

        # The volley account, step by step, with the seed-determined outcome.
        assert "Turn 1 — Intercessor Squad fires Bolt Rifle at Termagants." in out
        assert "ATTACKS: 5 models x 2 attacks = 10 dice" in out
        assert "HIT:     need 3+" in out
        assert "WOUND:   need 3+ (S4 vs T3)" in out
        assert "SAVE:    need 6+ (armour 5+, AP -1)" in out
        survivors = self._expected_survivors()
        assert f"{survivors} of 10 remain" in out
        assert f"Termagants — {survivors} models" in out  # final battlefield legend

    def test_unknown_scenario_names_the_available_ones(self) -> None:
        result = CliRunner().invoke(main, ["play", "99_nope"])
        assert result.exit_code != 0
        assert "no scenario named '99_nope'" in result.output
        assert "01_first_shots" in result.output


class TestOtherCommands:
    def test_version(self) -> None:
        result = CliRunner().invoke(main, ["version"])
        assert result.exit_code == 0
        assert __version__ in result.output

    def test_demo_still_renders(self) -> None:
        result = CliRunner().invoke(main, ["demo"])
        assert result.exit_code == 0, result.output
        assert "Battlefield" in result.output
