from __future__ import annotations

from pathlib import Path
import hashlib
import json
import sqlite3
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import core
from .db import DATA_DIR, FULL_VIEW_ROOT, db
from .seed import dump_json, utc_now


app = FastAPI(title="Fullview Canonical Core", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    core.init_database()


@app.get("/api/health")
def health():
    return {"ok": True, "service": "fullview-core", "database": str(db.path)}


@app.get("/api/v1/departments")
def departments():
    return {"departments": core.list_departments()}


@app.get("/api/v1/departments/{department_id}/capabilities")
def capabilities(department_id: str):
    if not core.ensure_department(department_id):
        return core.api_error("DEPARTMENT_NOT_FOUND", f"Unknown department: {department_id}")
    return core.api_ok(core.department_capabilities(department_id))


@app.get("/api/v1/departments/{department_id}/schemas")
def schemas(department_id: str):
    meta = core.ensure_department(department_id)
    if not meta:
        return core.api_error("DEPARTMENT_NOT_FOUND", f"Unknown department: {department_id}")
    return core.api_ok({request_type: core.request_schema(request_type) for request_type in meta["enabled_request_types"]})


@app.get("/api/v1/departments/{department_id}/examples")
def examples(department_id: str):
    if not core.ensure_department(department_id):
        return core.api_error("DEPARTMENT_NOT_FOUND", f"Unknown department: {department_id}")
    return core.api_ok(core.department_examples(department_id))


@app.get("/api/v1/departments/{department_id}/requests/recent")
def recent_requests(department_id: str):
    with db.connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM department_requests
            WHERE department_id=?
            ORDER BY created_at DESC
            LIMIT 20
            """,
            (department_id,),
        ).fetchall()
    return core.api_ok({"requests": [department_request_view(row) for row in rows]})


@app.post("/api/v1/departments/{department_id}/requests/{request_type}")
@app.post("/api/v1/departments/{department_id}/playground/{request_type}")
async def department_request(department_id: str, request_type: str, request: Request, idempotency_key: str | None = Header(None, alias="Idempotency-Key")):
    payload = await request.json()
    return core.handle_department_request(department_id, request_type, payload, idempotency_key or "")


@app.get("/api/v1/departments/{department_id}/inbox")
def department_inbox(department_id: str, after_seq: int = Query(0), limit: int = Query(50)):
    with db.transaction() as conn:
        rows = conn.execute(
            """
            SELECT * FROM department_inbox
            WHERE department_id=? AND event_seq > ?
            ORDER BY event_seq ASC
            LIMIT ?
            """,
            (department_id, after_seq, min(max(limit, 1), 200)),
        ).fetchall()
        last_seq = rows[-1]["event_seq"] if rows else after_seq
        conn.execute(
            """
            INSERT INTO department_sync_cursor (department_id, last_delivered_seq, last_acked_seq, updated_at)
            VALUES (?, ?, 0, ?)
            ON CONFLICT(department_id) DO UPDATE SET last_delivered_seq=max(last_delivered_seq, excluded.last_delivered_seq), updated_at=excluded.updated_at
            """,
            (department_id, last_seq, utc_now()),
        )
    return core.api_ok({"events": [inbox_view(row) for row in rows], "cursor": {"last_delivered_seq": last_seq}})


@app.post("/api/v1/departments/{department_id}/inbox/{delivery_id}/ack")
def ack_inbox(department_id: str, delivery_id: str):
    with db.transaction() as conn:
        row = conn.execute("SELECT * FROM department_inbox WHERE department_id=? AND delivery_id=?", (department_id, delivery_id)).fetchone()
        if not row:
            return core.api_error("DELIVERY_NOT_FOUND", f"No delivery {delivery_id} for {department_id}.")
        conn.execute("UPDATE department_inbox SET status='acked', acked_at=? WHERE delivery_id=?", (utc_now(), delivery_id))
        conn.execute(
            """
            INSERT INTO department_sync_cursor (department_id, last_delivered_seq, last_acked_seq, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(department_id) DO UPDATE SET
              last_acked_seq=max(last_acked_seq, excluded.last_acked_seq),
              last_delivered_seq=max(last_delivered_seq, excluded.last_delivered_seq),
              updated_at=excluded.updated_at
            """,
            (department_id, row["event_seq"], row["event_seq"], utc_now()),
        )
    return core.api_ok({"delivery_id": delivery_id, "status": "acked", "event_seq": row["event_seq"]})


@app.get("/api/v1/departments/{department_id}/sync-cursor")
def sync_cursor(department_id: str):
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM department_sync_cursor WHERE department_id=?", (department_id,)).fetchone()
    return core.api_ok({"cursor": dict(row) if row else {"department_id": department_id, "last_delivered_seq": 0, "last_acked_seq": 0}})


@app.get("/api/v1/events")
def api_events(after_seq: int = Query(0), department_id: str | None = Query(None)):
    with db.connect() as conn:
        if department_id:
            rows = conn.execute(
                """
                SELECT h.* FROM hospital_events h
                JOIN department_inbox i ON i.event_seq=h.event_seq
                WHERE i.department_id=? AND h.event_seq > ?
                ORDER BY h.event_seq ASC
                LIMIT 200
                """,
                (department_id, after_seq),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM hospital_events WHERE event_seq > ? ORDER BY event_seq ASC LIMIT 200", (after_seq,)).fetchall()
    return core.api_ok({"events": [event_view(row) for row in rows]})


@app.get("/api/hospital/snapshot")
def hospital_snapshot():
    return build_snapshot()


@app.get("/api/hospital/rooms")
def hospital_rooms():
    return {"rooms": build_snapshot()["rooms"]}


@app.get("/api/hospital/people")
def hospital_people():
    snapshot = build_snapshot()
    return {"patients": snapshot["patients"], "staff": snapshot["staff"]}


@app.get("/api/hospital/events")
def hospital_events(after: int = Query(0)):
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM hospital_events WHERE event_seq > ? ORDER BY event_seq ASC LIMIT 200", (after,)).fetchall()
    return {"events": [event_view(row) for row in rows]}


@app.post("/api/hospital/events/move")
async def hospital_move(request: Request):
    payload = await request.json()
    patient_id = payload.get("patientId") or payload.get("patient_id")
    with db.connect() as conn:
        patient = conn.execute("SELECT * FROM patients WHERE patient_id=?", (patient_id,)).fetchone()
    department_id = patient["current_department_id"] if patient else "outpatient"
    event_id = payload.get("eventId") or payload.get("event_id")
    request_type = console_request_type_for_event(event_id)
    target_department_id = core.target_department_for_transfer_event(event_id) if request_type == "transfer_request" else None
    normalized = {
        "patient_id": patient_id,
        "encounter_id": payload.get("encounterId") or payload.get("encounter_id") or active_encounter_id(patient_id),
        "event_id": event_id,
        "from_room_id": payload.get("fromRoomId") or payload.get("from_room_id"),
        "to_room_id": payload.get("toRoomId") or payload.get("to_room_id"),
        "to_department_id": target_department_id,
        "reason": payload.get("reason") or "console movement",
        "summary": {"source": "console"},
    }
    response = core.handle_department_request(department_id, request_type, normalized, "")
    core_response = (response.get("data") or {}).get("coreResponse") if isinstance(response, dict) else None
    if core_response:
        return core_response
    error = (response.get("error") or {}) if isinstance(response, dict) else {}
    return {
        "accepted": False,
        "eventId": event_id,
        "event_id": event_id,
        "patientId": patient_id,
        "patient_id": patient_id,
        "reasonCode": error.get("code") or "REQUEST_REJECTED",
        "message": error.get("message") or "Move request was rejected by Fullview Core.",
    }


def console_request_type_for_event(event_id: str | None) -> str:
    rule = core.find_rule(event_id) if event_id else None
    if not rule:
        return "movement_request"
    kind = core.rule_kind(rule)
    if kind == "transfer":
        return "transfer_request"
    if kind == "discharge":
        return "discharge_request"
    if kind == "clinical_event":
        return "clinical_event"
    return "movement_request"


@app.post("/api/hospital/patients/admit")
async def hospital_admit(request: Request):
    payload = await request.json()
    department_id = payload.get("department_id") or payload.get("departmentId") or "outpatient"
    return core.handle_department_request(department_id, "patient_upsert", payload, "")


@app.delete("/api/hospital/patients/{patient_id}")
def delete_patient(patient_id: str):
    with db.transaction() as conn:
        row = conn.execute("SELECT * FROM patients WHERE patient_id=?", (patient_id,)).fetchone()
        if not row:
            return {"accepted": False, "eventId": "PATIENT_DELETE", "reasonCode": "PATIENT_NOT_FOUND", "message": f"No patient found for {patient_id}."}
        now = utc_now()
        conn.execute("UPDATE beds SET status='available', patient_id=NULL, updated_at=? WHERE patient_id=?", (utc_now(), patient_id))
        conn.execute("UPDATE bed_assignments SET status='released', released_at=? WHERE patient_id=? AND released_at IS NULL", (utc_now(), patient_id))
        conn.execute("UPDATE encounters SET status='CLOSED', closed_at=COALESCE(closed_at, ?), updated_at=? WHERE patient_id=? AND status!='CLOSED'", (now, now, patient_id))
        conn.execute("UPDATE episodes SET status='CLOSED', ended_at=COALESCE(ended_at, ?) WHERE patient_id=? AND status!='CLOSED'", (now, patient_id))
        conn.execute("UPDATE patients SET status='DELETED', current_room_id=NULL, current_bed_id=NULL, updated_at=? WHERE patient_id=?", (now, patient_id))
        event_seq = core.write_event(conn, "patient.deleted", {"patient_id": patient_id, "correlation_id": core.new_event_id(), "producer": "fullview.console"}, "dashboard", None, True)
    return {"accepted": True, "eventSeq": event_seq, "eventId": "PATIENT_DELETE", "patientId": patient_id, "snapshotRefresh": True}


@app.get("/api/event-rules")
def event_rule_index():
    return read_json(FULL_VIEW_ROOT / "event-rules" / "index.json", {})


@app.get("/api/event-rules/{file_name}")
def event_rule_file(file_name: str):
    path = safe_rule_file(file_name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Rule file not found")
    return read_json(path, {})


@app.put("/api/event-rules/{file_name}")
async def save_event_rule_file(file_name: str, request: Request):
    path = safe_rule_file(file_name)
    payload = await request.json()
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    mirror = FULL_VIEW_ROOT.parent / "rules" / "event-rules" / file_name
    if mirror.parent.exists():
        mirror.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"ok": True}


@app.put("/api/map-config")
async def save_map_config(request: Request):
    payload = await request.json()
    (FULL_VIEW_ROOT / "map-config.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"ok": True}


@app.get("/api/v1/debug/scenarios/closed-loop")
def closed_loop_scenario():
    return core.api_ok(build_closed_loop_debug_scenario())


def build_snapshot():
    with db.connect() as conn:
        floors = snapshot_floors()
        room_rows = conn.execute("SELECT * FROM locations ORDER BY floor, room_id").fetchall()
        patient_rows = conn.execute("SELECT * FROM patients WHERE status NOT IN ('DISCHARGED', 'DELETED') ORDER BY patient_id").fetchall()
        bed_rows = conn.execute("SELECT * FROM beds ORDER BY room_id, bed_index").fetchall()
        encounter_rows = conn.execute(
            """
            SELECT patient_id, encounter_id
            FROM encounters
            WHERE status='OPEN'
            ORDER BY opened_at DESC
            """
        ).fetchall()
        last_seq = conn.execute("SELECT COALESCE(MAX(event_seq), 0) FROM hospital_events").fetchone()[0]
    bed_room_by_id = {bed["bed_id"]: bed["room_id"] for bed in bed_rows}
    encounter_by_patient = {}
    for row in encounter_rows:
        encounter_by_patient.setdefault(row["patient_id"], row["encounter_id"])
    patients = [patient_view(row, bed_room_by_id, encounter_by_patient) for row in patient_rows]
    patients_by_room: dict[str, list[dict[str, Any]]] = {}
    for patient in patients:
        if patient.get("roomId"):
            patients_by_room.setdefault(patient["roomId"], []).append(patient)
    beds_by_room: dict[str, list[dict[str, Any]]] = {}
    for bed in bed_rows:
        beds_by_room.setdefault(bed["room_id"], []).append(bed_view(bed))
    staff = normalize_staff_records(read_json(DATA_DIR / "staff.json", {"staff": []}).get("staff", []), room_rows)
    staff_by_room: dict[str, list[dict[str, Any]]] = {}
    for member in staff:
        room_id = member.get("roomId") or member.get("room_id")
        if room_id:
            staff_by_room.setdefault(room_id, []).append(member)
    rooms = [
        room_view(
            row,
            patients_by_room.get(row["room_id"], []),
            staff_by_room.get(row["room_id"], []),
            beds_by_room.get(row["room_id"], []),
            index,
        )
        for index, row in enumerate(room_rows, start=1)
    ]
    return {
        "floors": floors,
        "rooms": rooms,
        "patients": patients,
        "staff": staff,
        "departments": department_status(patients),
        "eventSeq": last_seq,
    }


def normalize_staff_records(records, room_rows):
    rooms_by_id = {row["room_id"]: row for row in room_rows}
    staff = [dict(member) for member in records]
    normalize_porter_home_locations(staff, rooms_by_id)
    assign_hallway_staff_positions(staff, rooms_by_id)
    return staff


def normalize_porter_home_locations(staff, rooms_by_id):
    for member in staff:
        if (member.get("role") or member.get("type")) != "porter":
            continue
        home_floor = porter_home_floor(member)
        if not home_floor:
            continue
        member["floor"] = home_floor
        member["floor_id"] = home_floor
        member["locationType"] = "hallway"
        member["location_type"] = "hallway"
        member["roomId"] = None
        member["room_id"] = None
        seed = member.get("staff_id") or member.get("employeeId") or member.get("employee_id") or member.get("id")
        if seed:
            member["hallway_seed"] = seed
        anchor_room_id = member.get("hallway_anchor_room_id")
        anchor_row = rooms_by_id.get(anchor_room_id) if anchor_room_id else None
        if anchor_row and int(anchor_row["floor"]) != home_floor:
            member.pop("hallway_anchor_room_id", None)
        location = dict(member.get("current_location") or {})
        location["kind"] = "hallway"
        location["location_type"] = "hallway"
        location["floor_id"] = home_floor
        if anchor_row and int(anchor_row["floor"]) != home_floor:
            location.pop("anchor_room_id", None)
        member["current_location"] = location


def porter_home_floor(member):
    for value in [member.get("staff_id"), member.get("employeeId"), member.get("employee_id"), member.get("id"), member.get("hallway_seed")]:
        text = str(value or "").upper()
        marker = "POT-"
        if marker not in text:
            continue
        after = text.split(marker, 1)[1]
        floor_text = after.split("F", 1)[0]
        if floor_text.isdigit():
            return int(floor_text)
    return None


def assign_hallway_staff_positions(staff, rooms_by_id):
    groups: dict[int, list[dict[str, Any]]] = {}
    for member in staff:
        if not is_hallway_staff(member):
            continue
        floor = int(member.get("floor_id") or member.get("floor") or (member.get("current_location") or {}).get("floor_id") or 0)
        if floor:
            groups.setdefault(floor, []).append(member)

    for floor, members in groups.items():
        candidates = hallway_candidates_for_floor(floor, rooms_by_id)
        if not candidates:
            continue
        chosen = []
        ordered = sorted(members, key=lambda member: stable_hash(member.get("id") or member.get("staff_id") or member.get("employeeId") or "staff"))
        for index, member in enumerate(ordered):
            anchor_room_id = member.get("hallway_anchor_room_id") or (member.get("current_location") or {}).get("anchor_room_id")
            anchor = hallway_point_for_room(rooms_by_id[anchor_room_id]) if anchor_room_id in rooms_by_id else None
            point = choose_hallway_point(member, candidates, chosen, index, anchor)
            chosen.append(point)
            set_staff_hallway_point(member, point)


def is_hallway_staff(member):
    location = member.get("current_location") or {}
    return (member.get("location_type") or member.get("locationType") or location.get("location_type") or location.get("kind")) == "hallway"


def choose_hallway_point(member, candidates, chosen, index, anchor=None):
    seed = member.get("hallway_seed") or member.get("staff_id") or member.get("employeeId") or member.get("id") or f"staff-{index}"
    if anchor:
        ordered = sorted(candidates, key=lambda point: squared_distance(point, anchor) + stable_hash(f"{seed}:{point['tileX']}:{point['tileY']}") / 10**18)
    else:
        ordered = sorted(candidates, key=lambda point: stable_hash(f"{seed}:{point['tileX']}:{point['tileY']}"))
    for min_distance in [4.4, 3.5, 2.7, 1.9, 0]:
        for point in ordered:
            if all(tile_distance(point, used) >= min_distance for used in chosen):
                return point
    return ordered[index % len(ordered)]


def set_staff_hallway_point(member, point):
    member["location_type"] = "hallway"
    member["locationType"] = "hallway"
    member["room_id"] = None
    member["roomId"] = None
    member["floor"] = point["floor"]
    member["floor_id"] = point["floor"]
    member["tile_x"] = point["tileX"]
    member["tile_y"] = point["tileY"]
    member["x"] = point["x"]
    member["y"] = point["y"]
    location = dict(member.get("current_location") or {})
    location.update({
        "kind": "hallway",
        "location_type": "hallway",
        "floor_id": point["floor"],
        "tile_x": point["tileX"],
        "tile_y": point["tileY"],
        "x": point["x"],
        "y": point["y"],
    })
    member["current_location"] = location


def hallway_candidates_for_floor(floor, rooms_by_id):
    rooms = [row for row in rooms_by_id.values() if row["floor"] == floor]
    raw = []
    for row in rooms:
        spec = core.json_loads(row["map_json"])
        x, y, w, h = (float(spec.get(key) or 0) for key in ("x", "y", "w", "h"))
        if w <= 0 or h <= 0:
            continue
        for offset in frange(x + 1.4, x + w - 1.4, 2.6):
            raw.append({"floor": floor, "tileX": offset, "tileY": y - 1.55})
            raw.append({"floor": floor, "tileX": offset, "tileY": y + h + 1.55})
        for offset in frange(y + 1.4, y + h - 1.4, 2.6):
            raw.append({"floor": floor, "tileX": x - 1.55, "tileY": offset})
            raw.append({"floor": floor, "tileX": x + w + 1.55, "tileY": offset})

    deduped = {}
    for point in raw:
        if point_inside_any_room(point, rooms, padding=0.9):
            continue
        key = (round(point["tileX"], 1), round(point["tileY"], 1))
        deduped[key] = world_point(floor, key[0], key[1])
    return list(deduped.values())


def hallway_point_for_room(row):
    spec = core.json_loads(row["map_json"])
    x, y, w, h = (float(spec.get(key) or 0) for key in ("x", "y", "w", "h"))
    tile_x = max(3.5, min(64.5, x + w / 2))
    tile_y = y - 1.4 if y >= 26 else y + h + 1.4
    tile_y = max(3.5, min(36.5, tile_y))
    return world_point(row["floor"], round(tile_x, 2), round(tile_y, 2))


def point_inside_any_room(point, rooms, padding=0.0):
    for row in rooms:
        spec = core.json_loads(row["map_json"])
        x, y, w, h = (float(spec.get(key) or 0) for key in ("x", "y", "w", "h"))
        if x - padding <= point["tileX"] <= x + w + padding and y - padding <= point["tileY"] <= y + h + padding:
            return True
    return False


def world_point(floor, tile_x, tile_y):
    return {"floor": floor, "floorId": floor, "tileX": tile_x, "tileY": tile_y, "x": tile_x * 32, "y": tile_y * 32}


def frange(start, stop, step):
    value = start
    while value <= stop:
        yield value
        value += step


def stable_hash(value):
    return int(hashlib.sha1(str(value).encode("utf-8")).hexdigest()[:12], 16)


def squared_distance(a, b):
    return (a["tileX"] - b["tileX"]) ** 2 + (a["tileY"] - b["tileY"]) ** 2


def tile_distance(a, b):
    return ((a["tileX"] - b["tileX"]) ** 2 + (a["tileY"] - b["tileY"]) ** 2) ** 0.5


def snapshot_floors():
    config = read_json(FULL_VIEW_ROOT / "map-config.json", {"floors": []})
    floors = []
    for floor in config.get("floors", []):
        floors.append(
            {
                "id": floor.get("id"),
                "label": floor.get("label") or f"{floor.get('id')}F",
                "shortLabel": floor.get("shortLabel") or f"{floor.get('id')}F",
                "subtitle": floor.get("subtitle") or "",
                "departmentKinds": floor.get("departmentKinds") or [],
                "rooms": [room.get("id") for room in floor.get("rooms", [])],
            }
        )
    return floors


def room_view(row, patients, staff, beds, index):
    occupied = sum(1 for bed in beds if bed["occupied"])
    map_spec = core.json_loads(row["map_json"])
    return {
        "id": row["room_id"],
        "roomId": row["room_id"],
        "visualRoomId": row["visual_room_id"],
        "floor": row["floor"],
        "kind": row["kind"],
        "departmentId": row["department_id"],
        "label": row["display_name"],
        "roomCode": map_spec.get("roomCode") or f"{row['floor']}F-Room{index}",
        "room_code": map_spec.get("roomCode") or f"{row['floor']}F-Room{index}",
        "protected": bool(map_spec.get("protected")),
        "capacityBeds": row["capacity_beds"],
        "occupiedBeds": occupied,
        "availableBeds": max(0, row["capacity_beds"] - occupied),
        "patientCount": len(patients),
        "patient_count": len(patients),
        "staffCount": len(staff),
        "staff_count": len(staff),
        "queue": [],
        "queueLength": 0,
        "queue_length": 0,
        "patients": patients,
        "staff": staff,
        "beds": beds,
        "bedAssignments": beds,
        "bedIds": [bed["bedId"] for bed in beds],
    }


def bed_view(row):
    return {
        "bedId": row["bed_id"],
        "bed_id": row["bed_id"],
        "roomId": row["room_id"],
        "room_id": row["room_id"],
        "occupied": row["status"] == "occupied",
        "patientId": row["patient_id"],
        "patient_id": row["patient_id"],
        "status": row["status"],
    }


def patient_view(row, bed_room_by_id=None, encounter_by_patient=None):
    profile = core.json_loads(row["profile_json"])
    room_id = row["current_room_id"]
    bed_room_id = (bed_room_by_id or {}).get(row["current_bed_id"])
    encounter_id = (encounter_by_patient or {}).get(row["patient_id"])
    return {
        "id": row["patient_id"],
        "patientId": row["patient_id"],
        "patient_id": row["patient_id"],
        "encounterId": encounter_id,
        "encounter_id": encounter_id,
        "type": "patient",
        "name": row["name"],
        "department": core.DEPARTMENT_LABELS.get(row["current_department_id"], row["current_department_id"] or "Hospital"),
        "department_id": row["current_department_id"],
        "symptoms": (profile.get("summary") or {}).get("chief_complaint") or profile.get("symptoms") or "",
        "status": row["status"],
        "roomId": room_id,
        "room_id": room_id,
        "bedRoomId": bed_room_id,
        "bed_room_id": bed_room_id,
        "bedId": row["current_bed_id"],
        "bed_id": row["current_bed_id"],
        "form": "bed" if row["current_bed_id"] else "walking",
        "baseForm": "walking",
        "relX": 0.4,
        "relY": 0.5,
        "color": "#5f8ec9",
        "skin": "#f2c799",
        "blanket": "#76c59d" if row["current_department_id"] == "ward" else "#d46d8e",
        "gender": row["gender"],
        "clinical": profile,
        "current_location": {"room_id": room_id},
    }


def department_status(patients):
    result = {department_id: {"label": label, "patients": 0, "transferring": 0} for department_id, label in core.DEPARTMENT_LABELS.items()}
    for patient in patients:
        department_id = patient.get("department_id")
        if department_id not in result:
            continue
        result[department_id]["patients"] += 1
        if patient.get("status") == "TRANSFERRING":
            result[department_id]["transferring"] += 1
    return result


def event_view(row):
    animation = core.json_loads(row["animation_plan_json"])
    payload = core.json_loads(row["payload_json"])
    staff_plan = payload.get("staffMovePlan") or core.to_camel_staff_plan(payload.get("staff_move_plan") or {})
    view = {
        "eventSeq": row["event_seq"],
        "event_seq": row["event_seq"],
        "eventId": row["event_id"],
        "event_id": row["event_id"],
        "eventType": row["event_type"],
        "event_type": row["event_type"],
        "patientId": row["patient_id"],
        "patient_id": row["patient_id"],
        "encounterId": row["encounter_id"],
        "encounter_id": row["encounter_id"],
        "accepted": bool(row["accepted"]),
        "reasonCode": row["reason_code"],
        "animationPlan": core.to_camel_animation(animation),
        "animation_plan": animation,
        "payload": payload,
        "occurredAt": row["occurred_at"],
        "occurred_at": row["occurred_at"],
    }
    if staff_plan:
        view["staffMovePlan"] = staff_plan
        view["staff_move_plan"] = core.to_snake_staff_plan(staff_plan)
    return view


def department_request_view(row):
    return {
        "requestId": row["request_id"],
        "request_id": row["request_id"],
        "departmentId": row["department_id"],
        "department_id": row["department_id"],
        "requestType": row["request_type"],
        "request_type": row["request_type"],
        "status": row["status"],
        "errorCode": row["error_code"],
        "error_code": row["error_code"],
        "correlationId": row["correlation_id"],
        "correlation_id": row["correlation_id"],
        "createdAt": row["created_at"],
        "created_at": row["created_at"],
        "rawPayload": core.json_loads(row["raw_payload_json"]),
        "normalizedPayload": core.json_loads(row["normalized_payload_json"]),
        "coreResponse": core.json_loads(row["core_response_json"]),
    }


def inbox_view(row):
    return {
        "delivery_id": row["delivery_id"],
        "deliveryId": row["delivery_id"],
        "department_id": row["department_id"],
        "event_seq": row["event_seq"],
        "event_type": row["event_type"],
        "status": row["status"],
        "created_at": row["created_at"],
        "acked_at": row["acked_at"],
        "envelope": core.json_loads(row["envelope_json"]),
    }


def active_encounter_id(patient_id: str | None) -> str | None:
    if not patient_id:
        return None
    with db.connect() as conn:
        row = conn.execute("SELECT encounter_id FROM encounters WHERE patient_id=? AND status='OPEN' ORDER BY opened_at DESC LIMIT 1", (patient_id,)).fetchone()
    return row["encounter_id"] if row else None


def build_closed_loop_debug_scenario():
    return {
        "id": "closed_loop_multi_patient_v2",
        "label": "Canonical closed-loop multi-patient flow",
        "description": "Creates standard-ID patients, moves them through handlers/rules, and discharges every patient at the end.",
        "defaults": {"stepDelayMs": 900, "idempotencyPrefix": "debug-closed-loop"},
        "patients": [
            {"key": "opA", "label": "OP A: registration -> triage -> consult -> lab -> ward -> discharge"},
            {"key": "opB", "label": "OP B: alternate consult room -> ward -> bed move -> discharge"},
            {"key": "edA", "label": "ED A: arrival -> treatment -> diagnostic -> ward -> discharge"},
            {"key": "icuA", "label": "ICU A: admission -> ICU bed -> exam -> ward -> discharge"},
        ],
        "steps": [
            scenario_upsert("opA", "outpatient", "R-OP-REGISTRATION", "Debug OP A {{runId}}", "门诊闭环 A：检查后住院"),
            scenario_move("opA", "outpatient", "OP_REGISTRATION_TO_TRIAGE_OR_WAITING", "R-OP-REGISTRATION", "R-OP-TRIAGE", "门诊 A 完成挂号后进入分诊"),
            scenario_move("opA", "outpatient", "OP_TRIAGE_TO_CONSULT_ROOM", "R-OP-TRIAGE", "R-OP-CONSULTATION-A", "门诊 A 分诊到诊室 A"),
            scenario_move("opA", "outpatient", "OP_CONSULT_TO_PAYMENT", "R-OP-CONSULTATION-A", "R-OP-PAYMENT", "门诊 A 诊后缴费"),
            scenario_move("opA", "outpatient", "OP_PAYMENT_TO_LAB", "R-OP-PAYMENT", "R-OP-LAB", "门诊 A 缴费后检验"),
            scenario_move("opA", "outpatient", "OP_LAB_RETURN_TO_WAITING", "R-OP-LAB", "R-OP-OUTPATIENT-WAITING", "门诊 A 检验完成返回候诊"),
            scenario_move("opA", "outpatient", "OP_SECOND_CONSULT_MOVE", "R-OP-OUTPATIENT-WAITING", "R-OP-CONSULTATION-A", "门诊 A 复诊"),
            scenario_transfer("opA", "outpatient", "OP_TO_WARD_MOVE", "R-OP-CONSULTATION-A", "R-WARD-WARD-ADMISSION", "ward", "门诊 A 转住院"),
            scenario_move("opA", "ward", "WARD_TO_DIAGNOSTIC_MOVE", "{{opA.currentRoom}}", "R-WARD-DIAGNOSTIC-CENTER", "住院 A 前往检查中心"),
            scenario_move("opA", "ward", "WARD_DIAGNOSTIC_RETURN", "R-WARD-DIAGNOSTIC-CENTER", "{{opA.bedRoom}}", "住院 A 检查后返回原病房"),
            scenario_discharge("opA", "ward", "WARD_DISCHARGE_EXIT_HOSPITAL", "住院 A 完成出院"),
            scenario_upsert("opB", "outpatient", "R-OP-REGISTRATION", "Debug OP B {{runId}}", "门诊闭环 B：转外科评估后住院"),
            scenario_move("opB", "outpatient", "OP_REGISTRATION_TO_TRIAGE_OR_WAITING", "R-OP-REGISTRATION", "R-OP-OUTPATIENT-WAITING", "门诊 B 挂号后候诊"),
            scenario_move("opB", "outpatient", "OP_TRIAGE_TO_CONSULT_ROOM", "R-OP-OUTPATIENT-WAITING", "R-OP-SURGERY", "门诊 B 分诊到外科"),
            scenario_transfer("opB", "outpatient", "OP_TO_WARD_MOVE", "R-OP-SURGERY", "R-WARD-WARD-ADMISSION", "ward", "门诊 B 转住院"),
            scenario_move("opB", "ward", "WARD_BED_TO_BED_MOVE", "{{opB.currentRoom}}", "R-WARD-NEURO", "住院 B 调整到神经病房"),
            scenario_discharge("opB", "ward", "WARD_DISCHARGE_EXIT_HOSPITAL", "住院 B 完成出院"),
            scenario_upsert("edA", "emergency", "R-ED-ENTRANCE", "Debug ED A {{runId}}", "急诊闭环：胸痛气促，检查后住院"),
            scenario_move("edA", "emergency", "ED_ENTRANCE_TO_REGISTRATION", "R-ED-ENTRANCE", "R-ED-REGISTRATION", "急诊 A 到登记"),
            scenario_move("edA", "emergency", "ED_REGISTRATION_TO_TRIAGE_OR_WAITING", "R-ED-REGISTRATION", "R-ED-TRIAGE", "急诊 A 登记后分诊"),
            scenario_move("edA", "emergency", "ED_TRIAGE_TO_TREATMENT_AREA", "R-ED-TRIAGE", "R-ED-MAJOR", "急诊 A 进入治疗区"),
            scenario_move("edA", "emergency", "ED_TO_DIAGNOSTIC_MOVE", "R-ED-MAJOR", "R-ED-DIAGNOSTIC", "急诊 A 前往检查"),
            scenario_move("edA", "emergency", "ED_DIAGNOSTIC_RETURN", "R-ED-DIAGNOSTIC", "R-ED-MAJOR", "急诊 A 检查返回"),
            scenario_transfer("edA", "emergency", "TRANSFER_ED_TO_WARD", "R-ED-MAJOR", "R-WARD-WARD-ADMISSION", "ward", "急诊 A 转住院"),
            scenario_discharge("edA", "ward", "WARD_DISCHARGE_EXIT_HOSPITAL", "急诊转住院 A 完成出院"),
            scenario_upsert("icuA", "icu", "R-ICU-ADMISSION", "Debug ICU A {{runId}}", "ICU 闭环：转普通住院并出院"),
            scenario_move("icuA", "icu", "ICU_ADMISSION_TO_BED", "R-ICU-ADMISSION", "R-ICU-BEDS-B", "ICU A 接收入床"),
            scenario_move("icuA", "icu", "ICU_TO_EXAM_OR_INTERVENTION", "{{icuA.currentRoom}}", "R-ICU-INTERVENTION-BAY", "ICU A 前往干预区"),
            scenario_move("icuA", "icu", "ICU_RETURN_TO_BED", "R-ICU-INTERVENTION-BAY", "{{icuA.bedRoom}}", "ICU A 返回原 ICU 床"),
            scenario_transfer("icuA", "icu", "TRANSFER_ICU_TO_WARD", "{{icuA.currentRoom}}", "R-WARD-WARD-ADMISSION", "ward", "ICU A 转普通住院"),
            scenario_discharge("icuA", "ward", "WARD_DISCHARGE_EXIT_HOSPITAL", "ICU A 转住院后完成出院"),
        ],
    }


def scenario_patient_id(patient_key):
    return f"{{{{{patient_key}.patientId}}}}"


def scenario_encounter_id(patient_key):
    return f"{{{{{patient_key}.encounterId}}}}"


def scenario_upsert(patient_key, department_id, room_id, name, symptoms):
    return {
        "patientKey": patient_key,
        "departmentId": department_id,
        "requestType": "patient_upsert",
        "title": f"{patient_key} upsert",
        "description": f"{patient_key} enters {department_id}.",
        "waitMs": 700,
        "payload": {"patient_id": scenario_patient_id(patient_key), "encounter_id": scenario_encounter_id(patient_key), "name": name, "gender": "unknown", "age": 48, "room_id": room_id, "status": "ARRIVED", "symptoms": symptoms, "summary": {"chief_complaint": symptoms, "debug_scenario": "closed_loop_multi_patient_v2"}},
    }


def scenario_move(patient_key, department_id, event_id, from_room_id, to_room_id, description):
    return {"patientKey": patient_key, "departmentId": department_id, "requestType": "movement_request", "title": event_id, "description": description, "waitMs": 900, "payload": {"patient_id": scenario_patient_id(patient_key), "encounter_id": scenario_encounter_id(patient_key), "event_id": event_id, "from_room_id": from_room_id, "to_room_id": to_room_id, "reason": description, "summary": {"debug_step": description}}}


def scenario_transfer(patient_key, department_id, event_id, from_room_id, to_room_id, to_department_id, description):
    return {"patientKey": patient_key, "departmentId": department_id, "requestType": "transfer_request", "title": event_id, "description": description, "waitMs": 1100, "payload": {"patient_id": scenario_patient_id(patient_key), "encounter_id": scenario_encounter_id(patient_key), "event_id": event_id, "from_room_id": from_room_id, "to_room_id": to_room_id, "to_department_id": to_department_id, "reason": description, "summary": {"chief_complaint": description, "key_findings": ["debug closed-loop transfer"]}, "requested_resources": {"bed_type": to_department_id.upper(), "monitor": to_department_id == "icu"}}}


def scenario_discharge(patient_key, department_id, event_id, description):
    return {"patientKey": patient_key, "departmentId": department_id, "requestType": "discharge_request", "title": event_id, "description": description, "waitMs": 800, "payload": {"patient_id": scenario_patient_id(patient_key), "encounter_id": scenario_encounter_id(patient_key), "event_id": event_id, "reason": description, "summary": {"final_status": "stable", "debug_outcome": "closed_loop_discharged"}}}


def read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def safe_rule_file(file_name: str) -> Path:
    if "/" in file_name or "\\" in file_name or not file_name.endswith(".json"):
        raise HTTPException(status_code=404, detail="Invalid rule file")
    return FULL_VIEW_ROOT / "event-rules" / file_name


app.mount("/", StaticFiles(directory=str(FULL_VIEW_ROOT), html=True), name="static")
