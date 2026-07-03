"""Tests for the phase-4 UI shell.

Rich renderables are rendered to plain text with a recording console and
asserted on as strings — no real terminal involved. Grid rows are found by
their empty-cell dots, which only appear on battlefield rows.
"""

from __future__ import annotations

import pytest
from rich.console import Console

from wh40k_tutorial.ui.demo import DEMO_TOKENS, build_demo_shell
from wh40k_tutorial.ui.shell import (
    GRID_HEIGHT,
    GRID_WIDTH,
    UnitToken,
    render_battlefield,
)


def _to_text(renderable: object, *, width: int = 110, height: int = 34) -> str:
    console = Console(width=width, height=height, record=True, color_system=None)
    console.print(renderable)
    return console.export_text()


def _grid_rows(text: str) -> list[str]:
    return [line for line in text.splitlines() if "\u00b7" in line]


class TestBattlefield:
    def test_tokens_land_on_their_row_in_order(self) -> None:
        rows = _grid_rows(_to_text(render_battlefield(DEMO_TOKENS), height=20))
        assert len(rows) == GRID_HEIGHT
        marines_row = rows[4]  # both demo units stand on row y=4
        assert "M" in marines_row and "T" in marines_row
        assert marines_row.index("M") < marines_row.index("T")  # marines on the left
        for y, row in enumerate(rows):
            if y != 4:
                assert "M" not in row and "T" not in row

    def test_grid_has_all_rows_and_column_axis(self) -> None:
        text = _to_text(render_battlefield(()), height=20)
        assert len(_grid_rows(text)) == GRID_HEIGHT
        assert str(GRID_WIDTH - 1) in text  # rightmost column label ("11")

    def test_legend_lists_units_with_model_counts(self) -> None:
        text = _to_text(render_battlefield(DEMO_TOKENS), height=20)
        assert "Intercessor Squad \u2014 5 models" in text
        assert "Termagants \u2014 10 models" in text

    def test_off_grid_token_is_rejected(self) -> None:
        rogue = UnitToken(glyph="X", color="red", x=GRID_WIDTH, y=0, name="Rogue", models=1)
        with pytest.raises(ValueError, match="off the"):
            render_battlefield([rogue])


class TestShell:
    def test_demo_shell_shows_all_three_regions(self) -> None:
        text = _to_text(build_demo_shell())
        assert "Battlefield" in text
        assert "Action Log" in text
        assert "Rules" in text

    def test_demo_shell_carries_the_sample_scene(self) -> None:
        text = _to_text(build_demo_shell())
        assert "Intercessor Squad" in text
        assert "static demo" in text
        assert "The hit roll" in text
