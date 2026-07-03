"""Terminal UI built with the Rich library.

Three regions (see `shell.py`):
- battlefield grid (12x8 by default), units rendered as colored glyphs
- action log, scrolling, showing every dice roll and what it meant
- rules panel, sidebar, contextual to whatever just happened

Build-phase-4 status: the static shell and a hard-coded demo scene are
implemented (`wh40k demo`). Wiring the panels to live game state happens
with the scenario runner (build phase 5).
"""
