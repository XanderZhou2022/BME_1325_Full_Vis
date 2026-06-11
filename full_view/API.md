# Full Hospital API

The full-view frontend treats the backend as the source of truth. The map only renders snapshots, sends event requests, and plays approved animation plans.

## Runtime

Run:

```bash
python dev-server.py 8000
```

Open:

```text
http://localhost:8000/
http://localhost:8000/console.html
```

The lightweight backend reads and writes:

- `backend-data/patients.json`
- `backend-data/staff.json`
- `backend-data/room-state.json`
- `backend-data/event-log.json`
- `map-config.json`
- `../rules/event-rules/*.json`

## Read APIs

`GET /api/hospital/snapshot`

Returns the full hospital state:

```json
{
  "floors": [],
  "rooms": [],
  "patients": [],
  "staff": [],
  "departments": {},
  "eventSeq": 0
}
```

`GET /api/hospital/rooms`

Returns all rooms with people and resource state.

`GET /api/hospital/people`

Returns all patients, doctors, and nurses.

`GET /api/hospital/events?after=12`

Returns event-log entries with `eventSeq > after`. The map page polls this endpoint and only animates accepted events with an `animationPlan`.

## Move Event API

`POST /api/hospital/events/move`

Request:

```json
{
  "requestId": "req-001",
  "source": "console",
  "operatorId": "manual-admin",
  "eventId": "TRANSFER_ED_TO_ICU",
  "patientId": "P-ER-001",
  "fromRoomId": "ed_red_resus",
  "toRoomId": "icu_admission",
  "context": {
    "reason": "needs ICU monitoring"
  }
}
```

Accepted response:

```json
{
  "accepted": true,
  "eventSeq": 12,
  "eventId": "TRANSFER_ED_TO_ICU",
  "patientId": "P-ER-001",
  "statusUpdates": {
    "patientStatus": "TRANSFERRING",
    "fromRoomReleased": true,
    "targetReserved": true
  },
  "animationPlan": {
    "kind": "patient-move",
    "transport": "stretcher",
    "escortRoles": ["porter", "ed_nurse"],
    "equipment": ["portable_monitor", "oxygen", "transport_bag"],
    "fromRoomId": "ed_red_resus",
    "toRoomId": "icu_admission",
    "viaRoomIds": ["ed_handoff", "elevator_1", "elevator_3"],
    "finalForm": "bed",
    "patientFormDuringMove": "stretcher"
  }
}
```

Rejected response:

```json
{
  "accepted": false,
  "eventSeq": 13,
  "eventId": "TRANSFER_ED_TO_ICU",
  "patientId": "P-ER-001",
  "reasonCode": "TARGET_ROOM_NOT_FOUND",
  "message": "Unknown target room: not_a_room."
}
```

## Movement Rule Standard

Every reusable movement rule should include:

- `eventId`: stable event name used by departments and console.
- `rooms`: related room ids.
- `movement.from`: source room id or symbolic source such as `current_ed_room`.
- `movement.to`: target room id, room-id list, or symbolic target.
- `movement.via`: ordered intermediate room ids, especially elevators.
- `movement.transport`: `walking`, `wheelchair`, or `stretcher`.
- `movement.patientFormDuringMove`: visual form during transport.
- `movement.finalForm`: `walking`, `waiting`, `consultation`, `stretcher`, `bed`, or `hidden`.
- `movement.escortRequired`, `movement.escortRoles`, and `movement.equipment`.
- `movement.pathPolicy`, `movement.resourcePolicy`, and `movement.failurePolicy`.

The backend checks the event rule first, then updates state and event log. The frontend should not decide whether a move is legal.

## Adding a New Department or Move

1. Add rooms to `map-config.json`.
2. Add seed people or room resources under `backend-data/` if needed.
3. Add a movement rule in `../rules/event-rules/*.json`.
4. Ensure `movement.via` includes cross-floor elevator rooms.
5. Start `dev-server.py`, open `console.html`, and submit a move request.
6. Confirm the map page animates the approved event and then matches `/api/hospital/snapshot`.
