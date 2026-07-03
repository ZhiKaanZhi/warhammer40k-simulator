"""Terminal UI built with the Rich library.

Three regions (see `shell.py`):
- battlefield grid (12x8 by default), units rendered as colored glyphs
- action log, scrolling, showing every dice roll and what it meant
- rules panel, sidebar, contextual to whatever just happened

The static shell (`shell.py`, `wh40k demo`) landed in build phase 4;
`live.py` (build phase 5) drives the same builders from live game state and
formats each volley's plain step-by-step account. The rules panel shows a
placeholder until the narrator (build phase 6) supplies real explanations.
"""
