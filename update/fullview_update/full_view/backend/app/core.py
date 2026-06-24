from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import re
import sqlite3
import uuid

from .db import DATA_DIR, FULL_VIEW_ROOT, db
from .seed import dump_json, seed_if_empty, utc_now


DEPARTMENT_ORDER = ["outpatient", "emergency", "icu", "mdt", "ward"]
DEPARTMENT_PRODUCERS = {
    "outpatient": "groupA.outpatient",
    "emergency": "groupB.ed",
    "icu": "groupC.icu",
    "mdt": "groupM.mdt",
    "ward": "groupD.inpatient",
}
DEPARTMENT_LABELS = {
    "outpatient": "Outpatient",
    "emergency": "Emergency",
    "icu": "ICU",
    "mdt": "MDT",
    "ward": "Ward",
}
ENABLED_REQUEST_TYPES = {
    "outpatient": ["patient_upsert", "encounter_open", "movement_request", "transfer_request", "clinical_event"],
    "emergency": ["patient_upsert", "encounter_open", "movement_request", "transfer_request", "clinical_event"],
    "icu": ["patient_upsert", "encounter_open", "movement_request", "transfer_request", "discharge_request", "clinical_event"],
    "mdt": ["patient_upsert", "encounter_open", "clinical_event"],
    "ward": ["patient_upsert", "encounter_open", "movement_request", "transfer_request", "discharge_request", "clinical_event"],
}
PATIENT_ID_RE = re.compile(r"^P-[0-9a-f]{8}$")
ENCOUNTER_ID_RE = re.compile(r"^E-[0-9]{14}-[0-9a-f]{4}$")
RULE_CATEGORY_BY_DEPARTMENT = {
    "outpatient": "outpatient",
    "emergency": "emergency",
    "icu": "icu",
    "ward": "ward",
}


def json_loads(value, default=None):
    if value is None:
        return {} if default is None else default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {} if default is None else default


def api_ok(data, trace_id=None):
    return {"ok": True, "traceId": trace_id or new_trace_id(), "data": data}


def api_error(code, message, trace_id=None, details=None):
    payload = {"ok": False, "traceId": trace_id or new_trace_id(), "error": {"code": code, "message": message}}
    if details is not None:
        payload["error"]["details"] = details
    return payload


def new_trace_id():
    return "trc_" + uuid.uuid4().hex[:26]


def new_event_id():
    return "evt_" + uuid.uuid4().hex[:26].upper()


def request_hash(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def init_database():
    db.initialize()
    with db.transaction() as conn:
        seed_if_empty(conn)


def list_departments():
    return [department_summary(department_id) for department_id in DEPARTMENT_ORDER]


def department_summary(department_id):
    return {
        "id": department_id,
        "label": DEPARTMENT_LABELS[department_id],
        "producer": DEPARTMENT_PRODUCERS[department_id],
        "enabledRequestTypes": ENABLED_REQUEST_TYPES[department_id],
        "dashboardPath": f"/department-dashboard.html#{department_id}",
    }


def department_capabilities(department_id):
    meta = ensure_department(department_id)
    rules = rules_for_department(department_id)
    return {
        **department_summary(department_id),
        "architecture": "Department Handler -> Fullview Core SQLite Transaction -> Inbox/Outbox -> Redis/Map/Dashboard",
        "requestTypes": [
            {
                "id": request_type,
                "label": request_type.replace("_", " ").title(),
                "description": request_type_description(request_type, department_id),
                "method": "POST",
                "path": f"/api/v1/departments/{department_id}/requests/{request_type}",
                "playgroundPath": f"/api/v1/departments/{department_id}/playground/{request_type}",
                "enabled": True,
                "allowedRules": rules.get(request_type, []),
            }
            for request_type in meta["enabled_request_types"]
        ],
        "rulesSource": {"index": "/api/event-rules"},
        "errorCodes": [
            "DEPARTMENT_NOT_FOUND",
            "REQUEST_TYPE_NOT_ENABLED",
            "MISSING_PATIENT_ID",
            "INVALID_PATIENT_ID",
            "MISSING_ENCOUNTER_ID",
            "INVALID_ENCOUNTER_ID",
            "MISSING_EVENT_ID",
            "RULE_NOT_ALLOWED_FOR_DEPARTMENT",
            "PATIENT_NOT_FOUND",
            "ROOM_NOT_FOUND",
            "BED_UNAVAILABLE",
            "ICU_BED_UNAVAILABLE",
            "WARD_BED_UNAVAILABLE",
            "IDEMPOTENCY_CONFLICT",
        ],
    }


def ensure_department(department_id):
    if department_id not in ENABLED_REQUEST_TYPES:
        return None
    return {
        "id": department_id,
        "label": DEPARTMENT_LABELS[department_id],
        "producer": DEPARTMENT_PRODUCERS[department_id],
        "enabled_request_types": ENABLED_REQUEST_TYPES[department_id],
    }


def request_type_description(request_type, department_id):
    if department_id == "mdt" and request_type == "clinical_event":
        return "Submit MDT consultation requests/results; it writes events without moving beds or patient locations."
    return {
        "patient_upsert": "Create or refresh the canonical patient profile.",
        "encounter_open": "Open or refresh a canonical encounter and department episode.",
        "movement_request": "Ask Fullview Core to move a patient by a Rules Admin event.",
        "transfer_request": "Ask Fullview Core to coordinate a cross-department transfer.",
        "discharge_request": "Ask Fullview Core to discharge a patient and release resources.",
        "clinical_event": "Submit a clinical fact, order, exam, or summary without direct movement.",
    }.get(request_type, request_type)


def request_schema(request_type):
    base = {
        "type": "object",
        "required": ["patient_id"],
        "properties": {
            "patient_id": {"type": "string", "pattern": "P-[0-9a-f]{8}"},
            "encounter_id": {"type": "string", "pattern": "E-[0-9]{14}-[0-9a-f]{4}"},
            "reason": {"type": "string"},
            "summary": {"type": "object"},
        },
    }
    return {
        "patient_upsert": {
            **base,
            "required": ["patient_id", "name"],
            "properties": {**base["properties"], "name": {"type": "string"}, "gender": {"type": "string"}, "age": {"type": "integer"}, "room_id": {"type": "string", "pattern": "R-*"}},
        },
        "encounter_open": {**base, "required": ["patient_id", "encounter_id"]},
        "movement_request": {
            **base,
            "required": ["patient_id", "encounter_id", "event_id", "from_room_id", "to_room_id"],
            "properties": {**base["properties"], "event_id": {"type": "string"}, "from_room_id": {"type": "string", "pattern": "R-*"}, "to_room_id": {"type": "string", "pattern": "R-*"}, "staff_id": {"type": "string", "description": "Optional Fullview standard escort staff id, e.g. NURSE_RESP_01."}},
        },
        "transfer_request": {
            **base,
            "required": ["patient_id", "encounter_id", "from_room_id", "to_department_id", "reason"],
            "properties": {**base["properties"], "event_id": {"type": "string"}, "from_room_id": {"type": "string", "pattern": "R-*"}, "to_room_id": {"type": "string"}, "to_department_id": {"type": "string"}, "requested_resources": {"type": "object"}},
        },
        "discharge_request": {
            **base,
            "required": ["patient_id", "encounter_id", "reason"],
            "properties": {**base["properties"], "event_id": {"type": "string"}, "bed_id": {"type": "string", "pattern": "B-*"}},
        },
        "clinical_event": {
            **base,
            "required": ["patient_id", "event_type", "summary"],
            "properties": {**base["properties"], "event_type": {"type": "string"}, "event_id": {"type": "string"}, "consultation_id": {"type": "string"}, "recommendations": {"type": "array"}, "staffId": {"type": "string", "description": "Fullview standard staff id, e.g. NURSE_RESP_01 or DOCTOR_RESP_01."}, "fromRoomId": {"type": "string", "pattern": "R-*"}, "toRoomId": {"type": "string", "pattern": "R-*"}, "returnRoomId": {"type": "string", "pattern": "R-*"}, "durationSeconds": {"type": "integer"}},
        },
    }.get(request_type, base)


def department_examples(department_id):
    patient_id = {
        "outpatient": "P-a1b2c3d4",
        "emergency": "P-b2c3d4e5",
        "icu": "P-5e56a778",
        "mdt": "P-d4e5f6a7",
        "ward": "P-c6617e6b",
    }[department_id]
    encounter_id = "E-20260612103000-9f3a"
    examples = {
        "patient_upsert": {
            "patient_id": patient_id,
            "encounter_id": encounter_id,
            "name": "Debug Patient",
            "gender": "unknown",
            "age": 56,
            "room_id": default_room_for_department(department_id),
            "summary": {"chief_complaint": "debug flow"},
        },
        "encounter_open": {
            "patient_id": patient_id,
            "encounter_id": encounter_id,
            "reason": f"{department_id} debug encounter",
            "summary": {"chief_complaint": "debug flow"},
        },
        "movement_request": movement_example_for(department_id, patient_id, encounter_id),
        "transfer_request": transfer_example_for(department_id, patient_id, encounter_id),
        "discharge_request": {
            "patient_id": patient_id,
            "encounter_id": encounter_id,
            "event_id": discharge_event_id_for_department(department_id),
            "reason": "stable for discharge",
            "summary": {"final_status": "stable", "follow_up": "outpatient review in 7 days"},
        },
        "clinical_event": clinical_example_for(department_id, patient_id, encounter_id),
    }
    return {key: value for key, value in examples.items() if key in ENABLED_REQUEST_TYPES[department_id]}


def handle_department_request(department_id, request_type, payload, idempotency_key=""):
    trace_id = new_trace_id()
    meta = ensure_department(department_id)
    if not meta:
        return api_error("DEPARTMENT_NOT_FOUND", f"Unknown department: {department_id}", trace_id)
    if request_type not in meta["enabled_request_types"]:
        return api_error("REQUEST_TYPE_NOT_ENABLED", f"{request_type} is not enabled for {department_id}.", trace_id)
    normalized = normalize_department_payload(department_id, request_type, payload)
    validation = validate_base_request(request_type, normalized)
    if validation:
        result = rejected_core_response(normalized, validation["code"], validation["message"])
        return persist_rejected_request(department_id, request_type, idempotency_key, payload, normalized, result, trace_id)

    scope = f"{department_id}:{request_type}"
    key = str(idempotency_key or "").strip()
    with db.transaction() as conn:
        if key:
            replay = conn.execute("SELECT request_hash, response_json FROM idempotency_keys WHERE scope=? AND idempotency_key=?", (scope, key)).fetchone()
            if replay:
                if replay["request_hash"] != request_hash(payload):
                    return api_error("IDEMPOTENCY_CONFLICT", "Idempotency-Key was reused with a different payload.", trace_id)
                response = json_loads(replay["response_json"])
                response["data"]["idempotencyReplay"] = True
                return response

        request_id = "REQ-" + uuid.uuid4().hex
        conn.execute(
            """
            INSERT INTO department_requests
            (request_id, department_id, request_type, idempotency_key, raw_payload_json, normalized_payload_json,
             status, core_response_json, error_code, correlation_id, trace_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'pending', '{}', NULL, ?, ?, ?)
            """,
            (request_id, department_id, request_type, key or None, dump_json(payload), dump_json(normalized), normalized["correlation_id"], trace_id, utc_now()),
        )
        result = dispatch(conn, department_id, request_type, normalized)
        status = "accepted" if result.get("accepted") else "rejected"
        error_code = result.get("reasonCode")
        conn.execute(
            "UPDATE department_requests SET status=?, core_response_json=?, error_code=? WHERE request_id=?",
            (status, dump_json(result), error_code, request_id),
        )
        conn.execute(
            """
            INSERT INTO department_outbox (outbox_id, department_id, request_id, event_seq, envelope_json, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'ready', ?)
            """,
            ("DOUT-" + uuid.uuid4().hex, department_id, request_id, result.get("eventSeq"), dump_json({"request_id": request_id, "core_response": result}), utc_now()),
        )
        response = api_ok(
            {
                "departmentId": department_id,
                "requestType": request_type,
                "status": status,
                "accepted": bool(result.get("accepted")),
                "correlationId": normalized["correlation_id"],
                "normalizedPayload": normalized,
                "coreResponse": result,
            },
            trace_id,
        )
        if not result.get("accepted"):
            response["error"] = {"code": error_code or "REQUEST_REJECTED", "message": result.get("message") or "Request rejected by Fullview Core.", "details": result}
        if key:
            conn.execute(
                "INSERT INTO idempotency_keys (scope, idempotency_key, request_hash, response_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (scope, key, request_hash(payload), dump_json(response), utc_now()),
            )
        return response


def persist_rejected_request(department_id, request_type, idempotency_key, payload, normalized, result, trace_id):
    with db.transaction() as conn:
        conn.execute(
            """
            INSERT INTO department_requests
            (request_id, department_id, request_type, idempotency_key, raw_payload_json, normalized_payload_json,
             status, core_response_json, error_code, correlation_id, trace_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'rejected', ?, ?, ?, ?, ?)
            """,
            (
                "REQ-" + uuid.uuid4().hex,
                department_id,
                request_type,
                idempotency_key or None,
                dump_json(payload),
                dump_json(normalized),
                dump_json(result),
                result.get("reasonCode"),
                normalized["correlation_id"],
                trace_id,
                utc_now(),
            ),
        )
    response = api_ok(
        {
            "departmentId": department_id,
            "requestType": request_type,
            "status": "rejected",
            "accepted": False,
            "correlationId": normalized["correlation_id"],
            "normalizedPayload": normalized,
            "coreResponse": result,
        },
        trace_id,
    )
    response["error"] = {"code": result.get("reasonCode"), "message": result.get("message"), "details": result}
    return response


def normalize_department_payload(department_id, request_type, payload):
    payload = dict(payload or {})
    if "patientId" in payload and "patient_id" not in payload:
        payload["patient_id"] = payload["patientId"]
    if "encounterId" in payload and "encounter_id" not in payload:
        payload["encounter_id"] = payload["encounterId"]
    if "fromRoomId" in payload and "from_room_id" not in payload:
        payload["from_room_id"] = payload["fromRoomId"]
    if "toRoomId" in payload and "to_room_id" not in payload:
        payload["to_room_id"] = payload["toRoomId"]
    correlation_id = payload.get("correlation_id") or payload.get("correlationId") or new_event_id()
    return {
        **payload,
        "department_id": department_id,
        "source_department_id": department_id,
        "producer": DEPARTMENT_PRODUCERS[department_id],
        "request_type": request_type,
        "correlation_id": correlation_id,
        "received_at": utc_now(),
    }


def validate_base_request(request_type, payload):
    patient_id = payload.get("patient_id")
    if not patient_id:
        return {"code": "MISSING_PATIENT_ID", "message": "patient_id is required."}
    if not PATIENT_ID_RE.fullmatch(patient_id):
        return {"code": "INVALID_PATIENT_ID", "message": "patient_id must match P-{8 lowercase hex}."}
    if request_type not in {"patient_upsert", "clinical_event"}:
        encounter_id = payload.get("encounter_id")
        if not encounter_id:
            return {"code": "MISSING_ENCOUNTER_ID", "message": "encounter_id is required."}
        if not ENCOUNTER_ID_RE.fullmatch(encounter_id):
            return {"code": "INVALID_ENCOUNTER_ID", "message": "encounter_id must match E-{YYYYMMDDHHmmss}-{4 lowercase hex}."}
    return None


def dispatch(conn, department_id, request_type, payload):
    if request_type == "patient_upsert":
        return patient_upsert(conn, department_id, payload)
    if request_type == "encounter_open":
        return encounter_open(conn, department_id, payload)
    if request_type == "movement_request":
        return movement_request(conn, department_id, payload)
    if request_type == "transfer_request":
        return transfer_request(conn, department_id, payload)
    if request_type == "discharge_request":
        return discharge_request(conn, department_id, payload)
    if request_type == "clinical_event":
        return clinical_event(conn, department_id, payload)
    return rejected_core_response(payload, "REQUEST_TYPE_UNKNOWN", f"Unknown request type: {request_type}")


def patient_upsert(conn, department_id, payload):
    patient_id = payload["patient_id"]
    room_id = payload.get("room_id") or default_room_for_department(department_id)
    if room_id and not room_exists(conn, room_id):
        return rejected_core_response(payload, "ROOM_NOT_FOUND", f"Unknown room_id: {room_id}")
    now = utc_now()
    conn.execute(
        """
        INSERT INTO patients
        (patient_id, name, gender, age, dob, contact, allergies_json, chronic_conditions_json, blood_type,
         status, current_department_id, current_room_id, current_bed_id, profile_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)
        ON CONFLICT(patient_id) DO UPDATE SET
          name=excluded.name, gender=excluded.gender, age=excluded.age, contact=excluded.contact,
          status=excluded.status, current_department_id=excluded.current_department_id,
          current_room_id=excluded.current_room_id, profile_json=excluded.profile_json, updated_at=excluded.updated_at
        """,
        (
            patient_id,
            payload.get("name") or "Unknown Patient",
            payload.get("gender") or "unknown",
            payload.get("age"),
            payload.get("dob"),
            payload.get("contact"),
            dump_json(payload.get("allergies") or []),
            dump_json(payload.get("chronic_conditions") or []),
            payload.get("blood_type"),
            payload.get("status") or "ARRIVED",
            department_id,
            room_id,
            dump_json(payload),
            now,
            now,
        ),
    )
    encounter_id = payload.get("encounter_id")
    if encounter_id and ENCOUNTER_ID_RE.fullmatch(encounter_id):
        ensure_encounter(conn, patient_id, encounter_id, department_id, payload)
    event_seq = write_event(conn, "patient.upserted", payload, department_id, None, accepted=True, animation_plan=animation_plan("patient-upsert", None, room_id, payload))
    return accepted_core_response(payload, event_seq, "patient.upserted", animation_plan("patient-upsert", None, room_id, payload), {"patient_status": payload.get("status") or "ARRIVED"})


def encounter_open(conn, department_id, payload):
    patient = get_patient(conn, payload["patient_id"])
    if not patient:
        return rejected_core_response(payload, "PATIENT_NOT_FOUND", f"No patient found for {payload['patient_id']}.")
    ensure_encounter(conn, payload["patient_id"], payload["encounter_id"], department_id, payload)
    event_seq = write_event(conn, "encounter.opened", payload, department_id, department_id, accepted=True)
    return accepted_core_response(payload, event_seq, "encounter.opened", {}, {"encounter_status": "OPEN"})


def movement_request(conn, department_id, payload):
    rule_error = ensure_rule_allowed(department_id, "movement_request", payload.get("event_id"))
    if rule_error:
        return rejected_core_response(payload, rule_error["code"], rule_error["message"], rule_error.get("details"))
    return apply_rule_move(conn, department_id, payload, "patient.moved")


def transfer_request(conn, department_id, payload):
    if payload.get("event_id"):
        rule_error = ensure_rule_allowed(department_id, "transfer_request", payload.get("event_id"))
        if rule_error:
            return rejected_core_response(payload, rule_error["code"], rule_error["message"], rule_error.get("details"))
    else:
        payload["event_id"] = default_transfer_event_id(department_id, payload.get("to_department_id"))
    return apply_rule_move(conn, department_id, payload, "patient.transferred", target_department_id=payload.get("to_department_id"))


def discharge_request(conn, department_id, payload):
    if payload.get("event_id"):
        rule_error = ensure_rule_allowed(department_id, "discharge_request", payload.get("event_id"))
        if rule_error:
            return rejected_core_response(payload, rule_error["code"], rule_error["message"], rule_error.get("details"))
    patient = get_patient(conn, payload["patient_id"])
    if not patient:
        return rejected_core_response(payload, "PATIENT_NOT_FOUND", f"No patient found for {payload['patient_id']}.")
    release_patient_bed(conn, payload["patient_id"])
    now = utc_now()
    conn.execute("UPDATE patients SET status='DISCHARGED', current_room_id=NULL, current_bed_id=NULL, updated_at=? WHERE patient_id=?", (now, payload["patient_id"]))
    conn.execute("UPDATE encounters SET status='CLOSED', closed_at=?, updated_at=? WHERE encounter_id=?", (now, now, payload["encounter_id"]))
    conn.execute("UPDATE episodes SET status='CLOSED', ended_at=? WHERE encounter_id=? AND ended_at IS NULL", (now, payload["encounter_id"]))
    animation = animation_plan("patient-discharge", patient["current_room_id"], None, payload)
    event_seq = write_event(conn, "patient.discharged", payload, department_id, None, accepted=True, animation_plan=animation, extra_targets=historical_departments(conn, payload["patient_id"], payload["encounter_id"]))
    write_event(conn, "encounter.closed", payload, department_id, None, accepted=True, extra_targets=historical_departments(conn, payload["patient_id"], payload["encounter_id"]))
    return accepted_core_response(payload, event_seq, "patient.discharged", animation, {"patient_status": "DISCHARGED", "encounter_status": "CLOSED", "bed_released": True})


def clinical_event(conn, department_id, payload):
    patient = get_patient(conn, payload["patient_id"])
    if not patient:
        return rejected_core_response(payload, "PATIENT_NOT_FOUND", f"No patient found for {payload['patient_id']}.")
    staff_event_id = payload.get("event_id") or payload.get("event_type")
    if staff_event_id in {"WARD_NURSE_ORDER_VISIT", "WARD_DOCTOR_ROUND_VISIT"}:
        payload["event_id"] = staff_event_id
        rule_error = ensure_rule_allowed(department_id, "clinical_event", staff_event_id)
        if rule_error:
            return rejected_core_response(payload, rule_error["code"], rule_error["message"], rule_error.get("details"))
    staff_visit = maybe_build_staff_visit_plan(conn, department_id, payload, patient)
    if staff_visit.get("error"):
        return rejected_core_response(payload, staff_visit["error"], staff_visit["message"])
    if payload.get("encounter_id") and ENCOUNTER_ID_RE.fullmatch(payload["encounter_id"]):
        ensure_encounter(conn, payload["patient_id"], payload["encounter_id"], department_id, payload)
    event_type = payload.get("event_type") or ("mdt.consultation_requested" if department_id == "mdt" else "clinical.event")
    if staff_visit.get("plan"):
        payload = {**payload, "staffMovePlan": staff_visit["plan"], "staff_move_plan": staff_visit["snake_plan"]}
        event_type = "staff.visit"
    event_seq = write_event(conn, event_type, payload, department_id, payload.get("source_department_id"), accepted=True, extra_targets=clinical_targets(department_id, payload))
    return accepted_core_response(payload, event_seq, payload.get("event_id") or payload.get("event_type") or event_type, {}, {"location_changed": False}, staff_move_plan=staff_visit.get("plan"))


def apply_rule_move(conn, department_id, payload, event_type, target_department_id=None):
    patient = get_patient(conn, payload["patient_id"])
    if not patient:
        return rejected_core_response(payload, "PATIENT_NOT_FOUND", f"No patient found for {payload['patient_id']}.")
    rule = find_rule(payload.get("event_id"))
    if not rule:
        return rejected_core_response(payload, "RULE_NOT_FOUND", f"No rule found for {payload.get('event_id')}.")
    from_room_id = payload.get("from_room_id") or patient["current_room_id"]
    requested_to_room_id = resolve_symbolic_target_room(conn, payload.get("to_room_id"), patient)
    if from_room_id and from_room_id != "outside" and not room_exists(conn, from_room_id):
        return rejected_core_response(payload, "ROOM_NOT_FOUND", f"Unknown from_room_id: {from_room_id}.")
    if requested_to_room_id and requested_to_room_id != "exit" and not room_exists(conn, requested_to_room_id):
        return rejected_core_response(payload, "ROOM_NOT_FOUND", f"Unknown to_room_id: {requested_to_room_id}.")
    room_scope_error = validate_rule_room_scope(conn, rule, payload, patient, from_room_id, requested_to_room_id)
    if room_scope_error:
        return rejected_core_response(payload, room_scope_error["code"], room_scope_error["message"], room_scope_error.get("details"))
    source_error = validate_special_rule_source(conn, payload, patient, requested_to_room_id)
    if source_error:
        return rejected_core_response(payload, source_error["code"], source_error["message"])
    escort = maybe_build_patient_escort_plan(conn, department_id, payload)
    if escort.get("error"):
        return rejected_core_response(payload, escort["error"], escort["message"])
    movement = rule.get("movement") or {}
    final_form = movement.get("finalForm") or movement.get("final_form") or "walking"
    resource_policy = movement.get("resourcePolicy") or movement.get("resource_policy") or {}
    target_room_id = resolve_target_room(conn, department_id, target_department_id, requested_to_room_id, final_form)
    final_form = final_form_for_target(conn, department_id, target_room_id, final_form)
    if not target_room_id and final_form != "hidden":
        code = "ICU_BED_UNAVAILABLE" if target_department_id == "icu" else "WARD_BED_UNAVAILABLE" if target_department_id == "ward" else "BED_UNAVAILABLE"
        event_seq = write_event(conn, event_type, payload, department_id, target_department_id, accepted=False, reason_code=code)
        return rejected_core_response(payload, code, f"No available {target_department_id or department_id} bed/resource.", {"eventSeq": event_seq})
    resource_error = validate_outpatient_room_resource(conn, department_id, payload, patient, from_room_id, target_room_id)
    if resource_error:
        event_seq = write_event(conn, event_type, payload, department_id, target_department_id, accepted=False, reason_code=resource_error["code"])
        details = {"eventSeq": event_seq, **resource_error.get("details", {})}
        return rejected_core_response(payload, resource_error["code"], resource_error["message"], details)
    bed_id = None
    source_bed_retained = bool(resource_policy.get("retainSourceBed") or resource_policy.get("retain_source_bed"))
    release_source_bed = bool(resource_policy.get("releaseSourceBed") or resource_policy.get("release_source_bed") or (final_form == "bed" and not source_bed_retained))
    if department_id == "outpatient" and final_form != "bed" and not source_bed_retained and patient["current_bed_id"]:
        source_bed_room = retained_patient_bed_room(conn, patient["current_bed_id"], payload["patient_id"])
        if source_bed_room and source_bed_room == from_room_id:
            release_source_bed = True
    if release_source_bed:
        release_patient_bed(conn, payload["patient_id"])
    if final_form == "bed" and target_room_id:
        bed_id = retained_patient_bed_id(conn, payload["patient_id"], patient["current_bed_id"], target_room_id)
        if not bed_id:
            bed_id = assign_available_bed(conn, payload["patient_id"], payload.get("encounter_id"), target_room_id)
        if not bed_id:
            code = "ICU_BED_UNAVAILABLE" if target_department_id == "icu" else "WARD_BED_UNAVAILABLE" if target_department_id == "ward" else "BED_UNAVAILABLE"
            event_seq = write_event(conn, event_type, payload, department_id, target_department_id, accepted=False, reason_code=code)
            return rejected_core_response(payload, code, f"No available bed in {target_room_id}.", {"eventSeq": event_seq})
    now = utc_now()
    final_department_id = target_department_id or department_for_room(conn, target_room_id) or department_id
    conn.execute(
        "UPDATE patients SET status=?, current_department_id=?, current_room_id=?, current_bed_id=COALESCE(?, current_bed_id), updated_at=? WHERE patient_id=?",
        ("TRANSFERRING" if event_type == "patient.transferred" else "IN_PROGRESS", final_department_id, target_room_id, bed_id, now, payload["patient_id"]),
    )
    if payload.get("encounter_id"):
        ensure_encounter(conn, payload["patient_id"], payload["encounter_id"], final_department_id, payload)
        ensure_episode(conn, payload["patient_id"], payload["encounter_id"], final_department_id, payload)
    conn.execute(
        "INSERT INTO location_history (history_id, patient_id, encounter_id, from_room_id, to_room_id, event_seq, moved_at) VALUES (?, ?, ?, ?, ?, NULL, ?)",
        ("LH-" + uuid.uuid4().hex, payload["patient_id"], payload.get("encounter_id"), from_room_id, target_room_id, now),
    )
    animation = animation_plan("patient-move", from_room_id, target_room_id, payload, rule)
    if escort.get("porter_id"):
        animation["porter_id"] = escort["porter_id"]
        animation["porter_return"] = escort["porter_return"]
    event_seq = write_event(conn, event_type, payload, department_id, final_department_id, accepted=True, animation_plan=animation)
    conn.execute("UPDATE location_history SET event_seq=? WHERE patient_id=? AND moved_at=?", (event_seq, payload["patient_id"], now))
    return accepted_core_response(
        payload,
        event_seq,
        payload.get("event_id") or event_type,
        animation,
        {
            "patient_status": "TRANSFERRING" if event_type == "patient.transferred" else "IN_PROGRESS",
            "target_reserved": bool(bed_id),
            "bed_room_id": target_room_id if bed_id else patient["current_room_id"],
            "bed_id": bed_id or patient["current_bed_id"],
            "previous_room_id": patient["current_room_id"],
        },
    )


def ensure_encounter(conn, patient_id, encounter_id, department_id, payload):
    now = utc_now()
    conn.execute(
        """
        INSERT INTO encounters (encounter_id, patient_id, status, opened_at, reason, summary_json, created_at, updated_at)
        VALUES (?, ?, 'OPEN', ?, ?, ?, ?, ?)
        ON CONFLICT(encounter_id) DO UPDATE SET status='OPEN', updated_at=excluded.updated_at, summary_json=excluded.summary_json
        """,
        (encounter_id, patient_id, now, payload.get("reason"), dump_json(payload.get("summary") or {}), now, now),
    )
    ensure_episode(conn, patient_id, encounter_id, department_id, payload)


def ensure_episode(conn, patient_id, encounter_id, department_id, payload):
    now = utc_now()
    conn.execute(
        """
        INSERT INTO episodes (episode_id, encounter_id, patient_id, department_id, status, started_at, department_payload_json)
        VALUES (?, ?, ?, ?, 'ACTIVE', ?, ?)
        ON CONFLICT(encounter_id, department_id) DO UPDATE SET status='ACTIVE', department_payload_json=excluded.department_payload_json
        """,
        (f"EP-{encounter_id}-{department_id}", encounter_id, patient_id, department_id, now, dump_json(payload)),
    )


def write_event(conn, event_type, payload, source_department_id, target_department_id=None, accepted=True, reason_code=None, animation_plan=None, extra_targets=None):
    occurred_at = utc_now()
    conn.execute(
        """
        INSERT INTO hospital_events
        (event_id, event_type, patient_id, encounter_id, source_department_id, target_department_id,
         correlation_id, producer, payload_json, animation_plan_json, accepted, reason_code, occurred_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payload.get("event_id") or new_event_id(),
            event_type,
            payload.get("patient_id"),
            payload.get("encounter_id"),
            source_department_id,
            target_department_id,
            payload.get("correlation_id") or new_event_id(),
            payload.get("producer") or DEPARTMENT_PRODUCERS.get(source_department_id, "fullview.core"),
            dump_json(payload),
            dump_json(animation_plan or {}),
            1 if accepted else 0,
            reason_code,
            occurred_at,
        ),
    )
    event_seq = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    envelope = event_envelope(conn, event_seq)
    conn.execute(
        "INSERT INTO event_outbox (outbox_id, event_seq, channel, envelope_json, status, attempts, created_at) VALUES (?, ?, ?, ?, 'pending', 0, ?)",
        ("OUT-" + uuid.uuid4().hex, event_seq, f"hospital.{event_type}", dump_json(envelope), occurred_at),
    )
    targets = event_targets(conn, source_department_id, target_department_id, payload.get("patient_id"), payload.get("encounter_id"), extra_targets)
    for department_id in targets:
        conn.execute(
            """
            INSERT OR IGNORE INTO department_inbox
            (delivery_id, department_id, event_seq, event_type, envelope_json, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'pending', ?)
            """,
            ("DIN-" + uuid.uuid4().hex, department_id, event_seq, event_type, dump_json(envelope), occurred_at),
        )
    return event_seq


def event_envelope(conn, event_seq):
    row = conn.execute("SELECT * FROM hospital_events WHERE event_seq=?", (event_seq,)).fetchone()
    payload = json_loads(row["payload_json"])
    animation = json_loads(row["animation_plan_json"])
    staff_plan = payload.get("staffMovePlan") or to_camel_staff_plan(payload.get("staff_move_plan") or {})
    envelope = {
        "event_seq": row["event_seq"],
        "eventSeq": row["event_seq"],
        "event_id": row["event_id"],
        "eventId": row["event_id"],
        "event_type": row["event_type"],
        "eventType": row["event_type"],
        "schema_version": "1.0",
        "occurred_at": row["occurred_at"],
        "producer": row["producer"],
        "patient_id": row["patient_id"],
        "patientId": row["patient_id"],
        "encounter_id": row["encounter_id"],
        "encounterId": row["encounter_id"],
        "correlation_id": row["correlation_id"],
        "accepted": bool(row["accepted"]),
        "reasonCode": row["reason_code"],
        "animation_plan": animation,
        "animationPlan": to_camel_animation(animation),
        "payload": payload,
    }
    if staff_plan:
        envelope["staffMovePlan"] = staff_plan
        envelope["staff_move_plan"] = to_snake_staff_plan(staff_plan)
    return envelope


def event_targets(conn, source_department_id, target_department_id, patient_id, encounter_id, extra_targets=None):
    targets = {"dashboard"}
    if source_department_id:
        targets.add(source_department_id)
    if target_department_id:
        targets.add(target_department_id)
    for department_id in extra_targets or []:
        targets.add(department_id)
    if encounter_id:
        rows = conn.execute("SELECT department_id FROM episodes WHERE encounter_id=?", (encounter_id,)).fetchall()
        for row in rows:
            targets.add(row["department_id"])
    elif patient_id:
        rows = conn.execute("SELECT DISTINCT department_id FROM episodes WHERE patient_id=?", (patient_id,)).fetchall()
        for row in rows:
            targets.add(row["department_id"])
    return sorted(targets)


def historical_departments(conn, patient_id, encounter_id):
    return [row["department_id"] for row in conn.execute("SELECT DISTINCT department_id FROM episodes WHERE patient_id=? OR encounter_id=?", (patient_id, encounter_id)).fetchall()]


def clinical_targets(department_id, payload):
    targets = set()
    source = payload.get("source") or payload.get("source_department_id")
    if source in ENABLED_REQUEST_TYPES:
        targets.add(source)
    if department_id == "mdt":
        targets.add("icu")
    return targets


def resolve_symbolic_target_room(conn, requested_to_room_id, patient):
    if requested_to_room_id in {"source_icu_bed_room", "source_ward_room"}:
        room_id = retained_patient_bed_room(conn, patient["current_bed_id"], patient["patient_id"])
        return room_id or requested_to_room_id
    return requested_to_room_id


def retained_patient_bed_room(conn, bed_id, patient_id):
    if not bed_id:
        return None
    row = conn.execute(
        "SELECT room_id FROM beds WHERE bed_id=? AND patient_id=? AND status='occupied'",
        (bed_id, patient_id),
    ).fetchone()
    return row["room_id"] if row else None


def retained_patient_bed_id(conn, patient_id, bed_id, target_room_id):
    if not bed_id:
        return None
    row = conn.execute(
        "SELECT bed_id FROM beds WHERE bed_id=? AND room_id=? AND patient_id=? AND status='occupied'",
        (bed_id, target_room_id, patient_id),
    ).fetchone()
    return row["bed_id"] if row else None


def maybe_build_staff_visit_plan(conn, department_id, payload, patient):
    event_id = payload.get("event_id") or payload.get("eventId") or payload.get("event_type")
    if event_id not in {"WARD_NURSE_ORDER_VISIT", "WARD_DOCTOR_ROUND_VISIT"}:
        return {}
    if department_id != "ward":
        return {"error": "STAFF_VISIT_DEPARTMENT_MISMATCH", "message": "Ward staff visit events must be submitted by the ward handler."}
    staff_id = payload.get("staffId") or payload.get("staff_id")
    staff = find_standard_staff(staff_id)
    if not staff:
        return {"error": "STAFF_ID_NOT_STANDARD", "message": f"staffId must be a Fullview standard staff id, got {staff_id or 'empty'}."}
    role = staff.get("role") or staff.get("type")
    expected_role = "nurse" if event_id == "WARD_NURSE_ORDER_VISIT" else "doctor"
    if role != expected_role:
        return {"error": "STAFF_ROLE_MISMATCH", "message": f"{event_id} requires a {expected_role} staff member."}
    from_room_id = payload.get("fromRoomId") or payload.get("from_room_id") or default_staff_from_room(expected_role)
    to_room_id = payload.get("toRoomId") or payload.get("to_room_id") or patient["current_room_id"]
    return_room_id = payload.get("returnRoomId") or payload.get("return_room_id") or default_staff_from_room(expected_role)
    for field, room_id in {"fromRoomId": from_room_id, "toRoomId": to_room_id, "returnRoomId": return_room_id}.items():
        if not room_id or not str(room_id).startswith("R-") or not room_exists(conn, room_id):
            return {"error": "ROOM_NOT_FOUND", "message": f"{field} must be an existing Fullview room id."}
    duration = int(payload.get("durationSeconds") or payload.get("duration_seconds") or (8 if expected_role == "nurse" else 9))
    plan = {
        "kind": "staff-visit",
        "staffId": canonical_staff_id(staff),
        "fromRoomId": from_room_id,
        "toRoomId": to_room_id,
        "returnRoomId": return_room_id,
        "patientId": payload.get("patient_id"),
        "durationSeconds": duration,
        "reason": payload.get("reason") or ("nurse execute_immediate" if expected_role == "nurse" else "doctor ward round"),
    }
    return {"plan": plan, "snake_plan": to_snake_staff_plan(plan)}


def maybe_build_patient_escort_plan(conn, department_id, payload):
    staff_id = payload.get("staff_id") or payload.get("staffId")
    if not staff_id:
        return {}
    staff = find_standard_staff(staff_id)
    if not staff:
        return {"error": "STAFF_ID_NOT_STANDARD", "message": f"staff_id must be a Fullview standard staff id, got {staff_id}."}
    role = staff.get("role") or staff.get("type")
    if role == "porter":
        return {"porter_id": canonical_staff_id(staff), "porter_return": {"kind": "hallway"}}
    if department_id == "ward" and (payload.get("event_id") in {"WARD_TO_DIAGNOSTIC_MOVE", "WARD_DIAGNOSTIC_RETURN"}):
        return_room_id = "R-WARD-NURSE-STATION" if (staff.get("role") or staff.get("type")) == "nurse" else "R-WARD-DOCTOR-OFFICE"
    else:
        return_room_id = staff.get("roomId") or staff.get("room_id")
    if not return_room_id or not room_exists(conn, return_room_id):
        return_room_id = default_staff_from_room(staff.get("role") or staff.get("type"))
    return {"porter_id": canonical_staff_id(staff), "porter_return": room_return_point(conn, return_room_id)}


def validate_special_rule_source(conn, payload, patient, requested_to_room_id):
    event_id = payload.get("event_id")
    if event_id == "ICU_TO_MDT_CONSULT_MOVE":
        allowed_sources = {"R-ICU-BEDS-A", "R-ICU-BEDS-B", "R-ICU-ISOLATION"}
        allowed_targets = {"R-MDT-CALL", "R-MDT-MEETING"}
        source = patient["current_room_id"] or payload.get("from_room_id")
        if source not in allowed_sources:
            return {"code": "PATIENT_NOT_IN_ICU_BED", "message": "ICU_TO_MDT_CONSULT_MOVE requires the patient to be in an ICU bed room."}
        if requested_to_room_id not in allowed_targets:
            return {"code": "TARGET_NOT_ALLOWED", "message": "ICU_TO_MDT_CONSULT_MOVE target must be R-MDT-CALL or R-MDT-MEETING."}
    if event_id == "ICU_MDT_CONSULT_RETURN":
        allowed_sources = {"R-MDT-CALL", "R-MDT-MEETING"}
        retained_room = retained_patient_bed_room(conn, patient["current_bed_id"], patient["patient_id"])
        if patient["current_room_id"] not in allowed_sources:
            return {"code": "PATIENT_NOT_IN_MDT_CONSULT", "message": "ICU_MDT_CONSULT_RETURN requires the patient to be in an MDT consultation room."}
        if not retained_room:
            return {"code": "ICU_SOURCE_BED_NOT_RETAINED", "message": "The original ICU bed is not retained by this patient."}
        if requested_to_room_id != retained_room:
            return {"code": "TARGET_NOT_RETAINED_ICU_BED", "message": "Return target must be the patient's retained ICU bed room."}
    return None


def find_standard_staff(staff_id):
    if not staff_id:
        return None
    staff_id = str(staff_id)
    for member in load_staff_records():
        ids = {member.get("id"), member.get("staffId"), member.get("staff_id"), member.get("employeeId"), member.get("employee_id")}
        if staff_id in {item for item in ids if item}:
            return member
    return None


def canonical_staff_id(member):
    return member.get("staff_id") or member.get("employee_id") or member.get("employeeId") or member.get("staffId") or member.get("id")


def load_staff_records():
    path = DATA_DIR / "staff.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("staff", [])


def default_staff_from_room(role):
    return "R-WARD-NURSE-STATION" if role == "nurse" else "R-WARD-DOCTOR-OFFICE"


def room_return_point(conn, room_id):
    row = conn.execute("SELECT floor, map_json FROM locations WHERE room_id=?", (room_id,)).fetchone()
    if not row:
        return {"roomId": room_id, "floor": 5}
    spec = json_loads(row["map_json"])
    tile_x = float(spec.get("x") or 0) + float(spec.get("w") or 1) / 2
    tile_y = float(spec.get("y") or 0) + float(spec.get("h") or 1) / 2
    return {
        "roomId": room_id,
        "floor": row["floor"],
        "tileX": tile_x,
        "tileY": tile_y,
        "x": tile_x * 32,
        "y": tile_y * 32,
    }


def to_snake_staff_plan(plan):
    if not plan:
        return {}
    return {
        "kind": plan.get("kind"),
        "staff_id": plan.get("staffId") or plan.get("staff_id"),
        "from_room_id": plan.get("fromRoomId") or plan.get("from_room_id"),
        "to_room_id": plan.get("toRoomId") or plan.get("to_room_id"),
        "return_room_id": plan.get("returnRoomId") or plan.get("return_room_id"),
        "patient_id": plan.get("patientId") or plan.get("patient_id"),
        "duration_seconds": plan.get("durationSeconds") or plan.get("duration_seconds"),
        "reason": plan.get("reason"),
    }


def to_camel_staff_plan(plan):
    if not plan:
        return {}
    return {
        "kind": plan.get("kind"),
        "staffId": plan.get("staffId") or plan.get("staff_id"),
        "fromRoomId": plan.get("fromRoomId") or plan.get("from_room_id"),
        "toRoomId": plan.get("toRoomId") or plan.get("to_room_id"),
        "returnRoomId": plan.get("returnRoomId") or plan.get("return_room_id"),
        "patientId": plan.get("patientId") or plan.get("patient_id"),
        "durationSeconds": plan.get("durationSeconds") or plan.get("duration_seconds"),
        "reason": plan.get("reason"),
    }


def accepted_core_response(payload, event_seq, event_id, animation, status_updates, staff_move_plan=None):
    response = {
        "accepted": True,
        "event_seq": event_seq,
        "eventSeq": event_seq,
        "event_id": event_id,
        "eventId": event_id,
        "patient_id": payload.get("patient_id"),
        "patientId": payload.get("patient_id"),
        "message": "Accepted by Fullview Core.",
        "status_updates": status_updates,
        "statusUpdates": to_camel_dict(status_updates),
        "animation_plan": animation,
        "animationPlan": to_camel_animation(animation),
    }
    if staff_move_plan:
        response["staffMovePlan"] = staff_move_plan
        response["staff_move_plan"] = to_snake_staff_plan(staff_move_plan)
    return response


def rejected_core_response(payload, code, message, details=None):
    result = {
        "accepted": False,
        "event_id": payload.get("event_id"),
        "eventId": payload.get("event_id"),
        "patient_id": payload.get("patient_id"),
        "patientId": payload.get("patient_id"),
        "reasonCode": code,
        "message": message,
    }
    if details:
        result["details"] = details
    return result


def animation_plan(kind, from_room_id, to_room_id, payload, rule=None):
    movement = (rule or {}).get("movement") or {}
    return {
        "kind": kind,
        "transport": movement.get("transport", "walking"),
        "escort_roles": movement.get("escortRoles") or movement.get("escort_roles") or [],
        "equipment": movement.get("equipment") or [],
        "from_room_id": from_room_id,
        "to_room_id": to_room_id,
        "requested_to_room_id": payload.get("to_room_id"),
        "via_room_ids": movement.get("via") or [],
        "final_form": movement.get("finalForm") or movement.get("final_form") or "walking",
        "patient_form_during_move": movement.get("patientFormDuringMove") or movement.get("patient_form_during_move") or movement.get("transport", "walking"),
        "porter_id": payload.get("staff_id") or payload.get("staffId") or payload.get("porter_id") or payload.get("porterId"),
        "porter_return": payload.get("porter_return") or payload.get("porterReturn"),
    }


def to_camel_animation(plan):
    result = {
        "kind": plan.get("kind"),
        "transport": plan.get("transport"),
        "escortRoles": plan.get("escort_roles") or [],
        "equipment": plan.get("equipment") or [],
        "fromRoomId": plan.get("from_room_id"),
        "toRoomId": plan.get("to_room_id"),
        "requestedToRoomId": plan.get("requested_to_room_id"),
        "viaRoomIds": plan.get("via_room_ids") or [],
        "finalForm": plan.get("final_form"),
        "patientFormDuringMove": plan.get("patient_form_during_move"),
    }
    if plan.get("porter_id"):
        result["porterId"] = plan.get("porter_id")
    if plan.get("porter_return"):
        result["porterReturn"] = plan.get("porter_return")
    if plan.get("bed_id"):
        result["bedId"] = plan.get("bed_id")
    return result


def to_camel_dict(value):
    return {snake_to_camel(key): item for key, item in (value or {}).items()}


def snake_to_camel(value):
    bits = str(value).split("_")
    return bits[0] + "".join(bit[:1].upper() + bit[1:] for bit in bits[1:])


def assign_available_bed(conn, patient_id, encounter_id, room_id):
    row = conn.execute("SELECT bed_id FROM beds WHERE room_id=? AND status='available' ORDER BY bed_index LIMIT 1", (room_id,)).fetchone()
    if not row:
        return None
    bed_id = row["bed_id"]
    now = utc_now()
    conn.execute("UPDATE beds SET status='occupied', patient_id=?, updated_at=? WHERE bed_id=?", (patient_id, now, bed_id))
    conn.execute(
        """
        INSERT INTO bed_assignments (assignment_id, bed_id, room_id, patient_id, encounter_id, assigned_at, released_at, status)
        VALUES (?, ?, ?, ?, ?, ?, NULL, 'active')
        """,
        ("BA-" + uuid.uuid4().hex, bed_id, room_id, patient_id, encounter_id, now),
    )
    return bed_id


def release_patient_bed(conn, patient_id):
    now = utc_now()
    conn.execute("UPDATE beds SET status='available', patient_id=NULL, updated_at=? WHERE patient_id=?", (now, patient_id))
    conn.execute("UPDATE bed_assignments SET status='released', released_at=? WHERE patient_id=? AND released_at IS NULL", (now, patient_id))
    conn.execute("UPDATE patients SET current_bed_id=NULL WHERE patient_id=?", (patient_id,))


def resolve_target_room(conn, department_id, target_department_id, requested_to_room_id, final_form):
    if final_form == "hidden":
        return None
    if requested_to_room_id and requested_to_room_id != "exit":
        if final_form == "bed" and is_admission_room(conn, requested_to_room_id):
            allocated = first_available_bed_room(conn, target_department_id or department_id)
            return allocated
        return requested_to_room_id
    if final_form == "bed":
        return first_available_bed_room(conn, target_department_id or department_id)
    return default_room_for_department(target_department_id or department_id)


def is_admission_room(conn, room_id):
    row = conn.execute("SELECT kind FROM locations WHERE room_id=?", (room_id,)).fetchone()
    return bool(row and row["kind"] in {"registration", "icu_station"})


def first_available_bed_room(conn, department_id):
    row = conn.execute(
        """
        SELECT b.room_id
        FROM beds b JOIN locations l ON l.room_id=b.room_id
        WHERE b.status='available' AND l.department_id=? AND l.capacity_beds > 0
        ORDER BY l.floor, l.room_id, b.bed_index
        LIMIT 1
        """,
        (department_id,),
    ).fetchone()
    return row["room_id"] if row else None


def get_patient(conn, patient_id):
    return conn.execute("SELECT * FROM patients WHERE patient_id=?", (patient_id,)).fetchone()


def room_exists(conn, room_id):
    return bool(room_id and conn.execute("SELECT 1 FROM locations WHERE room_id=?", (room_id,)).fetchone())


def room_row(conn, room_id):
    if not room_id:
        return None
    return conn.execute("SELECT * FROM locations WHERE room_id=?", (room_id,)).fetchone()


def room_map_json(row):
    return json_loads(row["map_json"]) if row else {}


def movement_room_values(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def validate_rule_room_scope(conn, rule, payload, patient, from_room_id, requested_to_room_id):
    movement = rule.get("movement") or {}
    if from_room_id and from_room_id != "outside" and not rule_room_allowed(conn, movement.get("from"), from_room_id, patient, "from"):
        return {
            "code": "SOURCE_NOT_ALLOWED",
            "message": f"{from_room_id} is not an allowed source for {payload.get('event_id')}.",
            "details": {"allowedSourceRoomIds": movement_room_values(movement.get("from"))},
        }
    if requested_to_room_id and requested_to_room_id != "exit" and not rule_room_allowed(conn, movement.get("to"), requested_to_room_id, patient, "to"):
        return {
            "code": "TARGET_NOT_ALLOWED",
            "message": f"{requested_to_room_id} is not an allowed target for {payload.get('event_id')}.",
            "details": {"allowedTargetRoomIds": movement_room_values(movement.get("to"))},
        }
    return None


def rule_room_allowed(conn, value, room_id, patient, direction):
    values = movement_room_values(value)
    if not values:
        return True
    if room_id in values:
        return True
    if "current_room" in values and room_id == patient["current_room_id"]:
        return True
    if "current_consult_room" in values and is_outpatient_limited_target(conn, room_id):
        return True
    if direction == "to" and any(str(item).startswith("source_") for item in values):
        retained_room = retained_patient_bed_room(conn, patient["current_bed_id"], patient["patient_id"])
        if retained_room and retained_room == room_id:
            return True
    return False


def final_form_for_target(conn, department_id, target_room_id, final_form):
    row = room_row(conn, target_room_id)
    if not row or department_id != "outpatient":
        return final_form
    if row["capacity_beds"] > 0 and room_map_json(row).get("department_group") == "surgery":
        return "bed"
    return final_form


def validate_outpatient_room_resource(conn, department_id, payload, patient, from_room_id, target_room_id):
    if department_id != "outpatient" or not target_room_id:
        return None
    event_id = payload.get("event_id")
    if event_id == "OP_CURRENT_TO_TARGET_DOOR_QUEUE":
        targets = queue_targets(conn, target_room_id)
        if not targets:
            return {"code": "TARGET_NOT_ALLOWED", "message": f"{target_room_id} is not an outpatient door queue."}
        if any(outpatient_target_available(conn, room_id, patient["patient_id"]) for room_id in targets):
            return {
                "code": "TARGET_STILL_AVAILABLE",
                "message": "A matching target room still has a free slot or bed; do not queue this patient yet.",
                "details": {"queueFor": targets},
            }
        return None
    if event_id == "OP_TARGET_DOOR_QUEUE_ADVANCE":
        if from_room_id != patient["current_room_id"]:
            return {"code": "PATIENT_NOT_IN_MATCHING_QUEUE", "message": "Patient is not currently in the submitted queue room."}
        targets = queue_targets(conn, from_room_id)
        if target_room_id not in targets:
            return {
                "code": "PATIENT_NOT_IN_MATCHING_QUEUE",
                "message": f"{target_room_id} is not served by queue {from_room_id}.",
                "details": {"queueFor": targets},
            }
        if not outpatient_target_available(conn, target_room_id, patient["patient_id"]):
            return {"code": "OUTPATIENT_SLOT_UNAVAILABLE", "message": f"No free outpatient slot or bed in {target_room_id}."}
        return None
    if is_outpatient_queue(conn, target_room_id):
        return None
    if is_outpatient_limited_target(conn, target_room_id) and not outpatient_target_available(conn, target_room_id, patient["patient_id"]):
        return {"code": "OUTPATIENT_SLOT_UNAVAILABLE", "message": f"No free outpatient slot or bed in {target_room_id}."}
    return None


def is_outpatient_queue(conn, room_id):
    row = room_row(conn, room_id)
    spec = room_map_json(row)
    return bool(row and row["department_id"] == "outpatient" and (spec.get("queueAnchor") or spec.get("queue_anchor")))


def queue_targets(conn, queue_room_id):
    row = room_row(conn, queue_room_id)
    spec = room_map_json(row)
    values = spec.get("queueFor") or spec.get("queue_for") or []
    return [item for item in values if room_exists(conn, item)]


def is_outpatient_limited_target(conn, room_id):
    row = room_row(conn, room_id)
    if not row or row["department_id"] != "outpatient":
        return False
    if is_outpatient_queue(conn, room_id):
        return False
    return row["capacity_beds"] > 0 or consult_slot_count(row) > 0


def consult_slot_count(row):
    spec = room_map_json(row)
    explicit = spec.get("consultSlots") if spec.get("consultSlots") is not None else spec.get("consult_slots")
    if explicit is not None:
        return max(0, int(explicit))
    kind = row["kind"]
    if kind not in {"consultation", "internal_medicine", "surgery", "pediatrics", "fever", "obgyn", "lab", "surgery_procedure"}:
        return 0
    items = spec.get("items") or []
    count = sum(1 for item in items if item.get("type") in {"desk", "screen"})
    return max(1, count)


def outpatient_target_available(conn, room_id, patient_id=None):
    row = room_row(conn, room_id)
    if not row:
        return False
    if row["capacity_beds"] > 0:
        available = conn.execute("SELECT 1 FROM beds WHERE room_id=? AND status='available' LIMIT 1", (room_id,)).fetchone()
        retained = patient_id and conn.execute("SELECT 1 FROM beds WHERE room_id=? AND patient_id=? AND status='occupied' LIMIT 1", (room_id, patient_id)).fetchone()
        return bool(available or retained)
    slots = consult_slot_count(row)
    if slots <= 0:
        return True
    occupied = conn.execute(
        """
        SELECT COUNT(*)
        FROM patients
        WHERE current_room_id=?
          AND status NOT IN ('DISCHARGED', 'DELETED')
          AND (? IS NULL OR patient_id<>?)
        """,
        (room_id, patient_id, patient_id),
    ).fetchone()[0]
    return occupied < slots


def department_for_room(conn, room_id):
    if not room_id:
        return None
    row = conn.execute("SELECT department_id FROM locations WHERE room_id=?", (room_id,)).fetchone()
    return row["department_id"] if row else None


def default_room_for_department(department_id):
    return {
        "outpatient": "R-OP-REGISTRATION",
        "emergency": "R-ED-ENTRANCE",
        "icu": "R-ICU-ADMISSION",
        "mdt": "R-MDT-LOUNGE",
        "ward": "R-WARD-WARD-ADMISSION",
    }.get(department_id, "R-OP-REGISTRATION")


def rules_for_department(department_id):
    if department_id == "mdt":
        return {"movement_request": [], "transfer_request": [], "discharge_request": [], "clinical_event": []}
    department_rules = rules_in_category(RULE_CATEGORY_BY_DEPARTMENT.get(department_id))
    transfer_rules = [rule for rule in rules_in_category("transfer") if transfer_source_department(rule) == department_id]
    transfer_rules += [rule for rule in department_rules if rule_kind(rule) == "transfer"]
    return {
        "movement_request": [rule_summary(rule, department_id) for rule in department_rules if rule_kind(rule) == "movement"],
        "transfer_request": [rule_summary(rule, "transfer") for rule in transfer_rules],
        "discharge_request": [rule_summary(rule, department_id) for rule in department_rules if rule_kind(rule) == "discharge"],
        "clinical_event": [rule_summary(rule, department_id) for rule in department_rules if rule_kind(rule) == "clinical_event"],
    }


def rules_in_category(category_id):
    if not category_id:
        return []
    path = FULL_VIEW_ROOT / "event-rules" / f"{category_id}.json"
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8")).get("rules", [])


def all_rules():
    rules = []
    for path in sorted((FULL_VIEW_ROOT / "event-rules").glob("*.json")):
        if path.name == "index.json":
            continue
        rules.extend(json.loads(path.read_text(encoding="utf-8")).get("rules", []))
    return rules


def find_rule(event_id):
    if not event_id:
        return None
    return next((rule for rule in all_rules() if rule.get("eventId") == event_id or rule.get("event_id") == event_id), None)


def rule_summary(rule, category_id):
    movement = rule.get("movement") or {}
    return {
        "eventId": rule.get("eventId") or rule.get("event_id"),
        "event_id": rule.get("eventId") or rule.get("event_id"),
        "name": rule.get("name", ""),
        "classification": rule.get("classification", ""),
        "categoryId": category_id,
        "from": movement.get("from"),
        "to": movement.get("to"),
        "via": movement.get("via", []),
        "transport": movement.get("transport", "walking"),
        "movementSchema": movement.get("schema"),
        "staffRole": movement.get("staffRole") or movement.get("staff_role"),
        "durationSeconds": movement.get("durationSeconds") or movement.get("duration_seconds"),
        "finalForm": movement.get("finalForm") or movement.get("final_form", "walking"),
        "rooms": rule.get("rooms", []),
        "trigger": rule.get("trigger", ""),
        "prechecks": rule.get("prechecks", ""),
        "blocking": rule.get("blocking", ""),
    }


def rule_kind(rule):
    movement = rule.get("movement") or {}
    if movement.get("schema") == "staff-visit":
        return "clinical_event"
    target = movement.get("to")
    classification = str(rule.get("classification") or "")
    if target == "exit" or "出院" in classification or "离院" in classification or "EXIT" in (rule.get("eventId") or ""):
        return "discharge"
    if "跨部门" in classification or "TRANSFER_" in (rule.get("eventId") or "") or (rule.get("eventId") or "").endswith("_TO_WARD") or (rule.get("eventId") or "").endswith("_TO_ICU"):
        return "transfer"
    return "movement"


def transfer_source_department(rule):
    event_id = rule.get("eventId") or ""
    if event_id.startswith("TRANSFER_ED_"):
        return "emergency"
    if event_id.startswith("TRANSFER_OP_"):
        return "outpatient"
    if event_id.startswith("TRANSFER_ICU_"):
        return "icu"
    if event_id.startswith("TRANSFER_WARD_"):
        return "ward"
    return None


def ensure_rule_allowed(department_id, request_type, event_id):
    allowed = {rule["eventId"] for rule in rules_for_department(department_id).get(request_type, []) if rule.get("eventId")}
    if not event_id:
        return {"code": "MISSING_EVENT_ID", "message": "event_id is required.", "details": {"allowedEventIds": sorted(allowed)}}
    if event_id not in allowed:
        return {"code": "RULE_NOT_ALLOWED_FOR_DEPARTMENT", "message": f"{event_id} is not allowed for {department_id} {request_type}.", "details": {"allowedEventIds": sorted(allowed)}}
    return None


def default_transfer_event_id(department_id, to_department_id):
    return {
        ("emergency", "icu"): "TRANSFER_ED_TO_ICU",
        ("emergency", "ward"): "TRANSFER_ED_TO_WARD",
        ("outpatient", "ward"): "TRANSFER_OP_TO_WARD",
        ("outpatient", "emergency"): "TRANSFER_OP_TO_ED",
        ("icu", "ward"): "TRANSFER_ICU_TO_WARD",
        ("ward", "icu"): "TRANSFER_WARD_TO_ICU",
    }.get((department_id, to_department_id))


def discharge_event_id_for_department(department_id):
    return {"icu": "ICU_PATIENT_EXIT_HOSPITAL", "ward": "WARD_DISCHARGE_EXIT_HOSPITAL", "outpatient": "OP_PATIENT_EXIT_HOSPITAL", "emergency": "ED_PATIENT_EXIT_HOSPITAL"}.get(department_id)


def first_rule_for_request(department_id, request_type):
    rules = rules_for_department(department_id).get(request_type, [])
    preferred = {
        ("outpatient", "movement_request"): "OP_TRIAGE_TO_SPECIALTY_CONSULT",
        ("icu", "movement_request"): "ICU_TO_MDT_CONSULT_MOVE",
        ("ward", "movement_request"): "WARD_TO_DIAGNOSTIC_MOVE",
    }.get((department_id, request_type))
    if preferred:
        selected = next((rule for rule in rules if rule.get("eventId") == preferred), None)
        if selected:
            return find_rule(selected["eventId"])
    return find_rule(rules[0]["eventId"]) if rules else None


def concrete_rule_value(value, fallback):
    values = value if isinstance(value, list) else [value]
    for item in values:
        if isinstance(item, str) and item.startswith("R-"):
            return item
    return fallback


def movement_example_for(department_id, patient_id, encounter_id):
    rule = first_rule_for_request(department_id, "movement_request")
    movement = rule.get("movement") if rule else {}
    example = {
        "patient_id": patient_id,
        "encounter_id": encounter_id,
        "event_id": (rule or {}).get("eventId"),
        "from_room_id": concrete_rule_value(movement.get("from"), default_room_for_department(department_id)),
        "to_room_id": concrete_rule_value(movement.get("to"), default_room_for_department(department_id)),
        "reason": "dashboard movement debug",
    }
    if department_id == "icu" and example["event_id"] == "ICU_TO_MDT_CONSULT_MOVE":
        example["from_room_id"] = "R-ICU-BEDS-A"
        example["to_room_id"] = "R-MDT-CALL"
        example["reason"] = "ICU requests MDT consultation"
    if department_id == "ward" and example["event_id"] == "WARD_TO_DIAGNOSTIC_MOVE":
        example["from_room_id"] = "R-WARD-CARD"
        example["to_room_id"] = "R-WARD-DIAGNOSTIC-CENTER"
        example["staff_id"] = "NURSE_RESP_01"
        example["reason"] = "nurse escorts patient to diagnostic center"
    if department_id == "outpatient" and example["event_id"] == "OP_TRIAGE_TO_SPECIALTY_CONSULT":
        example["from_room_id"] = "R-OP-TRIAGE"
        example["to_room_id"] = "R-OP-INTERNAL"
        example["reason"] = "triage sends patient to internal consult slot"
        example["additional_examples"] = {
            "door_queue_when_internal_full": {
                "patient_id": patient_id,
                "encounter_id": encounter_id,
                "event_id": "OP_CURRENT_TO_TARGET_DOOR_QUEUE",
                "from_room_id": "R-OP-TRIAGE",
                "to_room_id": "R-OP-QUEUE-INTERNAL",
                "reason": "internal consult slots are full; wait at internal door queue",
            },
            "queue_advance_to_internal": {
                "patient_id": patient_id,
                "encounter_id": encounter_id,
                "event_id": "OP_TARGET_DOOR_QUEUE_ADVANCE",
                "from_room_id": "R-OP-QUEUE-INTERNAL",
                "to_room_id": "R-OP-INTERNAL",
                "reason": "internal consult slot is now available",
            },
            "surgery_procedure": {
                "patient_id": patient_id,
                "encounter_id": encounter_id,
                "event_id": "OP_TRIAGE_TO_SPECIALTY_CONSULT",
                "from_room_id": "R-OP-TRIAGE",
                "to_room_id": "R-OP-SURGERY-PROCEDURE",
                "reason": "surgery sends patient to outpatient procedure room",
            },
        }
    return example


def target_department_for_transfer_event(event_id):
    return {
        "TRANSFER_ED_TO_ICU": "icu",
        "TRANSFER_ED_TO_WARD": "ward",
        "TRANSFER_OP_TO_ED": "emergency",
        "TRANSFER_OP_TO_WARD": "ward",
        "TRANSFER_ICU_TO_WARD": "ward",
        "TRANSFER_WARD_TO_ICU": "icu",
        "OP_TO_WARD_MOVE": "ward",
        "OP_TO_ICU_MOVE": "icu",
        "ED_TO_ICU_MOVE": "icu",
        "ED_TO_WARD_MOVE": "ward",
        "ICU_TO_WARD_MOVE": "ward",
        "WARD_TO_ICU_MOVE": "icu",
    }.get(event_id)


def transfer_example_for(department_id, patient_id, encounter_id):
    rule = first_rule_for_request(department_id, "transfer_request")
    event_id = (rule or {}).get("eventId") or default_transfer_event_id(department_id, "ward")
    movement = (rule or {}).get("movement") or {}
    target = target_department_for_transfer_event(event_id) or "ward"
    return {
        "patient_id": patient_id,
        "encounter_id": encounter_id,
        "event_id": event_id,
        "from_room_id": concrete_rule_value(movement.get("from"), default_room_for_department(department_id)),
        "to_room_id": concrete_rule_value(movement.get("to"), default_room_for_department(target)),
        "to_department_id": target,
        "reason": "needs coordinated care",
        "ctas_level": "L2",
        "summary": {"chief_complaint": "dashboard transfer debug", "key_findings": ["requires monitored bed"]},
        "requested_resources": {"bed_type": target.upper(), "monitor": target == "icu"},
    }


def clinical_example_for(department_id, patient_id, encounter_id):
    if department_id == "mdt":
        return {
            "patient_id": patient_id,
            "encounter_id": encounter_id,
            "event_type": "mdt.consultation_completed",
            "consultation_id": "MDT-20260612-001",
            "summary": {"case_summary": "MDT reviewed the debug case."},
            "recommendations": ["continue monitoring", "repeat imaging if symptoms worsen"],
            "required_updates": [],
        }
    if department_id == "ward":
        return {
            "patient_id": patient_id,
            "encounter_id": encounter_id,
            "event_type": "WARD_NURSE_ORDER_VISIT",
            "event_id": "WARD_NURSE_ORDER_VISIT",
            "staffId": "NURSE_RESP_01",
            "fromRoomId": "R-WARD-NURSE-STATION",
            "toRoomId": "R-WARD-RESP",
            "returnRoomId": "R-WARD-NURSE-STATION",
            "durationSeconds": 8,
            "reason": "nurse execute_immediate",
            "summary": {"note": "ward nurse order visit debug"},
            "additional_examples": {
                "doctor_round": {
                    "patient_id": patient_id,
                    "encounter_id": encounter_id,
                    "event_type": "WARD_DOCTOR_ROUND_VISIT",
                    "event_id": "WARD_DOCTOR_ROUND_VISIT",
                    "staffId": "DOCTOR_RESP_01",
                    "fromRoomId": "R-WARD-DOCTOR-OFFICE",
                    "toRoomId": "R-WARD-RESP",
                    "returnRoomId": "R-WARD-DOCTOR-OFFICE",
                    "durationSeconds": 9,
                    "reason": "doctor ward round",
                    "summary": {"note": "ward doctor round debug"},
                }
            },
        }
    return {"patient_id": patient_id, "encounter_id": encounter_id, "event_type": "clinical.summary_updated", "summary": {"note": f"{department_id} debug clinical update"}}
