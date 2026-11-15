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
- Retain the existing charcoal/paper/terracotta/mint design tokens and native
  accessible controls. Mobile Jezero navigation must remain visible.

QA:

- `tests/test_interface.py`: English source copy, absent removed features.
- `tests/smoke_english_workspace.py`: actual global/local routes, exports,
  English report/PDF, no removed content, no relief requests, responsive layout.
- `tests/smoke_photo_globe_browser.py`: automatic optical imagery.
- Point/route viewport, GPU coordinate and tile-retention scenarios remain in CI.

Evidence: `artifacts/workspace/`.
