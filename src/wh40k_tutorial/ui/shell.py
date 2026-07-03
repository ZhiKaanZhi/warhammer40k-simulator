"""Rich renderables for the three-panel tutorial shell.

Pure builders: every function returns a Rich renderable and does no
printing, so tests can render them to text and the scenario runner
(build phase 5) can drive them from live game state later. The only
place that talks to a real console is ``ui.demo`` / ``wh40k demo``.

Screen layout:

    +---------------------------+--------------+
    | battlefield grid          | rules panel  |
    +---------------------------+ (contextual) |
    | action log                |              |
    +---------------------------+--------------+
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from rich.layout import Layout
from rich.panel import Panel
from rich.text import Text

from wh40k_tutorial.core.scenario import BATTLEFIELD_HEIGHT, BATTLEFIELD_WIDTH

# Kept under the names the rest of the ui package (and its tests) use; the
# single source of truth is core/scenario.py, which validates positions
# against the same dimensions the grid is drawn with.
GRID_WIDTH = BATTLEFIELD_WIDTH
GRID_HEIGHT = BATTLEFIELD_HEIGHT


@dataclass(frozen=True)
class UnitToken:
    """Everything the battlefield needs to draw one unit."""

    glyph: str   # single character drawn on the grid
    color: str   # Rich style, e.g. "bold blue"
    x: int       # column, 0-indexed from the left
    y: int       # row, 0-indexed from the top
    name: str    # shown in the legend
    models: int  # shown in the legend


def render_battlefield(
    tokens: Sequence[UnitToken],
    *,
    width: int = GRID_WIDTH,
    height: int = GRID_HEIGHT,
) -> Panel:
    """Draw the grid with unit glyphs, plus a legend underneath."""
    by_position: dict[tuple[int, int], UnitToken] = {}
    for token in tokens:
        if not (0 <= token.x < width and 0 <= token.y < height):
            raise ValueError(
                f"unit {token.name!r} at ({token.x}, {token.y}) is off the {width}x{height} grid"
            )
        by_position[(token.x, token.y)] = token

    text = Text()
    text.append("   " + "".join(f"{x:^3}" for x in range(width)) + "\n", style="dim")
    for y in range(height):
        text.append(f"{y:>2} ", style="dim")
        for x in range(width):
            token = by_position.get((x, y))
            if token is None:
                text.append(" \u00b7 ", style="dim")
            else:
                text.append(f" {token.glyph} ", style=token.color)
        text.append("\n")

    text.append("\n")
    for token in tokens:
        text.append(f" {token.glyph} ", style=token.color)
        text.append(f"{token.name} \u2014 {token.models} models\n")

    return Panel(text, title="Battlefield", border_style="cyan")


def render_action_log(lines: Sequence[str]) -> Panel:
    """The scrolling record of what happened, one event per line."""
    return Panel(Text("\n".join(lines)), title="Action Log", border_style="green")


def render_rules_panel(heading: str, body: str) -> Panel:
    """The contextual sidebar explaining the rule behind the latest event."""
    text = Text(heading + "\n\n", style="bold")
    text.append(body)
    return Panel(text, title="Rules", border_style="magenta")


def build_shell(battlefield: Panel, action_log: Panel, rules: Panel) -> Layout:
    """Assemble the three panels into the tutorial's screen layout."""
    root = Layout(name="root")
    root.split_row(Layout(name="main", ratio=2), Layout(rules, name="rules", ratio=1))
    root["main"].split_column(
        Layout(battlefield, name="battlefield", minimum_size=16),
        Layout(action_log, name="log"),
    )
    return root
