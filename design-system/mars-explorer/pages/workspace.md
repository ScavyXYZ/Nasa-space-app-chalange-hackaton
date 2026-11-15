# Current workspace overrides

These rules override the earlier editorial/promotion and terrain-view sections
of `MASTER.md`.

- English only: labels, controls, accessible names, errors, reports and exports.
- The main page contains the planner, globe/2D atlas and computed results only.
- No mission stories, destination cards, discovery search, Jezero promo, demo
  plans, onboarding text, tutorial prompts or empty-state advice.
- No traversability, reliability or safety explanation banners, model-policy
  paragraphs or disclaimer sections in the UI or generated report.
- Keep concise actual errors, numeric results, parameter controls and provider
  credits. Removing explanatory copy does not change routing calculations.
- The globe is an ordinary constant-radius imagery sphere. No adaptive height
  mesh, oblique terrain camera, height exaggeration or local 3D viewer.
- Detailed CTX / HiRISE photos still activate automatically with zoom.
- Do not move the camera when editing/placing points, building/comparing
  routes or showing an error.
- Use a restrained cartographic workstation, not an editorial landing page:
  neutral charcoal surfaces, a muted copper action, green geographic markers,
  system sans typography, monospace only for coordinates and measurements.
- Compact header and an 18px page title. No hero, italic serif heading, decorative
  planet emblem, section numbering, tiny uppercase labels or surface-area facts.
- One flat planner surface with field groups separated by rules. No cream
  sidebar, nested cards, decorative shadows, glass effects or pill controls.
- Give the map the remaining width, use readable 12–13px labels and 44px control
  targets. On mobile, put the atlas first without remounting its component.
- Keep shared tokens and native accessible controls. Mobile Jezero navigation
  must remain visible. Accent is reserved for actions and selected states.

## Guidance

Reviewed the public Impeccable skill and its `distill`, `quieter`, `operate` and
`craft-floor` references: https://github.com/pbakaus/impeccable/tree/main/skill.
Applied the Operate principles: familiar affordances, one font family, flatter
surfaces, fewer redundant headings and no ornamental metrics. The skill engine,
installer, hooks and live mode were not installed or executed.

The focused `ui-ux-pro-max` style search (`dense operational dashboard`) supported
compact, readable tool controls. Its unrelated landing-page/neumorphic design
system output was rejected and not persisted.

QA:

- `tests/test_interface.py`: English source copy, absent removed features.
- `tests/smoke_english_workspace.py`: actual global/local routes, exports,
  English report/PDF, no removed content, no relief requests, responsive layout.
- `tests/smoke_photo_globe_browser.py`: automatic optical imagery.
- `tests/smoke_workstation_design.py`: rendered flat surfaces, compact titles,
  195 control checks across five desktop/mobile sizes, ≥4.5:1 control-text
  contrast, ≥44px control height, visible mobile keyboard focus and preserved
  local map instance/endpoint state when toggling the planner.
- Point/route viewport, GPU coordinate and tile-retention scenarios remain in CI.

Evidence: `artifacts/workspace/`.
