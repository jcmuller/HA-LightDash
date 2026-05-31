# Changelog
Only a few days old, and LightDash has already had a handful of feature requests and 8 pull requests with contributions from other users! Shout-out to `jcmuller` on GitHub, who contributed quality-of-development improvements to make it easier to work with as a developer, a few fixes for layout bugs and column support, and a bugfix for incorrect data parsing with some entity types. Thanks, Juan!

## v0.10.3 (2026-05-31)
- **Fixed:** External state changes (e.g. toggling a light from HA directly) not
  reflected in frontend — `htmx:sseMessage` handler was reading
  `e.detail.elt` (always `undefined` because the detail is a raw SSE
  `MessageEvent`, not an HTMX event with an `elt` property). Changed to
  `e.target`, which is the element the event was dispatched on (the entity-state
  span).
- **Fixed:** `st()` moved before the guard in `htmx:sseMessage` handler so
  toggle sync runs even if the event target isn't an entity-state span.
- **Fixed:** Same `e.detail.elt` → `e.target` fix in the slider sync
  `htmx:sseMessage` handler (`ss()` function).

## v0.10.2 (2026-05-31)
- **Fixed:** Tile cards with `hide_state: true` (e.g. Porch, Entryway) showing no
  visual state change when toggled — always render hidden entity-state span for
  binary entities so SSE events have a DOM target for icon recoloring.
- **Fixed:** Click handler no longer returns early when toggle switch is absent
  (guard relaxed from `if(!t||!s)return` to `if(!s)return`).
- **Fixed:** `st()` function now toggles `entity-on`/`entity-off` classes even
  when no toggle switch is present, via `if(s)` guard.

## v0.10.1 (2026-05-31)
- **Fixed:** Clock function renamed from `uc()` to `uclk()` to avoid overwriting
  the icon color interpolation function `uc(s)` at global scope.

## v0.10.0 (2026-05-31)
- **Added:** Icon color interpolation — entity card icons now show an amber glow
  when on and dim grey when off, with smooth brightness-aware transitions.
- **Added:** `_icon_color_for_state()` server-side helper and `uc(s)` client-side
  function for real-time color updates via SSE.

## v0.9.2 (2026-05-31)
- **Added:** Diagnostic startup logs in `main.py` and `sse_manager.py`.
- **Changed:** SSE notify log promoted from DEBUG to INFO for operational
  observability.
- **Changed:** File-watcher poll interval increased from 2s to 10s.

## v0.9.1 (2026-05-31)
- **Fixed:** Toggle switches not syncing with entity state on initial page load
  after inline rendering change — `st()` now also runs on `DOMContentLoaded`.

## v0.9.0 (2026-05-31)
- **Optimization:** Removed `pydantic` and `python-dotenv` dependencies — smaller
  container, faster pip install, less memory at runtime.
- **Optimization:** Entity state values now rendered inline during page generation
  instead of 1 HTTP request per entity on page load — eliminates N round-trips
  per dashboard render.
- **Optimization:** Icon SVG cache capped at 200 entries — prevents unbounded
  memory growth across many dashboards.
- **Optimization:** Dashboard file watcher reduced from 2s to 10s polling —
  fewer filesystem hits on SD card storage.
- **Resilience:** HA WebSocket reconnection uses exponential backoff (5s → 120s)
  with random jitter — avoids thundering-herd on supervisor recovery.
- **Resilience:** HA WebSocket auth failures stop retrying instead of spinning
  forever against a hopeless connection.
- **Resilience:** Health endpoint now exposes WebSocket status and active SSE
  client count for easier monitoring.

## v0.8.1 (2026-05-29)
- **Fixed:** Clock cards displaying `--:--` after switching views — the update
  function now runs on every HTMX content swap, not just on page load.

## v0.8.0 (2026-05-29)
- **Experiment:** Tested moving inline HTML/JS into Jinja2 templates, but found it was
  far too slow for lower-CPU Home Assistant devices like the HA Yellow, and reverted to
  the less-clean but much higher performing approach retained, albeit with some flow improvements.

## v0.7.2 (2026-05-29)
- **Optimistic toggle updates** — switches now flip instantly when clicked, no
  waiting for confirmation from Home Assistant. The server confirms silently in
  the background and corrects if needed.
- **Loading pulse animation** — tiles, toggles, sliders, and buttons glow with a
  subtle blue pulse while the command is being sent to Home Assistant if the request takes 
  more than a second or so. Provides visual feedback during the round-trip.

## v0.7.1 (2026-05-29)
- **Fixed:** Inline feature layout for number entities — the up/value/down
  controls now sit flush to the right of the tile name as intended, rather than
  floating in the middle with extra padding.

## v0.7.0 (2026-05-29)
- **Fixed:** Dashboard file watching during startup (the `watch_task` coroutine
  was referenced but never created, preventing clean shutdown).
- **Fixed:** Route handlers no longer crash when escaping HTML output.
- **Added:** `markupsafe` to dependencies.
