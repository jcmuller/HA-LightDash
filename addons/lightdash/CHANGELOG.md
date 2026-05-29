# Changelog
Only a few days old, and LightDash has already had a handful of feature requests and 8 pull requests with contributions from other users! Shout-out to `jcmuller` on GitHub, who contributed quality-of-development improvements to make it easier to work with as a developer, a few fixes for layout bugs and column support, and a bugfix for incorrect data parsing with some entity types. Thanks, Juan!

## v0.8.1 (2026-05-29)
- **Fixed:** Clock cards displaying `--:--` after switching views — the update
  function now runs on every HTMX content swap, not just on page load.

## v0.8.0 (2026-05-29)
- **Rollback:** Replaced Jinja2 template rendering with inline f-string HTML.
  Jinja2 was too heavy for low-powered Home Assistant containers and added an
  extra dependency without meaningful benefit for this project's rendering needs.
- **Kept:** Optimistic toggle updates, loading pulse animation, and all CSS
  improvements from v0.7.1–v0.7.2.
- **Removed:** `jinja2` and `markupsafe` from dependencies.

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
