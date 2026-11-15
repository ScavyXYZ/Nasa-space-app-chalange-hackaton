# Mars Explorer — Orbit / Field Station

## Direction

An editorial scientific workstation, not a sci-fi game or generic SaaS page.
Warm charcoal observation deck, bone-paper mission planner, terracotta primary
actions, mint telemetry. Authentic NASA/USGS imagery is the hero; no generated
terrain, fabricated live signals or decorative charts.

## Sources and decisions

Verified `ui-ux-pro-max` recommendations: Swiss hierarchy, neutral operational
dashboard grid, functional sidebar, visible focus, readable data and minimal
motion. The generic landing-page/pink CTA recommendation was rejected as
unsuitable for geospatial planning. Existing React/native inputs and Phosphor
icons are retained; no component-library installation or logic migration.

## Token source

`frontend/src/styles/mission-tokens.css` is the implementation source of truth:

1. Primitive `--orbit-*`: raw palette, spacing, typography and radius.
2. Semantic `--mc-*`: surfaces, text, feedback, paper controls, focus.
3. Component aliases: button fill/hover/text, input border/fill, overlay fill.

Main surfaces: coal `#101312`, paper `#F0EEE6`. Action fill `#ED9069` with dark
text; paper links/focus use dark rust `#A64024`. Dark surface secondary text
uses `#A7AFA8`, paper secondary text `#62665C`. Scientific elevation/soil/
geology colors are data encodings, not decorative brand tokens.

## Type and space

- System Segoe UI / Inter fallback: offline and Cyrillic support.
- Mono only for coordinates, provenance and small operational labels.
- Georgia italic only for the short editorial hero accent.
- Body 12–14px in controls, 13px in editorial cards; no 6px interface labels.
- 4px rhythm; 44px interactive targets, 48px primary action.
- Radii: 6px controls, 10px groups, 16px main surfaces.

## Behaviour

Hover changes color/border, not layout. Native select/details controls keep
keyboard interaction. Map placement, route building and comparison do not
issue camera commands. CSS handles layout without reparenting the map.
Reduced motion disables spinner/transition animation. No polling indicators
or invented computation percentage.

On small screens the atlas appears first; a bottom navigation links atlas,
plan and actual results. Safe-area padding and scroll margins protect content.
The scientific notice remains fully visible after a route result; provenance
details in the planner are progressively disclosed, never deleted.

## Components and states

| Component | Default | Selected/focus | Busy/disabled |
|---|---|---|---|
| Endpoint | paper field with A/B badge | rust border and inset stripe; aria-pressed | editable |
| Build | terracotta, dark label | lighter fill; visible ring | spinner + text + aria-busy; disabled |
| Atlas mode | dark segmented buttons | light active fill + aria-pressed | native disabled |
| Scientific notice | amber border, explicit limitations | same text and action | failure never shows stale route |
| Results | structured metrics/profile/export | keyboard profile control | absent without valid metrics |

## Scope

`mission.css`: full planetary interface, atlas overlays and responsive states.
`local-mission.css`: coordinated styling for existing detailed Jezero tools.
Routing, source data, geographic registration and map engines are unchanged.

## Verification and handoff

- `npm --prefix frontend run build`
- `python tests/smoke_design_browser.py`: 375, 768, 812, 1024, 1440, 1920px;
  keyboard skip link, native scientific disclosure, real result/export UI,
  coordinated local Jezero theme and reduced motion.
- Measured text contrast: paper secondary 5.06:1; coordinate fields 14.82:1;
  active primary action 7.82:1; dark secondary 8.31:1.
- Existing point/route viewport, crater detour, mission, atlas, zoom, regional
  scale and 3D browser regressions pass.
- Atlas ResizeObserver now avoids redundant `invalidateSize` calls, which
  otherwise clear Leaflet's cached centre and can introduce half-pixel drift.
  The observer replaces duplicate window-resize tracking; no focus command
  is added during point placement or route building.

Preview evidence:

- `artifacts/design/mission-desktop-first-fold.png`
- `artifacts/design/mission-mobile-first-fold.png`
- `artifacts/design/mission-results.png`
- `artifacts/design/mission-stories.png`
- `artifacts/design/mission-locations.png`
- `artifacts/design/jezero-desktop.png`
- `artifacts/design/design-report.json`
