# Fullview Canonical Backend

Fullview now has a runnable FastAPI Core backed by SQLite.

Run it from the workspace root:

```bash
python3 hospital/full_view/dev-server.py 8123
```

If 8123 is already occupied, use another port:

```bash
python3 hospital/full_view/dev-server.py 8124
```

The old `dev-server.py` command is kept as a compatibility launcher, but the main service is `backend/app/main.py`.

## Source Of Truth

- SQLite database: `hospital/full_view/backend-data/fullview.sqlite`
- Schema: `hospital/full_view/backend/db/schema.sql`
- Seed command: `python3 hospital/full_view/backend/db/seed_from_json.py`
- Seed inputs: standardized `map-config.json`, `event-rules/*.json`, and `backend-data/*.json`

Business IDs are standardized:

- Patients: `P-{8 lowercase hex}`
- Encounters: `E-{YYYYMMDDHHmmss}-{4 lowercase hex}`
- Rooms: `R-*`
- Beds: `B-*`

`backend-data/canonical-id-map.json` records the old-to-new ID rewrite.

## APIs

Department handler APIs:

- `GET /api/v1/departments`
- `GET /api/v1/departments/{department_id}/capabilities`
- `GET /api/v1/departments/{department_id}/schemas`
- `GET /api/v1/departments/{department_id}/examples`
- `GET /api/v1/departments/{department_id}/requests/recent`
- `POST /api/v1/departments/{department_id}/requests/{request_type}`
- `POST /api/v1/departments/{department_id}/playground/{request_type}`

Department sync APIs:

- `GET /api/v1/departments/{department_id}/inbox?after_seq=&limit=`
- `POST /api/v1/departments/{department_id}/inbox/{delivery_id}/ack`
- `GET /api/v1/departments/{department_id}/sync-cursor`
- `GET /api/v1/events?after_seq=&department_id=`

Map/console compatibility APIs:

- `GET /api/hospital/snapshot`
- `GET /api/hospital/events?after=`
- `POST /api/hospital/events/move`

## Transaction Contract

Every department write request goes through one SQLite transaction:

1. Check idempotency.
2. Insert `department_requests`.
3. Normalize the department payload.
4. Validate rules/resources.
5. Update patients/encounters/episodes/beds.
6. Insert `hospital_events`.
7. Fan out to `department_inbox`.
8. Insert `event_outbox`.
9. Store the handler response.

Redis remains a future realtime publisher fed by `event_outbox`; the SQLite inbox/cursor tables are the durable replay path.
