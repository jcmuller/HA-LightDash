LightDash
=========

A lightweight, self-contained dashboard renderer for Home Assistant. Define
dashboards in YAML — LightDash renders them as a single-page app with live
entity state updates via SSE, toggle switches, brightness sliders, and more.

Instead of running HA's full Lovelace frontend, LightDash is a focused,
low-ceremony alternative: no Node.js build step, no custom-card compatibility
matrix, just plain HTML + CSS + htmx served from a Python/FastAPI process.


Quick Start
-----------

**Local dev:**

    cp .env.example .env    # edit HA_URL and HA_TOKEN
    pip install -r requirements.txt
    python3 -m uvicorn app.main:app --reload

Drop YAML files into `config/` — each file becomes a dashboard at
`/d/{filename_without_ext}`.

**HA add-on:**

Add `https://github.com/richkershaw/HA-LightDash` as an add-on repository in
HA Supervisor → Settings → Add-ons → Repositories. Install LightDash and
configure dashboards inline on the Configuration tab.

**Required:** HA instance with `homeassistant_api: true` (Supervisor proxy).


YAML Dashboard Format
---------------------

A dashboard is a YAML file with a top-level `views` key:

```yaml
views:
  - title: Living Room
    path: living
    icon: mdi:sofa
    bg_image: /api/image/serve/abc123/original
    type: sections
    max_columns: 4
    sections:
      - type: grid
        cards:
          - type: tile
            entity: light.porch
            features:
              - type: light-brightness
            features_position: inline
```

**View fields:**

| Field        | Description                                        |
|--------------|----------------------------------------------------|
| `title`      | Display title (also used in `<title>`)             |
| `path`       | URL path segment (defaults to slug of title)       |
| `icon`       | MDI icon (shown in view index)                     |
| `bg_color`   | CSS background-color                               |
| `bg_image`   | Background image URL                               |
| `type`       | View layout type (`sections` or `custom:layout-card`) |
| `max_columns`| Column count for max-width grid                    |

When `type: custom:layout-card` is used, the parser groups cards into grid
sections split by `custom:layout-break` card entries. The `layout.max_cols`
value determines section column count.

**Section fields** (inside `sections: [...]`):

| Field     | Description                          |
|-----------|--------------------------------------|
| `type`    | Section type (`grid`)                |
| `columns` | Number of grid columns               |

**Grid options on cards** (inside `grid_options: {...}`):

| Field     | Description                          |
|-----------|--------------------------------------|
| `columns` | Span this many columns               |
| `rows`    | Span this many rows                  |


Supported Card Types
--------------------

### tile

A rich card showing entity icon, name, state, and optional controls.

```yaml
type: tile
entity: light.living_room
name: Living Room
icon: mdi:lamp
color: yellow              # tint icon (yellow/orange/red/pink/purple/blue/green/teal)
vertical: true             # stack icon above info
hide_state: true           # hide entity state & toggle
features_position: inline   # or "bottom" (default)
features:
  - type: light-brightness
  - type: light-color-temp
  - type: numeric-input
```

Features:

| Feature            | Description                                     |
|--------------------|-------------------------------------------------|
| `light-brightness` | Range slider (0–100%), posts `light.turn_on`    |
| `light-color-temp` | Range slider (153–500 mired), posts `light.turn_on` |
| `numeric-input`    | Decrement/increment buttons, posts `input_number.decrement/increment` |

Binary-domain entities (`light`, `switch`, `fan`, `input_boolean`) get a
toggle switch. Non-binary entities show state text.

### entities

A grouped list of entity rows, each with icon, name, state, and controls.

```yaml
type: entities
title: Lights
entities:
  - entity: light.dining_room
  - entity: light.kitchen
    name: Kitchen
    icon: mdi:counter
  - entity: cover.kitchen_roof
    icon: mdi:window-closed
  - type: divider           # horizontal rule
  - type: section           # section header
    name: Other
```

Cover entities automatically get open/stop/close buttons.
Binary non-cover entities get a toggle switch.

### button

A compact action button. Supports `tap_action`.

```yaml
type: button
name: Other Rooms
icon: mdi:arrow-right-bold
tap_action:
  action: navigate
  navigation_path: other-rooms
```

### glance

A grid of entity icons with names and state, organised in columns.

```yaml
type: glance
title: Sensors
columns: 3
entities:
  - sensor.temperature
  - entity: sensor.humidity
    icon: mdi:water-percent
    tap_action:
      action: toggle
```

### entity

A single-row entity card.

```yaml
type: entity
entity: sensor.temperature
name: Temp
icon: mdi:thermometer
```

### heading

```yaml
type: heading
heading: Living Room
icon: mdi:sofa
```

### markdown

Simple markdown rendering with bold, italic, code, links, lists, and headers.
**HA Jinja2 template syntax (`{{`, `{%`) is not supported.** Use a `clock`
card for time display instead.

```yaml
type: markdown
content: |
  # Hello
  **bold** and *italic*
```

### clock

Digital clock card with timezone and format support. Updates every 30 seconds
via JS `Intl.DateTimeFormat`.

```yaml
type: clock
time_zone: Europe/London
time_format: "24"           # or "12"
show_seconds: false
clock_size: large           # small / medium / large
no_background: true
```

### sensor

```yaml
type: sensor
entity: sensor.temperature
name: Outside
graph: line                 # or leave unset
hours_to_show: 24
```

### gauge

```yaml
type: gauge
entity: sensor.battery
min: 0
max: 100
severity:
  green: 40
  yellow: 20
  red: 0
```

### history-graph / statistics-graph

```yaml
type: history-graph
title: Temperature
entities:
  - sensor.outdoor_temp
hours_to_show: 24
```

Requires uPlot (loaded from CDN).

### light

A legacy light card with toggle + brightness slider (all-in-one).

```yaml
type: light
entity: light.living_room
name: Ceiling
```

### grid / horizontal-stack / vertical-stack

Nested card layouts:

```yaml
type: grid
columns: 2
cards:
  - type: entity
    entity: sensor.a
  - type: entity
    entity: sensor.b
```

### conditional

Shows/hides a child card based on entity state conditions:

```yaml
type: conditional
conditions:
  - entity: light.test
    state: "on"
card:
  type: entity
  entity: sensor.a
```

### iframe

```yaml
type: iframe
url: https://example.com
aspect_ratio: "50%"
```

### placeholder

Rendered when a card type is unknown. Displays a `?` placeholder.


Tap Actions
-----------

Cards can define a `tap_action` configuration:

| Action           | Effect                                                     |
|------------------|------------------------------------------------------------|
| `toggle`         | Posts entity toggle to HA                                  |
| `call-service`   | Calls an arbitrary HA service                              |
| `navigate`       | Navigates to another view within the same dashboard        |
| `url`            | Opens a URL in a new tab                                   |

```yaml
tap_action:
  action: call-service
  service: light.turn_on
  target:
    entity_id: light.living_room
  data:
    brightness_pct: 100
```


Architecture
------------

```
┌──────────────────────────────────────────────────────────────────┐
│                        LightDash (FastAPI)                       │
│                                                                  │
│  ┌──────────┐   ┌──────────┐   ┌──────────────┐                 │
│  │  parser   │◄──│  config  │◄──│  *yaml files  │  or inline     │
│  │  .py      │   │  .py     │   │  config/      │  add-on config │
│  └────┬─────┘   └──────────┘   └──────────────┘                 │
│       │ Dashboard / View / Card models                           │
│       ▼                                                          │
│  ┌──────────┐                                                    │
│  │ renderer │────► HTML + CSS + JS  (htmx + SSE)                │
│  │  .py     │                                                    │
│  └──────────┘                                                    │
│       │                                                          │
│  ┌──────────┐   ┌──────────────┐                                 │
│  │ compat   │   │  ha_client   │◄── HTTP POST /api/services/...  │
│  │  .py     │   │  .py         │◄── GET  /api/states/...         │
│  └──────────┘   └──────┬───────┘                                 │
│                        │                                         │
│  ┌──────────┐          │                                         │
│  │   sse    │◄─────────┘  WebSocket /api/websocket              │
│  │ manager  │──► SSE /_sse  (entity state events)               │
│  └──────────┘                                                    │
└──────────────────────────────────────────────────────────────────┘
        │
        │  Ingress (add-on) or direct HTTP (local dev)
        ▼
┌──────────────────┐       ┌────────────────────┐
│  Browser (client)│◄─────►│  Home Assistant    │
│  - htmx v2       │   SSE │  - REST API        │
│  - htmx-sse ext  │       │  - WebSocket       │
│  - live updates  │       └────────────────────┘
└──────────────────┘
```

**Data flow:**

1. **Startup** — YAML dashboard files are parsed into `Dashboard`/`View`/`Card`
   model objects. Custom HA card types (`custom:mushroom-*`,
   `custom:layout-card`) are mapped to native LightDash equivalents.

2. **Navigation** — `GET /d/{name}` redirects (302) to the first view.
   `GET /d/{name}/view/{path}` renders a full HTML page.

3. **Rendering** — The renderer walks view cards/sections, generates HTML with
   htmx attributes for live interactions, SSE event attributes for live state
   updates, and inline CSS/JS for sliders, toggles, and clock.

4. **Live updates** — The SSE manager connects to the HA WebSocket API,
   subscribes to `state_changed` events, and relays entity state changes to
   connected browser clients via Server-Sent Events. htmx's
   `sse-swap` attribute updates entity state spans in-place.

5. **Actions** — Toggle switches, sliders, and tap actions POST to `/action`,
   which forwards service calls to the HA REST API.

6. **Toggle sync** — A JS function (`st()`) runs after every htmx swap and
   SSE message, synchronising toggle switch positions and dimming classes with
   the rendered entity state text.

7. **Slider sync** — A JS function (`ss()`) runs after SSE messages for views
   with brightness/color-temp features. It fetches the live entity state and
   updates slider values when the state changes externally.


Compatibility Checker
---------------------

The compatibility module (`app/compat.py`) scans dashboards for known
limitations and displays a yellow banner at the top of the rendered view:

- **Custom card types not in the mapping table** — rendered as `placeholder`
- **HA Jinja2 template syntax** in markdown cards — unsupported
- **`card_mod` styling** — not supported
- **Mapped custom cards** — the mapping may not capture every nuance of the
  original Mushroom/Layout card configuration

Add `compat_warnings=scan_view(view)` when calling `render_view()` to enable.


Auto-Mapped HA Custom Cards
---------------------------

These card types are automatically translated at parse time. The renderer
never sees the original type.

| Source card                      | Target    | Notes                                          |
|----------------------------------|-----------|------------------------------------------------|
| `custom:mushroom-light-card`     | `tile`    | brightness/color-temp features, inline layout  |
| `custom:mushroom-cover-card`     | `entities`| single entity row with open/stop/close buttons |
| `custom:mushroom-number-card`    | `tile`    | numeric-input feature                          |
| `custom:layout-card` (view type) | sections  | grouped by `custom:layout-break` into sections |

**Unsupported card types** (not mapped, rendered as `placeholder`):

- `custom:mushroom-template-card` — use `button` with `tap_action.navigate` instead
- `shortcut` — use `button` instead
- Any other `custom:*` card type


Local Development
-----------------

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in HA_URL and HA_TOKEN
uvicorn app.main:app --reload  # → http://localhost:8000
```

Create dashboards by dropping YAML files into `config/`.
Each file becomes a dashboard at `/d/{filename_without_ext}`.

Run tests:

```bash
python3 -m pytest tests/test_pipeline.py -v
```


HA Add-On
---------

LightDash is available as a Home Assistant add-on via the GitHub repository.

### Prerequisites

- Home Assistant OS or Supervised installation
- `homeassistant_api: true` enabled (Supervisor proxy — automatic)

### Adding the Repository

1. Go to **Settings → Add-ons → Repositories**
2. Paste `https://github.com/richkershaw/HA-LightDash`
3. Click **Add**

### Installation

1. The **LightDash** add-on will now appear in the add-on store
2. Click **Install** (wait for the download to complete)
3. Go to the **Configuration** tab

### Dashboard Configuration

Each dashboard is defined as an entry in the `dashboards` list. Add one entry
per dashboard:

| Field   | Description                                                  |
|---------|--------------------------------------------------------------|
| `name`  | URL path segment (e.g. `living-room` → `/d/living-room`)    |
| `title` | Display title shown in the tab bar                           |
| `yaml`  | The full dashboard YAML pasted as text in the multiline textarea (see format above) |

Example with two dashboards:

```yaml
dashboards:
  - name: living-room
    title: Living Room
    yaml: |
      views:
        - title: Living Room
          path: main
          sections:
            - cards:
                - type: tile
                  entity: light.living_room
  - name: kitchen
    title: Kitchen
    yaml: |
      views:
        - title: Kitchen
          path: main
          sections:
            - cards:
                - type: tile
                  entity: light.kitchen
```

### Starting the Add-On

1. Go to the **Info** tab
2. Click **Start**
3. LightDash appears in the sidebar as **LightDash**

### Dashboard URLs

Each dashboard is available at:

    https://[your-ha-instance]/[ingress-path]/d/{name}

The exact URLs are logged in the add-on logs at startup and listed at the
`/health` endpoint.

### Updating

When a new version is released, the add-on shows an **Update** button on the
Info tab. Click it and then **Restart**.

### Releasing

Before pushing changes, bump the version in `lightdash/config.yaml`
so Supervisor detects a new build:

```yaml
version: "0.3.5"   # increment each push
```

Then commit and push to trigger a rebuild in Supervisor.
