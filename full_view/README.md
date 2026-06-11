# Full Hospital View

Static Canvas 2D whole-hospital visualization for the simulated hospital course project.

Run from this directory:

```bash
python dev-server.py
```

Open:

```text
http://localhost:8000/
http://localhost:8000/console.html
```

`dev-server.py` serves the static pages, enables the map/rule editors to save JSON, and provides the lightweight hospital backend APIs used by the map and console.

The page can still run with `python -m http.server 8000`, but the browser cannot write local files in that mode. If the save API is unavailable, the editor stores the updated map in browser storage and applies it immediately for the current browser.

## Map Configuration

The floor layout is driven by `map-config.json`.

- `floors[]` defines each hospital floor, title, subtitle, department kinds, and rooms.
- `rooms[]` defines each room with `id`, `kind`, `label`, `x`, `y`, `w`, `h`, and `accent`.
- `rooms[].protected` prevents critical rooms from being deleted or edited in the map admin. Elevator rooms are protected automatically.
- `rooms[].maxBeds` overrides the room's bed limit in the map admin. Ward and ICU rooms default to 4 beds; emergency/rescue rooms default to 2 beds.
- Room coordinates use tile units, not pixels. One tile is currently 32px.
- `doors[]` is stored inside each room and uses room-relative offsets.
- `items[]` is also stored inside each room. Beds, desks, screens, sofas, cabinets, tables, and reception counters use room-relative tile offsets, so they move automatically when the room moves.

After editing `map-config.json`, click `Refresh` in the right panel. The page refetches the JSON, rebuilds rooms, doors, props, walls, collisions, mini map, room info, and relative person placement without editing JS.

Use `Edit Map` to open the room editor. It lists rooms by floor, supports deleting rooms, changing bed counts within each room's max limit, and adding a new room with an automatically generated unique room id.

## Event Rules

Structured patient-movement event rules live in `../rules/event-rules/`.

- `index.json` lists the rule categories.
- `emergency.json`, `outpatient.json`, `icu.json`, `ward.json`, `transfer.json`, and `resource-blocking.json` store the editable rule lists.
- Each rule keeps `eventId`, `classification`, `trigger`, `rooms`, `prechecks`, `actions`, `successState`, `blocking`, and `visualization`.
- Current rules intentionally focus on patient movement: room-to-room movement, cross-floor transfers, discharge/exit, exam/pharmacy routing, and movement blockers.

Use `Rules` in the right panel to open the event rule editor. It can browse rules by category, edit rule fields, add a new placeholder rule, delete a rule, and save the category JSON through `dev-server.py`.

## Hospital Backend APIs

The current demo backend is intentionally lightweight and file-based. It stores runtime state under `backend-data/`:

- `patients.json`: patient identity, status, room, form, and visual placement.
- `staff.json`: doctor and nurse identity, room, role, gender, and pose.
- `room-state.json`: bed occupancy, queues, room reservations, and escort resources.
- `event-log.json`: accepted/rejected events with monotonically increasing `eventSeq`.

The map page loads `/api/hospital/snapshot`, polls `/api/hospital/events`, and only plays backend-approved animation plans. The standalone `console.html` reads the same APIs and sends global move requests through `POST /api/hospital/events/move`.

See `API.md` for request/response shapes and the reusable movement-rule standard.
