A lightweight, self-contained dashboard renderer for Home Assistant. Instead of running HA's full Lovelace frontend, which is a struggle for low-power devices such as NSPanels and older Android tablets, LightDash is a focused alternative: support for tiles and built-in entities, intelligent mapping of some common custom cards to lightweight alternatives, and plain HTML + CSS with much of the interactivity shifted to the addon itself.

I orignally built LightDash to run on the NSPanel Pro in-wall touchscreens I have around my house, which are getting increasingly slow as the HA team add more dashboard capabilities. Wonderful for iPads, desktop browsing and recent smartphones, but almost unusable on the devices that sit in the gap between ESPHome and modern browsers.

LightDash is designed to handle copy-and-pasted YAML from existing dashboards with _minimal_ (not quite zero) adjustment - there's an edit-and-preview web UI accessible from the addon control panel, where you can tweak the YAML and see the results immediately before saving.

**Caveat 1:** I've focused on the cards I use in my own small-screen dashboards. I'd love for contributors to add support for their own layouts!

**Caveat 2:** Yep, I used OpenCode to build a lot of this. I'm a 25+ year software architect and developer, but this is a one-day project. I'm pretty happy it's not filled with slop - I've reviewed it and it's passable - but I make no warranties about code quality this early in its life.

Accessing Dashboards
--------------------

LightDash serves dashboards via two methods. Both work simultaneously.

### Via the HA Sidebar (Ingress)

After starting the add-on, click the **Open Web UI** button or the LightDash sidebar entry. This opens
the dashboard index page within the HA interface. This is fine for devices you're happy to login on regularly.

### Via Direct Port (HTTP, No Auth)

The add-on also exposes a raw HTTP port (`8001` by default). Any device on
your LAN can reach it without Home Assistant authentication:

    http://[your HA server]]:8001/

This is useful for:
- **Wall-mounted tablets** that shouldn't show a login screen
- **Guest devices** that shouldn't have HA credentials
- **kiosk-mode browsers** or screens that auto-launch a URL

The hostname defaults to your HA instance's hostname (auto-detected from the
Supervisor API). You can override it in the add-on Configuration tab:

| Option          | Default                 | Description                                    |
|-----------------|-------------------------|------------------------------------------------|
| `public_host`   | auto-detected           | Hostname for direct-port URLs                  |
| `public_port`   | `8001`                  | Port mapped to `8000/tcp` inside the container |

**Security note:** The direct port has no authentication. Anyone on the
network can view dashboards. Use firewall rules or a reverse proxy if you
need to restrict access. Disable the port mapping in the add-on Info tab
(change `8000/tcp: 8001` to `8000/tcp: null`) if you only want ingress access.

### Dashboard URLs

Each dashboard is available at:

    {base}/d/{name}

Where `{base}` depends on the access method:

- **Ingress:** `https://[your HA server]/api/hassio_ingress/{token}/d/{dashboard name}`
- **Direct port:** `http://[your HA server]:8001/d/{dashboard name}`

The exact URLs are logged in the add-on logs at startup and listed at the
`/dashboards` endpoint. Use the **Public URL** button in the config editor
to copy the external URL for the current dashboard.


In-App Editor
-------------

Dashboards are managed entirely through the in-app editor.

1. Open the LightDash sidebar entry (or navigate to the dashboard index)
2. Click **⚙ Config** at the bottom of the page
3. Click **+ Add Dashboard** and enter a URL-safe name (e.g. `living-room`)
4. Edit the YAML in the left pane
5. Click **Save** — the preview pane updates automatically
6. Click **Preview** to refresh the preview without saving
7. Click **Public URL** to copy the externally-available URL to add to your kiosk devices' config

The config page shows a split view:

```
┌──────────────────────────────────────────────────────────┐
│  Dashboard list         CodeMirror YAML    Preview       │
│                         editor             (iframe)      │
│  living-room ──active── ┌─────────────────┐              │
│  kitchen                │ views:          │   [rendered  │
│                         │   - title: Home │    view]     │
│  [+ Add Dashboard]      │     path: home  │              │
│  [Delete]               │     sections:...│              │
│                         └─────────────────┘              │
│                         [Preview] [Save]                 │
└──────────────────────────────────────────────────────────┘
```

- **Add Dashboard**: Creates a new YAML file with a starter template
- **Delete**: Removes the dashboard file entirely
- **Rename**: Renames the dashboard (and its YAML file on disk)
- **Save**: Writes YAML to disk and reloads the dashboard
- **Preview**: Renders the current editor content in the right pane
- **Public URL**: Copies the external dashboard URL to the clipboard

Dashboards are stored as individual YAML files in the add-on data directory
(`/data/dashboards/`), which is included in HA snapshots.


YAML Dashboard Format
---------------------

A dashboard is a YAML file with a top-level `views` key:

```yaml
title: Living Room
lightdash:
  container_width: 480px
  container_height: 480px
views:
  - title: Home
    path: home
    icon: mdi:home
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

**Top-level fields:**

| Field       | Description                                        |
|-------------|----------------------------------------------------|
| `title`     | Display title                                      |
| `lightdash` | Container sizing (see below)                       |
| `views`     | List of views                                      |

### lightdash config

You can optionally fix the container size - useful for small-screen devices, and previewing rendering.

```yaml
lightdash:
  container_width: 480px    # fixed container width (e.g. 480px, 100%)
  container_height: 480px   # fixed container height
```

### View fields

| Field         | Description                                        |
|---------------|----------------------------------------------------|
| `title`       | Display title (also used in `<title>`)             |
| `path`        | URL path segment (defaults to slug of title)       |
| `icon`        | MDI icon (shown in view index)                     |
| `bg_color`    | CSS background-color                               |
| `bg_image`    | Background image URL (`/api/image/serve/...`)      |
| `type`        | View layout type (`sections` or `custom:layout-card`) |
| `max_columns` | Column count for max-width grid                    |

When `type: custom:layout-card` is used, the parser groups cards into grid
sections split by `custom:layout-break` card entries. The `layout.max_cols`
value determines section column count.

### Section fields

| Field     | Description                          |
|-----------|--------------------------------------|
| `type`    | Section type (`grid`)                |
| `columns` | Number of grid columns               |

### Grid options on cards

```yaml
grid_options:
  columns: 6      # span this many columns
  rows: auto      # span this many rows
```


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
toggle switch. Non-binary entities show state text. Cover entities show
open/stop/close buttons instead of a toggle.

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

A compact action button. Icon and name are on one line. Supports `tap_action`.

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


Compatibility Checker
---------------------

The compatibility module (`app/compat.py`) scans dashboards at startup for
known limitations and logs warnings:

- **Custom card types not in the mapping table** — rendered as `placeholder`
- **HA Jinja2 template syntax** in markdown cards — unsupported
- **`card_mod` styling** — not supported
- **Mapped custom cards** — the mapping may not capture every nuance of the
  original Mushroom/Layout card configuration


Updating
--------

When a new version is released, the add-on shows an **Update** button on the
Info tab. Click it and then **Restart**. Dashboards persist across updates
in `/data/dashboards/`.