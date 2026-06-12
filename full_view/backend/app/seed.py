from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import re
import sqlite3
import uuid

from .db import DATA_DIR, FULL_VIEW_ROOT


DEPARTMENT_BY_FLOOR = {
    1: "emergency",
    2: "outpatient",
    3: "icu",
    4: "mdt",
    5: "ward",
}

DEFAULT_BED_CAPACITY_BY_KIND = {
    "icu": 4,
    "rescue": 2,
    "emergency": 2,
    "ward": 4,
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def dump_json(value) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, separators=(",", ":"))


def stable_patient_id(seed: str) -> str:
    return "P-" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:8]


def stable_encounter_id(seed: str) -> str:
    return "E-20260612000000-" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:4]


def ensure_standard_patient_id(value: str) -> str:
    value = str(value or "")
    if re.fullmatch(r"P-[0-9a-f]{8}", value):
        return value
    return stable_patient_id(value or uuid.uuid4().hex)


def ensure_standard_encounter_id(value: str) -> str:
    value = str(value or "")
    if re.fullmatch(r"E-[0-9]{14}-[0-9a-f]{4}", value):
        return value
    return stable_encounter_id(value or uuid.uuid4().hex)


def seed_if_empty(conn: sqlite3.Connection) -> None:
    count = conn.execute("SELECT COUNT(*) FROM locations").fetchone()[0]
    if count:
        return
    seed_locations_and_beds(conn)
    seed_patients(conn)
    seed_department_cursors(conn)


def seed_locations_and_beds(conn: sqlite3.Connection) -> None:
    now = utc_now()
    map_config = read_json(FULL_VIEW_ROOT / "map-config.json", {"floors": []})
    room_state = read_json(DATA_DIR / "room-state.json", {"rooms": {}})
    for floor in map_config.get("floors", []):
        floor_id = int(floor.get("id") or 0)
        department_id = DEPARTMENT_BY_FLOOR.get(floor_id, "hospital")
        for room in floor.get("rooms", []):
            room_id = room.get("id")
            if not room_id:
                continue
            kind = room.get("kind") or "room"
            state = (room_state.get("rooms") or {}).get(room_id, {})
            bed_ids = state.get("bedIds") or state.get("bed_ids") or []
            capacity = int(state.get("capacityBeds") or state.get("capacity_beds") or len(bed_ids) or DEFAULT_BED_CAPACITY_BY_KIND.get(kind, 0))
            conn.execute(
                """
                INSERT OR REPLACE INTO locations
                (room_id, visual_room_id, department_id, floor, kind, display_name, capacity_beds, map_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    room_id,
                    room.get("visualRoomId"),
                    department_id,
                    floor_id,
                    kind,
                    room.get("label") or room_id,
                    capacity,
                    dump_json(room),
                ),
            )
            for index in range(1, capacity + 1):
                bed_id = bed_ids[index - 1] if index <= len(bed_ids) else f"B-{room_id.removeprefix('R-')}-{index:02d}"
                conn.execute(
                    """
                    INSERT OR REPLACE INTO beds (bed_id, room_id, bed_index, status, patient_id, updated_at)
                    VALUES (?, ?, ?, 'available', NULL, ?)
                    """,
                    (bed_id, room_id, index, now),
                )


def seed_patients(conn: sqlite3.Connection) -> None:
    now = utc_now()
    payload = read_json(DATA_DIR / "patients.json", {"patients": []})
    for raw in payload.get("patients", []):
        patient_id = ensure_standard_patient_id(raw.get("patient_id") or raw.get("patientId") or raw.get("id"))
        room_id = raw.get("room_id") or raw.get("roomId")
        bed_id = raw.get("bed_id") or raw.get("bedId")
        department_id = raw.get("department_id") or department_for_room(conn, room_id)
        status = raw.get("status") or (raw.get("clinical") or {}).get("status") or "ARRIVED"
        conn.execute(
            """
            INSERT OR REPLACE INTO patients
            (patient_id, name, gender, age, dob, contact, allergies_json, chronic_conditions_json, blood_type,
             status, current_department_id, current_room_id, current_bed_id, profile_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                patient_id,
                raw.get("name") or "Unknown Patient",
                raw.get("gender") or "unknown",
                raw.get("age"),
                raw.get("dob"),
                raw.get("contact"),
                dump_json(raw.get("allergies") or []),
                dump_json(raw.get("chronic_conditions") or []),
                raw.get("blood_type"),
                status,
                department_id,
                room_id if room_exists(conn, room_id) else None,
                bed_id if bed_exists(conn, bed_id) else None,
                dump_json(raw),
                now,
                now,
            ),
        )
        encounter_id = ensure_standard_encounter_id(raw.get("encounter_id") or raw.get("encounterId") or patient_id)
        encounter_status = "CLOSED" if status == "DISCHARGED" else "OPEN"
        conn.execute(
            """
            INSERT OR IGNORE INTO encounters
            (encounter_id, patient_id, status, opened_at, closed_at, reason, summary_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                encounter_id,
                patient_id,
                encounter_status,
                now,
                now if encounter_status == "CLOSED" else None,
                raw.get("symptoms") or "",
                dump_json(raw.get("clinical") or {}),
                now,
                now,
            ),
        )
        if department_id:
            conn.execute(
                """
                INSERT OR IGNORE INTO episodes
                (episode_id, encounter_id, patient_id, department_id, status, started_at, ended_at, department_payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"EP-{encounter_id}-{department_id}",
                    encounter_id,
                    patient_id,
                    department_id,
                    "ACTIVE" if encounter_status == "OPEN" else "CLOSED",
                    now,
                    now if encounter_status == "CLOSED" else None,
                    dump_json(raw.get("clinical") or {}),
                ),
            )
        if bed_id and bed_exists(conn, bed_id):
            conn.execute("UPDATE beds SET status='occupied', patient_id=?, updated_at=? WHERE bed_id=?", (patient_id, now, bed_id))
            conn.execute(
                """
                INSERT OR IGNORE INTO bed_assignments
                (assignment_id, bed_id, room_id, patient_id, encounter_id, assigned_at, released_at, status)
                VALUES (?, ?, ?, ?, ?, ?, NULL, 'active')
                """,
                (f"BA-{bed_id}-{patient_id}", bed_id, room_id, patient_id, encounter_id, now),
            )


def seed_department_cursors(conn: sqlite3.Connection) -> None:
    now = utc_now()
    for department_id in ["outpatient", "emergency", "icu", "mdt", "ward", "dashboard"]:
        conn.execute(
            "INSERT OR IGNORE INTO department_sync_cursor (department_id, last_delivered_seq, last_acked_seq, updated_at) VALUES (?, 0, 0, ?)",
            (department_id, now),
        )


def department_for_room(conn: sqlite3.Connection, room_id: str | None) -> str | None:
    if not room_id:
        return None
    row = conn.execute("SELECT department_id FROM locations WHERE room_id=?", (room_id,)).fetchone()
    return row["department_id"] if row else None


def room_exists(conn: sqlite3.Connection, room_id: str | None) -> bool:
    return bool(room_id and conn.execute("SELECT 1 FROM locations WHERE room_id=?", (room_id,)).fetchone())


def bed_exists(conn: sqlite3.Connection, bed_id: str | None) -> bool:
    return bool(bed_id and conn.execute("SELECT 1 FROM beds WHERE bed_id=?", (bed_id,)).fetchone())
