# Design system (demo view, pitch deck, architecture diagram)

Subject: remote assistance for autonomous vehicles in a city. The visual language comes from the street itself: asphalt,
lane markings, roadworks barriers, and US highway signage.

## Color
| Token | Hex | Role |
|---|---|---|
| asphalt | `#2E3438` | page background (a mid-dark road grey, not near-black) |
| kerb | `#3B4246` | raised surfaces: panels, zone tiles |
| lane | `#E8EBE4` | primary text and lane markings (a cool off-white, not cream) |
| verge | `#9AA39E` | secondary text, grid lines |
| hi-vis | `#F2B33D` | THE accent: the agent, its tool calls, roadworks hatching |
| stop | `#E5624B` | semantic only: advice rejected by code, closed zones |
| go | `#7CC5A1` | semantic only: advice accepted |

One accent (hi-vis). Stop and go appear only as safety-check states, never as decoration.

## Type
- **Barlow Condensed** (600/700) for display: headlines, zone labels, big numbers. Barlow is drawn from California highway signage,
  the same streets robotaxis are tested on.
- **Barlow** (400/500) for body and UI text. Tabular numerals (`font-variant-numeric: tabular-nums`) for every metric.
- Sentence case everywhere. No all-caps labels, no monospace labels.

## Shape and texture
- Radius: 4px on panels and tiles, nothing rounder. Sign-plate corners, not app cards.
- The signature element: **a closed zone is drawn with roadworks barrier hatching** (diagonal hi-vis/asphalt stripes). This is the
  one memorable thing; everything else stays quiet.
- No shadows. Separation comes from the kerb/asphalt tone step.

## Layout
- Demo: the city grid on the left (about 60%), the agent's live log on the right; the verdict banner across the bottom of the grid.
- Deck: 16:9, left-aligned, one idea per slide, max ~25 words of body per slide.

## Motion
One orchestrated moment: when the validator rejects advice, the proposed route draws onto the grid, hits the hatched zone, and
turns stop-red. Everything else appears without animation. Honour `prefers-reduced-motion`.
