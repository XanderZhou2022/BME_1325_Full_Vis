# Fullview Backend Migration Scaffold

This directory documents the intended FastAPI/PostgreSQL shape for the department-handler work.

The current runnable implementation still lives in `../dev-server.py` so the existing Canvas map and Console keep working. It already exposes:

- `GET /api/v1/departments`
- `GET /api/v1/departments/{department_id}/capabilities`
- `GET /api/v1/departments/{department_id}/schemas`
- `GET /api/v1/departments/{department_id}/examples`
- `GET /api/v1/departments/{department_id}/requests/recent`
- `POST /api/v1/departments/{department_id}/requests/{request_type}`
- `POST /api/v1/departments/{department_id}/playground/{request_type}`

The next migration step is to move those handlers into FastAPI routers and replace the JSON files under `../backend-data/` with the PostgreSQL tables sketched in `db/schema.sql`.

Movement, transfer, and discharge handler requests must stay aligned with the Rules Admin event library. Handler capabilities expose `allowedRules` from `../event-rules/*.json`, examples are generated from those rules, and incoming `event_id` values are rejected when they are not valid for that department/request type.
