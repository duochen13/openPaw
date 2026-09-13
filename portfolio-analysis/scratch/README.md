# scratch

Throwaway spikes, not part of the shipped pipeline.

## `preview_render.py`

A preview of the Plan 4 `render` stage, written early to see the shape of the
data before Plans 2-4 exist.
It reads `data/prices.sqlite` and `data/moves/META.json` and writes
`out/META-preview.html`.

It is **not** `src/portfolio_analysis/render.py` and should not be mistaken for it.
Plan 4 will specify the real renderer; this exists so that plan can be written
against something seen rather than imagined.

What it already gets right, and what Plan 4 should keep:

- Both series indexed to 100 at the series start, so there is one shared y-axis.
  A dual-axis chart would be the single worst mistake available here.
- Log y-scale, because the subject is percentage moves and META ranges from
  index 34 to 280 over the window; on a linear scale the 2022 drawdown compresses
  into illegibility.
- The price lines are achromatic (META solid ink, QQQ dashed grey) and the whole
  colour budget goes to move direction. The obvious alternative - META blue, QQQ
  orange, red/blue markers - puts a blue "up" marker on a blue META line, where
  one colour means two things.
- Marker palette validated with the dataviz skill's checker rather than by eye:
  CVD dE 21.6 light / 19.2 dark against a target of 8, normal-vision 32.3 / 29.0
  against a floor of 15, contrast >= 3:1 both modes.
- Dark mode is a selected set of steps, not an automatic inversion.
- A table view carries every value, so nothing is encoded by colour alone.

What is deliberately empty: the reported-claims and reason half of the card.
Events arrive in Plan 2 and attribution in Plan 3.
The card says so in place rather than showing a plausible-looking blank.
