from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import sys
import uuid
from urllib.parse import parse_qs, unquote, urlparse


ROOT = Path(__file__).resolve().parent
MAP_CONFIG = ROOT / "map-config.json"
RULES_DIR = ROOT.parent / "rules" / "event-rules"
BACKEND_DATA = ROOT / "backend-data"
PATIENTS_FILE = BACKEND_DATA / "patients.json"
STAFF_FILE = BACKEND_DATA / "staff.json"
ROOM_STATE_FILE = BACKEND_DATA / "room-state.json"
EVENT_LOG_FILE = BACKEND_DATA / "event-log.json"
DEPARTMENT_REQUESTS_FILE = BACKEND_DATA / "department-requests.json"
IDEMPOTENCY_FILE = BACKEND_DATA / "idempotency-keys.json"
CARE_ROOM_KINDS = {"icu", "ward"}
CONSULT_ROOM_KINDS = {"consultation", "internal_medicine", "surgery", "pediatrics", "fever", "obgyn"}
TILE_SIZE = 32
FLOOR_DEPARTMENTS = {
    1: "emergency",
    2: "outpatient",
    3: "icu",
    4: "mdt",
    5: "ward",
}
ROOM_DEPARTMENT_BY_KIND = {
    "lab": "laboratory",
    "pharmacy": "pharmacy",
    "imaging_review": "mdt",
}
DEPARTMENT_DISPLAY = {
    "emergency": "Emergency",
    "outpatient": "Outpatient",
    "laboratory": "Laboratory",
    "pharmacy": "Pharmacy",
    "icu": "ICU",
    "ward": "Ward",
    "mdt": "MDT Center",
    "hospital": "Hospital",
}
DEPARTMENT_ORDER = ["outpatient", "emergency", "icu", "mdt", "ward"]
DEPARTMENT_PRODUCERS = {
    "outpatient": "groupA.outpatient",
    "emergency": "groupB.ed",
    "icu": "groupC.icu",
    "mdt": "groupM.mdt",
    "ward": "groupD.inpatient",
}
REQUEST_TYPES = [
    "patient_upsert",
    "encounter_open",
    "movement_request",
    "transfer_request",
    "discharge_request",
    "clinical_event",
]


class HospitalViewHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        route = parsed.path
        query = parse_qs(parsed.query)

        if route == "/api/hospital/snapshot":
            self.send_json(build_snapshot())
            return
        if route == "/api/hospital/rooms":
            self.send_json({"rooms": build_snapshot()["rooms"]})
            return
        if route == "/api/hospital/people":
            snapshot = build_snapshot()
            self.send_json({"patients": snapshot["patients"], "staff": snapshot["staff"]})
            return
        if route == "/api/hospital/events":
            after = int(first_query_value(query, "after", "0") or "0")
            events = read_json(EVENT_LOG_FILE).get("events", [])
            self.send_json({"events": [event for event in events if event.get("eventSeq", 0) > after]})
            return
        if route == "/api/v1/departments":
            self.send_json({"departments": list_departments()})
            return
        if route == "/api/v1/debug/scenarios/closed-loop":
            self.send_json(api_ok(build_closed_loop_debug_scenario()))
            return
        if route.startswith("/api/v1/departments/"):
            response = handle_department_get(route)
            if response is None:
                self.send_error(404, "Unknown department API endpoint")
                return
            self.send_json(response)
            return
        if route == "/api/event-rules":
            self.send_json(read_json(RULES_DIR / "index.json"))
            return
        if route.startswith("/api/event-rules/"):
            target = safe_rule_file(route.removeprefix("/api/event-rules/"))
            if not target.exists():
                self.send_error(404, "Rule file not found")
                return
            self.send_json(read_json(target))
            return

        super().do_GET()

    def do_POST(self):
        route = self.path.split("?", 1)[0]
        if route == "/api/hospital/events/move":
            body = self.read_json_body()
            if body is None:
                return
            self.send_json(handle_move_request(body))
            return
        if route == "/api/hospital/patients/admit":
            body = self.read_json_body()
            if body is None:
                return
            self.send_json(handle_admit_patient(body))
            return
        if route.startswith("/api/v1/departments/"):
            body = self.read_json_body()
            if body is None:
                return
            idempotency_key = self.headers.get("Idempotency-Key", "")
            response = handle_department_post(route, body, idempotency_key)
            if response is None:
                self.send_error(404, "Unknown department API endpoint")
                return
            self.send_json(response)
            return
        self.send_error(404, "Unknown API endpoint")

    def do_DELETE(self):
        route = self.path.split("?", 1)[0]
        if route.startswith("/api/hospital/patients/"):
            patient_id = unquote(route.removeprefix("/api/hospital/patients/"))
            self.send_json(handle_delete_patient(patient_id))
            return
        self.send_error(404, "Unknown API endpoint")

    def do_PUT(self):
        route = self.path.split("?", 1)[0]
        if route == "/api/map-config":
            self.save_json(MAP_CONFIG)
            return
        if route.startswith("/api/event-rules/"):
            target = safe_rule_file(route.removeprefix("/api/event-rules/"))
            self.save_rule_json(target)
            return
        self.send_error(404, "Unknown API endpoint")

    def read_json_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as error:
            self.send_error(400, f"Invalid JSON: {error}")
            return None

    def save_json(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix != ".json":
            self.send_error(404, "Unknown API endpoint")
            return

        data = self.read_json_body()
        if data is None:
            return

        write_json(path, data)
        self.send_json({"ok": True})

    def save_rule_json(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix != ".json":
            self.send_error(404, "Unknown API endpoint")
            return

        data = self.read_json_body()
        if data is None:
            return

        write_json(path, data)
        mirror = ROOT / "event-rules" / path.name
        if mirror.parent.exists():
            write_json(mirror, data)
        refresh_rule_index()
        mirror_rule_index()
        self.send_json({"ok": True})

    def send_json(self, data):
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def new_event_id():
    return "evt_" + uuid.uuid4().hex[:26].upper()


def new_trace_id():
    return "trc_" + uuid.uuid4().hex[:26]


def list_departments():
    return [department_summary(department_id) for department_id in DEPARTMENT_ORDER]


def department_summary(department_id):
    meta = department_meta(department_id)
    return {
        "id": department_id,
        "label": meta["label"],
        "producer": DEPARTMENT_PRODUCERS[department_id],
        "enabledRequestTypes": meta["enabled_request_types"],
        "dashboardPath": f"/department-dashboard.html#{department_id}",
    }


def department_meta(department_id):
    labels = {
        "outpatient": "Outpatient",
        "emergency": "Emergency",
        "icu": "ICU",
        "mdt": "MDT",
        "ward": "Ward",
    }
    enabled = {
        "outpatient": ["patient_upsert", "encounter_open", "movement_request", "transfer_request", "clinical_event"],
        "emergency": ["patient_upsert", "encounter_open", "movement_request", "transfer_request", "clinical_event"],
        "icu": ["patient_upsert", "encounter_open", "movement_request", "transfer_request", "discharge_request", "clinical_event"],
        "mdt": ["patient_upsert", "encounter_open", "clinical_event"],
        "ward": ["patient_upsert", "encounter_open", "movement_request", "transfer_request", "discharge_request", "clinical_event"],
    }
    if department_id not in enabled:
        return None
    return {
        "id": department_id,
        "label": labels[department_id],
        "producer": DEPARTMENT_PRODUCERS[department_id],
        "enabled_request_types": enabled[department_id],
    }


def handle_department_get(route):
    parts = route.strip("/").split("/")
    if len(parts) < 5 or parts[:3] != ["api", "v1", "departments"]:
        return None
    department_id = parts[3]
    meta = department_meta(department_id)
    if not meta:
        return api_error("DEPARTMENT_NOT_FOUND", f"Unknown department: {department_id}")
    resource = parts[4]
    if resource == "capabilities":
        return api_ok(department_capabilities(department_id))
    if resource == "schemas":
        return api_ok({key: request_schema(key) for key in meta["enabled_request_types"]})
    if resource == "examples":
        return api_ok(department_examples(department_id))
    if resource == "requests" and len(parts) >= 6 and parts[5] == "recent":
        return api_ok({"requests": recent_department_requests(department_id)})
    return None


def handle_department_post(route, body, idempotency_key):
    parts = route.strip("/").split("/")
    if len(parts) < 6 or parts[:3] != ["api", "v1", "departments"]:
        return None
    department_id = parts[3]
    route_kind = parts[4]
    request_type = parts[5]
    if route_kind not in {"requests", "playground"}:
        return None
    return handle_department_request(department_id, request_type, body, idempotency_key)


def department_capabilities(department_id):
    meta = department_meta(department_id)
    rules = rules_for_department(department_id)
    return {
        **department_summary(department_id),
        "architecture": "Department Handler -> Fullview Core -> backend-data/event-log -> Map/Console/Dashboard",
        "requestTypes": [
            {
                "id": request_type,
                "label": request_type.replace("_", " ").title(),
                "description": request_type_description(request_type, department_id),
                "method": "POST",
                "path": f"/api/v1/departments/{department_id}/requests/{request_type}",
                "playgroundPath": f"/api/v1/departments/{department_id}/playground/{request_type}",
                "enabled": request_type in meta["enabled_request_types"],
                "allowedRules": rules.get(request_type, []),
            }
            for request_type in meta["enabled_request_types"]
        ],
        "rulesSource": {
            "index": "/api/event-rules",
            "categories": sorted({rule["categoryId"] for group in rules.values() for rule in group}),
        },
        "errorCodes": [
            "DEPARTMENT_NOT_FOUND",
            "REQUEST_TYPE_NOT_ENABLED",
            "MISSING_PATIENT_ID",
            "MISSING_ENCOUNTER_ID",
            "MISSING_EVENT_ID",
            "RULE_NOT_ALLOWED_FOR_DEPARTMENT",
            "PATIENT_NOT_FOUND",
            "TARGET_ROOM_NOT_FOUND",
            "NO_BED_AVAILABLE",
            "ICU_BED_UNAVAILABLE",
            "WARD_BED_UNAVAILABLE",
            "MOVEMENT_RULE_REJECTED",
        ],
    }


def request_type_description(request_type, department_id):
    descriptions = {
        "patient_upsert": "Create or refresh the hospital-wide patient profile before clinical actions.",
        "encounter_open": "Open or refresh an encounter and link it to this department handler.",
        "movement_request": "Ask Fullview Core to move a patient by an existing movement rule.",
        "transfer_request": "Ask Fullview Core to coordinate a cross-department transfer.",
        "discharge_request": "Ask Fullview Core to discharge a patient and release owned resources.",
        "clinical_event": "Submit a clinical fact, consultation note, or department summary without moving the patient.",
    }
    if department_id == "mdt" and request_type == "clinical_event":
        return "Submit MDT consultation requests/results; this handler does not directly control beds or patient movement."
    return descriptions.get(request_type, request_type)


def rules_for_department(department_id):
    if department_id == "mdt":
        return {"movement_request": [], "transfer_request": [], "discharge_request": [], "clinical_event": []}
    department_rules = movement_rules_for_category(department_id)
    transfer_rule_entries = [
        ("transfer", rule)
        for rule in transfer_rules_for_department(department_id)
    ] + [
        (department_id, rule)
        for rule in department_rules
        if rule_kind(rule) == "transfer"
    ]
    return {
        "movement_request": [
            rule_summary(rule, department_id)
            for rule in department_rules
            if rule_kind(rule) == "movement"
        ],
        "transfer_request": [
            rule_summary(rule, category_id)
            for category_id, rule in transfer_rule_entries
        ],
        "discharge_request": [
            rule_summary(rule, department_id)
            for rule in department_rules
            if rule_kind(rule) == "discharge"
        ],
        "clinical_event": [
            rule_summary(rule, department_id)
            for rule in department_rules
            if rule_kind(rule) == "clinical_event"
        ],
    }


def movement_rules_for_category(category_id):
    rules_path = category_rule_path(category_id)
    if not rules_path:
        return []
    return read_json(rules_path).get("rules", [])


def transfer_rules_for_department(department_id):
    return [
        rule for rule in movement_rules_for_category("transfer")
        if transfer_source_department_for_rule(rule) == department_id
    ]


def category_rule_path(category_id):
    index = read_json(RULES_DIR / "index.json")
    for category in index.get("categories", []):
        if category.get("id") == category_id:
            path = RULES_DIR / category.get("file", "")
            return path if path.exists() else None
    return None


def rule_event_id(rule):
    return rule.get("eventId") or rule.get("event_id") or ""


def rule_kind(rule):
    movement = rule.get("movement", {})
    if movement.get("schema") == "staff-visit":
        return "clinical_event"
    target = movement.get("to")
    classification = str(rule.get("classification") or "")
    if target == "exit" or "离院" in classification or "出院" in rule.get("name", ""):
        return "discharge"
    if "跨部门" in classification:
        return "transfer"
    return "movement"


def rule_summary(rule, category_id):
    movement = rule.get("movement", {})
    return {
        "eventId": rule_event_id(rule),
        "event_id": rule_event_id(rule),
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


def first_rule_for_request(department_id, request_type):
    rules = rules_for_department(department_id).get(request_type, [])
    if not rules:
        return None
    preferred = {
        ("outpatient", "movement_request"): "OP_CONSULT_TO_PAYMENT",
        ("emergency", "movement_request"): "ED_TO_DIAGNOSTIC_MOVE",
        ("icu", "movement_request"): "ICU_TO_EXAM_OR_INTERVENTION",
        ("ward", "movement_request"): "WARD_TO_DIAGNOSTIC_MOVE",
        ("outpatient", "transfer_request"): "TRANSFER_OP_TO_WARD",
        ("emergency", "transfer_request"): "TRANSFER_ED_TO_ICU",
        ("icu", "transfer_request"): "TRANSFER_ICU_TO_WARD",
        ("ward", "transfer_request"): "TRANSFER_WARD_TO_ICU",
    }.get((department_id, request_type))
    selected = next((rule for rule in rules if rule.get("eventId") == preferred), rules[0])
    event_id = selected.get("eventId")
    return find_rule(event_id) if event_id else None


def allowed_event_ids_for_request(department_id, request_type):
    return {
        rule["eventId"]
        for rule in rules_for_department(department_id).get(request_type, [])
        if rule.get("eventId")
    }


def ensure_rule_allowed_for_department(department_id, request_type, event_id):
    allowed = allowed_event_ids_for_request(department_id, request_type)
    if not event_id:
        return {"accepted": False, "reasonCode": "MISSING_EVENT_ID", "message": "event_id is required."}
    if event_id not in allowed:
        return {
            "accepted": False,
            "reasonCode": "RULE_NOT_ALLOWED_FOR_DEPARTMENT",
            "message": f"{event_id} is not allowed for {department_id} {request_type}.",
            "allowedEventIds": sorted(allowed),
        }
    return None


def transfer_source_department_for_rule(rule):
    event_id = rule_event_id(rule)
    if event_id.startswith("TRANSFER_ED_"):
        return "emergency"
    if event_id.startswith("TRANSFER_OP_"):
        return "outpatient"
    if event_id.startswith("TRANSFER_ICU_"):
        return "icu"
    if event_id.startswith("TRANSFER_WARD_"):
        return "ward"
    movement = rule.get("movement", {})
    return source_department_for_rule_value(movement.get("from"))


def target_department_for_transfer_rule(rule):
    if not rule:
        return None
    event_id = rule_event_id(rule)
    route_targets = {
        "TRANSFER_ED_TO_ICU": "icu",
        "TRANSFER_ED_TO_WARD": "ward",
        "TRANSFER_OP_TO_ED": "emergency",
        "TRANSFER_OP_TO_WARD": "ward",
        "TRANSFER_ICU_TO_WARD": "ward",
        "TRANSFER_WARD_TO_ICU": "icu",
    }
    if event_id in route_targets:
        return route_targets[event_id]
    return target_department_for_rule_value(rule.get("movement", {}).get("to"))


def source_department_for_rule_value(value):
    values = value if isinstance(value, list) else [value]
    for item in values:
        if item in {"current_ed_room", "current_ed_bed_room"} or str(item).startswith("ed_"):
            return "emergency"
        if item == "current_op_room" or str(item).endswith("_2") or item == "outpatient_waiting":
            return "outpatient"
        if item in {"current_icu_bed_room", "source_icu_bed_room", "current_icu_exam_room"} or str(item).startswith("icu_"):
            return "icu"
        if item in {"current_ward_room", "source_ward_room", "target_ward_room"} or "ward" in str(item):
            return "ward"
    return None


def target_department_for_rule_value(value):
    values = value if isinstance(value, list) else [value]
    for item in values:
        if item in {"icu_admission", "current_icu_bed_room", "source_icu_bed_room"} or str(item).startswith("icu_"):
            return "icu"
        if item in {"ward_admission", "target_ward_room", "source_ward_room"} or "ward" in str(item):
            return "ward"
        if str(item).startswith("ed_"):
            return "emergency"
        if str(item).endswith("_2") or item == "outpatient_waiting":
            return "outpatient"
    return None


def example_room_for_rule_value(value, department_id, direction):
    values = value if isinstance(value, list) else [value]
    for item in values:
        if isinstance(item, str) and item and not is_symbolic_room(item) and item != "exit":
            return item
    fallback = {
        "outpatient": {"from": "consultation_b_2", "to": "payment_2"},
        "emergency": {"from": "ed_minor", "to": "ed_diagnostic"},
        "icu": {"from": "icu_beds_a", "to": "intervention_bay"},
        "ward": {"from": "resp_ward", "to": "diagnostic_center"},
    }.get(department_id, {})
    symbolic = values[0] if values else None
    symbolic_rooms = {
        "current_ed_room": "ed_minor",
        "current_ed_bed_room": "ed_observation",
        "current_op_room": "consultation_b_2",
        "current_consult_room": "consultation_b_2",
        "current_icu_bed_room": "icu_beds_a",
        "source_icu_bed_room": "icu_beds_a",
        "current_icu_exam_room": "intervention_bay",
        "current_ward_room": "resp_ward",
        "source_ward_room": "resp_ward",
        "target_ward_room": "resp_ward",
        "current_room": default_room_for_department(department_id),
    }
    return symbolic_rooms.get(symbolic) or fallback.get(direction) or default_room_for_department(department_id)


def request_schema(request_type):
    base = {
        "type": "object",
        "required": ["patient_id"],
        "properties": {
            "patient_id": {"type": "string"},
            "encounter_id": {"type": "string"},
            "reason": {"type": "string"},
            "summary": {"type": "object"},
        },
    }
    schemas = {
        "patient_upsert": {
            **base,
            "required": ["patient_id", "name"],
            "properties": {
                **base["properties"],
                "name": {"type": "string"},
                "gender": {"type": "string", "enum": ["male", "female", "other", "unknown"]},
                "age": {"type": "integer"},
                "contact": {"type": "string"},
                "allergies": {"type": "array"},
                "chronic_conditions": {"type": "array"},
                "blood_type": {"type": "string"},
            },
        },
        "encounter_open": {**base, "required": ["patient_id", "encounter_id"]},
        "movement_request": {
            **base,
            "required": ["patient_id", "event_id", "from_room_id", "to_room_id"],
            "properties": {
                **base["properties"],
                "event_id": {"type": "string", "description": "Must match an allowed Rules Admin eventId."},
                "from_room_id": {"type": "string"},
                "to_room_id": {"type": "string"},
            },
        },
        "transfer_request": {
            **base,
            "required": ["patient_id", "encounter_id", "from_room_id", "to_department_id", "reason"],
            "properties": {
                **base["properties"],
                "event_id": {"type": "string", "description": "Optional; when provided it must match an allowed transfer rule."},
                "from_room_id": {"type": "string"},
                "to_room_id": {"type": "string", "description": "Optional; defaults to the rule target room."},
                "to_department_id": {"type": "string"},
                "ctas_level": {"type": "string"},
                "requested_resources": {"type": "object"},
            },
        },
        "discharge_request": {
            **base,
            "required": ["patient_id", "encounter_id", "reason"],
            "properties": {
                **base["properties"],
                "event_id": {"type": "string", "description": "Optional; defaults to the department discharge rule."},
                "admission_id": {"type": "string"},
                "bed_id": {"type": "string"},
            },
        },
        "clinical_event": {
            **base,
            "required": ["patient_id", "event_type", "summary"],
            "properties": {
                **base["properties"],
                "event_type": {"type": "string"},
                "clinical_summary": {"type": "object"},
                "recommendations": {"type": "array"},
                "required_updates": {"type": "array"},
            },
        },
    }
    return schemas.get(request_type, base)


def department_examples(department_id):
    patient_id = example_patient_id_for(department_id)
    encounter_id = "E-20260612103000-9f3a"
    examples = {
        "patient_upsert": {
            "patient_id": patient_id,
            "name": "Debug Patient",
            "gender": "unknown",
            "age": 56,
            "contact": "13800000000",
            "allergies": ["penicillin"],
            "chronic_conditions": ["hypertension"],
            "blood_type": "A+",
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
            "admission_id": "ADM-DEBUG-001",
            "bed_id": "icu_beds_a-bed-01",
            "reason": "stable for discharge",
            "summary": {"final_status": "stable", "follow_up": "outpatient review in 7 days"},
        },
        "clinical_event": clinical_example_for(department_id, patient_id, encounter_id),
    }
    enabled = department_meta(department_id)["enabled_request_types"]
    return {key: value for key, value in examples.items() if key in enabled}


def build_closed_loop_debug_scenario():
    return {
        "id": "closed_loop_multi_patient_v1",
        "label": "Closed-loop multi-patient flow",
        "description": "Creates debug patients, moves them through department handlers, and discharges every patient at the end.",
        "defaults": {
            "stepDelayMs": 1800,
            "idempotencyPrefix": "debug-closed-loop",
        },
        "patients": [
            {"key": "opA", "label": "OP A: registration -> triage -> consult -> lab -> ward -> discharge"},
            {"key": "opB", "label": "OP B: alternate consult room -> ward -> discharge"},
            {"key": "edA", "label": "ED A: arrival -> triage -> treatment -> diagnostic -> ward -> discharge"},
            {"key": "icuA", "label": "ICU A: admission -> ICU bed -> exam -> ward -> discharge"},
        ],
        "steps": [
            scenario_upsert("opA", "outpatient", "registration_2", "Debug OP A {{runId}}", "门诊闭环 A：咳嗽复诊，需要检查后住院"),
            scenario_move("opA", "outpatient", "OP_REGISTRATION_TO_TRIAGE_OR_WAITING", "registration_2", "triage_2", "门诊 A 完成挂号后进入分诊"),
            scenario_move("opA", "outpatient", "OP_TRIAGE_TO_CONSULT_ROOM", "triage_2", "consultation_a_2", "门诊 A 分诊到 consultation_a_2"),
            scenario_move("opA", "outpatient", "OP_CONSULT_TO_PAYMENT", "consultation_a_2", "payment_2", "门诊 A 诊后缴费"),
            scenario_move("opA", "outpatient", "OP_PAYMENT_TO_LAB", "payment_2", "lab_2", "门诊 A 缴费后检验"),
            scenario_move("opA", "outpatient", "OP_LAB_RETURN_TO_WAITING", "lab_2", "outpatient_waiting", "门诊 A 检验完成返回候诊"),
            scenario_move("opA", "outpatient", "OP_SECOND_CONSULT_MOVE", "outpatient_waiting", "consultation_a_2", "门诊 A 复诊回到 consultation_a_2"),
            scenario_transfer("opA", "outpatient", "OP_TO_WARD_MOVE", "consultation_a_2", "ward_admission", "ward", "门诊 A 转住院"),
            scenario_move("opA", "ward", "WARD_TO_DIAGNOSTIC_MOVE", "{{opA.currentRoom}}", "diagnostic_center", "住院 A 前往检查中心"),
            scenario_move("opA", "ward", "WARD_DIAGNOSTIC_RETURN", "diagnostic_center", "{{opA.bedRoom}}", "住院 A 检查后返回原病房"),
            scenario_discharge("opA", "ward", "WARD_DISCHARGE_EXIT_HOSPITAL", "住院 A 完成出院"),

            scenario_upsert("opB", "outpatient", "registration_2", "Debug OP B {{runId}}", "门诊闭环 B：皮疹和低热，转外科评估后住院"),
            scenario_move("opB", "outpatient", "OP_REGISTRATION_TO_TRIAGE_OR_WAITING", "registration_2", "outpatient_waiting", "门诊 B 挂号后进入候诊区"),
            scenario_move("opB", "outpatient", "OP_TRIAGE_TO_CONSULT_ROOM", "outpatient_waiting", "surgery_2", "门诊 B 分诊到 surgery_2"),
            scenario_transfer("opB", "outpatient", "OP_TO_WARD_MOVE", "surgery_2", "ward_admission", "ward", "门诊 B 转住院"),
            scenario_move("opB", "ward", "WARD_BED_TO_BED_MOVE", "{{opB.currentRoom}}", "neuro_ward", "住院 B 从初始病房调整到神经病房"),
            scenario_discharge("opB", "ward", "WARD_DISCHARGE_EXIT_HOSPITAL", "住院 B 完成出院"),

            scenario_upsert("edA", "emergency", "ed_entrance", "Debug ED A {{runId}}", "急诊闭环：胸痛气促，检查后住院"),
            scenario_move("edA", "emergency", "ED_ENTRANCE_TO_REGISTRATION", "ed_entrance", "ed_registration", "急诊 A 到登记"),
            scenario_move("edA", "emergency", "ED_REGISTRATION_TO_TRIAGE_OR_WAITING", "ed_registration", "ed_triage", "急诊 A 登记后分诊"),
            scenario_move("edA", "emergency", "ED_TRIAGE_TO_TREATMENT_AREA", "ed_triage", "ed_major", "急诊 A 进入治疗区"),
            scenario_move("edA", "emergency", "ED_TO_DIAGNOSTIC_MOVE", "ed_major", "ed_diagnostic", "急诊 A 前往检查"),
            scenario_move("edA", "emergency", "ED_DIAGNOSTIC_RETURN", "ed_diagnostic", "ed_major", "急诊 A 检查返回"),
            scenario_transfer("edA", "emergency", "TRANSFER_ED_TO_WARD", "ed_major", "ward_admission", "ward", "急诊 A 转住院"),
            scenario_discharge("edA", "ward", "WARD_DISCHARGE_EXIT_HOSPITAL", "急诊转住院 A 完成出院"),

            scenario_upsert("icuA", "icu", "icu_admission", "Debug ICU A {{runId}}", "ICU 闭环：入 ICU 后转普通住院并出院"),
            scenario_move("icuA", "icu", "ICU_ADMISSION_TO_BED", "icu_admission", "icu_beds_b", "ICU A 接收入床"),
            scenario_move("icuA", "icu", "ICU_TO_EXAM_OR_INTERVENTION", "{{icuA.currentRoom}}", "intervention_bay", "ICU A 前往干预区"),
            scenario_move("icuA", "icu", "ICU_RETURN_TO_BED", "intervention_bay", "{{icuA.bedRoom}}", "ICU A 返回原 ICU 床"),
            scenario_transfer("icuA", "icu", "TRANSFER_ICU_TO_WARD", "{{icuA.currentRoom}}", "ward_admission", "ward", "ICU A 转普通住院"),
            scenario_discharge("icuA", "ward", "WARD_DISCHARGE_EXIT_HOSPITAL", "ICU A 转住院后完成出院"),
        ],
    }


def scenario_patient_id(patient_key):
    return f"P-DBG-{patient_key.upper()}-{{{{runId}}}}"


def scenario_encounter_id(patient_key):
    return f"E-DBG-{patient_key.upper()}-{{{{runId}}}}"


def scenario_upsert(patient_key, department_id, room_id, name, symptoms):
    return {
        "patientKey": patient_key,
        "departmentId": department_id,
        "requestType": "patient_upsert",
        "title": f"{patient_key} upsert",
        "description": f"{patient_key} enters {department_id}.",
        "waitMs": 1100,
        "payload": {
            "patient_id": scenario_patient_id(patient_key),
            "encounter_id": scenario_encounter_id(patient_key),
            "name": name,
            "gender": "unknown",
            "age": 48,
            "room_id": room_id,
            "status": "ARRIVED",
            "symptoms": symptoms,
            "summary": {"chief_complaint": symptoms, "debug_scenario": "closed_loop_multi_patient_v1"},
        },
    }


def scenario_move(patient_key, department_id, event_id, from_room_id, to_room_id, description):
    return {
        "patientKey": patient_key,
        "departmentId": department_id,
        "requestType": "movement_request",
        "title": event_id,
        "description": description,
        "waitMs": 1800,
        "payload": {
            "patient_id": scenario_patient_id(patient_key),
            "encounter_id": scenario_encounter_id(patient_key),
            "event_id": event_id,
            "from_room_id": from_room_id,
            "to_room_id": to_room_id,
            "reason": description,
            "summary": {"debug_step": description},
        },
    }


def scenario_transfer(patient_key, department_id, event_id, from_room_id, to_room_id, to_department_id, description):
    return {
        "patientKey": patient_key,
        "departmentId": department_id,
        "requestType": "transfer_request",
        "title": event_id,
        "description": description,
        "waitMs": 2200,
        "payload": {
            "patient_id": scenario_patient_id(patient_key),
            "encounter_id": scenario_encounter_id(patient_key),
            "event_id": event_id,
            "from_room_id": from_room_id,
            "to_room_id": to_room_id,
            "to_department_id": to_department_id,
            "reason": description,
            "summary": {
                "chief_complaint": description,
                "key_findings": ["debug closed-loop transfer"],
                "active_diagnoses": ["debug scenario"],
            },
            "requested_resources": {"bed_type": to_department_id.upper(), "monitor": to_department_id == "icu"},
        },
    }


def scenario_discharge(patient_key, department_id, event_id, description):
    return {
        "patientKey": patient_key,
        "departmentId": department_id,
        "requestType": "discharge_request",
        "title": event_id,
        "description": description,
        "waitMs": 1600,
        "payload": {
            "patient_id": scenario_patient_id(patient_key),
            "encounter_id": scenario_encounter_id(patient_key),
            "event_id": event_id,
            "reason": description,
            "summary": {"final_status": "stable", "debug_outcome": "closed_loop_discharged"},
        },
    }


def example_patient_id_for(department_id):
    return {
        "outpatient": "P-OP-005",
        "emergency": "P-ER-002",
        "icu": "P-ICU-001",
        "mdt": "P-MDT-001",
        "ward": "P-WD-002",
    }.get(department_id, "P-a1b2c3d4")


def movement_example_for(department_id, patient_id, encounter_id):
    rule = first_rule_for_request(department_id, "movement_request")
    event_id = rule.get("eventId") if rule else "ED_WAITING_TO_CONSULT_ROOM"
    movement = rule.get("movement", {}) if rule else {"from": "ed_waiting", "to": "ed_minor"}
    from_room_id = example_room_for_rule_value(movement.get("from"), department_id, "from")
    to_room_id = example_room_for_rule_value(movement.get("to"), department_id, "to")
    return {
        "patient_id": patient_id,
        "encounter_id": encounter_id,
        "event_id": event_id,
        "from_room_id": from_room_id,
        "to_room_id": to_room_id,
        "reason": "dashboard movement debug",
    }


def transfer_example_for(department_id, patient_id, encounter_id):
    rule = first_rule_for_request(department_id, "transfer_request")
    event_id = rule.get("eventId") if rule else None
    movement = rule.get("movement", {}) if rule else {}
    target = target_department_for_transfer_rule(rule) or {"emergency": "icu", "outpatient": "ward", "icu": "ward", "ward": "icu"}.get(department_id, "icu")
    source_room = example_room_for_rule_value(movement.get("from"), department_id, "from")
    target_room = example_room_for_rule_value(movement.get("to"), target, "to")
    return {
        "patient_id": patient_id,
        "encounter_id": encounter_id,
        "event_id": event_id,
        "from_room_id": source_room,
        "to_room_id": target_room,
        "to_department_id": target,
        "reason": "needs higher level coordinated care",
        "ctas_level": "L2",
        "summary": {
            "chief_complaint": "dashboard transfer debug",
            "key_findings": ["requires monitored bed"],
            "active_diagnoses": ["debug diagnosis"],
            "vital_baseline": {"hr": 92, "sbp": 118, "dbp": 74, "spo2": 96, "temp": 36.8, "rr": 18},
        },
        "requested_resources": {"bed_type": target.upper(), "monitor": True},
    }


def clinical_example_for(department_id, patient_id, encounter_id):
    if department_id == "mdt":
        return {
            "patient_id": patient_id,
            "encounter_id": encounter_id,
            "event_type": "mdt.consultation_completed",
            "consultation_id": "MDT-DEBUG-001",
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
            "staffId": "N-WD-001",
            "fromRoomId": "R-WARD-NURSE-STATION",
            "toRoomId": "R-WARD-CARD",
            "returnRoomId": "R-WARD-NURSE-STATION",
            "durationSeconds": 8,
            "reason": "nurse execute immediate order",
            "summary": {"note": "Ward nurse visit debug event"},
            "additionalExamples": [
                {
                    "event_type": "WARD_DOCTOR_ROUND_VISIT",
                    "event_id": "WARD_DOCTOR_ROUND_VISIT",
                    "staffId": "D-WD-001",
                    "fromRoomId": "R-WARD-DOCTOR-OFFICE",
                    "toRoomId": "R-WARD-CARD",
                    "returnRoomId": "R-WARD-DOCTOR-OFFICE",
                    "durationSeconds": 9,
                }
            ],
        }
    return {
        "patient_id": patient_id,
        "encounter_id": encounter_id,
        "event_type": "clinical.summary_updated",
        "summary": {"note": f"{department_id} debug clinical update"},
    }


def handle_department_request(department_id, request_type, payload, idempotency_key=""):
    trace_id = new_trace_id()
    meta = department_meta(department_id)
    if not meta:
        return api_error("DEPARTMENT_NOT_FOUND", f"Unknown department: {department_id}", trace_id=trace_id)
    if request_type not in meta["enabled_request_types"]:
        return api_error("REQUEST_TYPE_NOT_ENABLED", f"{request_type} is not enabled for {department_id}.", trace_id=trace_id)

    idempotency_key = str(idempotency_key or "").strip()
    if idempotency_key:
        replay = idempotency_lookup(department_id, request_type, idempotency_key)
        if replay:
            replay["data"]["idempotencyReplay"] = True
            return replay

    normalized = normalize_department_handler_payload(department_id, request_type, payload)
    result = dispatch_department_request(department_id, request_type, normalized)
    status = "accepted" if result.get("accepted") else "rejected"
    error_code = result.get("reasonCode") or result.get("error_code") or result.get("error", {}).get("code")
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
        trace_id=trace_id,
    )
    if not result.get("accepted"):
        response["error"] = {
            "code": error_code or "REQUEST_REJECTED",
            "message": result.get("message") or "Request rejected by Fullview Core.",
            "details": result,
        }
    log_department_request(
        department_id=department_id,
        request_type=request_type,
        idempotency_key=idempotency_key,
        raw_payload=payload,
        normalized_payload=normalized,
        status=status,
        core_response=result,
        error_code=error_code,
        trace_id=trace_id,
    )
    if idempotency_key:
        idempotency_store(department_id, request_type, idempotency_key, response)
    return response


def normalize_department_handler_payload(department_id, request_type, payload):
    payload = dict(payload or {})
    correlation_id = payload.get("correlation_id") or payload.get("correlationId") or new_event_id()
    normalized = {
        **payload,
        "department_id": department_id,
        "source_department_id": department_id,
        "producer": DEPARTMENT_PRODUCERS[department_id],
        "request_type": request_type,
        "correlation_id": correlation_id,
        "received_at": utc_now_iso(),
    }
    if "patientId" in normalized and "patient_id" not in normalized:
        normalized["patient_id"] = normalized["patientId"]
    if "encounterId" in normalized and "encounter_id" not in normalized:
        normalized["encounter_id"] = normalized["encounterId"]
    return normalized


def dispatch_department_request(department_id, request_type, payload):
    if request_type == "patient_upsert":
        return handle_department_patient_upsert(department_id, payload)
    if request_type == "encounter_open":
        return handle_department_encounter_open(department_id, payload)
    if request_type == "movement_request":
        return handle_department_movement(department_id, payload)
    if request_type == "transfer_request":
        return handle_department_transfer(department_id, payload)
    if request_type == "discharge_request":
        return handle_department_discharge(department_id, payload)
    if request_type == "clinical_event":
        return handle_department_clinical_event(department_id, payload)
    return {"accepted": False, "reasonCode": "REQUEST_TYPE_UNKNOWN", "message": f"Unknown request type: {request_type}"}


def build_snapshot():
    map_config = read_json(MAP_CONFIG)
    patients = [normalize_patient_record(patient) for patient in read_json(PATIENTS_FILE).get("patients", [])]
    staff = [normalize_staff_record(member) for member in read_json(STAFF_FILE).get("staff", [])]
    room_state = read_json(ROOM_STATE_FILE)
    floors, rooms = normalize_map(map_config)
    rooms_by_id = {room["id"]: room for room in rooms}
    assign_hallway_staff_positions(staff, rooms_by_id)
    sanitize_patient_staff_references(patients, staff)
    recompute_room_state(room_state, patients, rooms_by_id)
    departments = build_department_status(floors, rooms, patients)

    return {
        "floors": floors,
        "rooms": [decorate_room(room, patients, staff, room_state) for room in rooms],
        "patients": patients,
        "staff": staff,
        "departments": departments,
        "eventSeq": read_json(EVENT_LOG_FILE).get("lastSeq", 0),
    }


def handle_move_request(request):
    request = normalize_move_request(request)
    patients_data = read_json(PATIENTS_FILE)
    staff_data = read_json(STAFF_FILE)
    room_state = read_json(ROOM_STATE_FILE)
    event_log = read_json(EVENT_LOG_FILE)
    map_config = read_json(MAP_CONFIG)
    _, rooms = normalize_map(map_config)
    rooms_by_id = {room["id"]: room for room in rooms}
    patients = [normalize_patient_record(patient) for patient in patients_data.get("patients", [])]
    recompute_room_state(room_state, patients, rooms_by_id)
    patient = find_patient(patients, request.get("patientId"))
    rule = find_rule(request.get("eventId"))
    from_room_id = request.get("fromRoomId")
    to_room_id = request.get("toRoomId")

    error = validate_move_request(request, patient, rule, rooms_by_id, room_state)
    event_seq = next_event_seq(event_log)

    if error:
        response = {
            "accepted": False,
            "eventSeq": event_seq,
            "eventId": request.get("eventId"),
            "patientId": request.get("patientId"),
            "reasonCode": error["code"],
            "message": error["message"],
        }
        append_event(event_log, response, request)
        write_json(EVENT_LOG_FILE, event_log)
        return response

    movement = rule.get("movement", {})
    requested_target_room = rooms_by_id[to_room_id]
    previous_room = rooms_by_id.get(patient.get("roomId"))
    previous_bed_room_id = patient.get("bedRoomId")
    final_form = movement.get("final_form") or movement.get("finalForm", "walking")
    target_room = resolve_final_target_room(movement, requested_target_room, room_state, rooms_by_id)
    if final_form == "bed" and not target_room:
        response = {
            "accepted": False,
            "eventSeq": event_seq,
            "eventId": request.get("eventId"),
            "patientId": request.get("patientId"),
            "reasonCode": "NO_BED_AVAILABLE",
            "message": "No available ward/ICU bed room for this transfer.",
        }
        append_event(event_log, response, request)
        write_json(EVENT_LOG_FILE, event_log)
        return response

    if should_queue_for_busy_consult(target_room, patient, patients):
        enqueue_consult_patient(room_state, target_room["id"], patient, from_room_id, request.get("eventId"))
        recompute_room_state(room_state, patients, rooms_by_id)
        write_json(ROOM_STATE_FILE, room_state)
        response = {
            "accepted": False,
            "eventSeq": event_seq,
            "eventId": request.get("eventId"),
            "patientId": request.get("patientId"),
            "reasonCode": "CONSULT_ROOM_BUSY_QUEUED",
            "message": "Target consultation room is occupied; patient has been added to this room queue.",
            "queued": True,
            "queueRoomId": target_room["id"],
        }
        append_event(event_log, response, request)
        write_json(EVENT_LOG_FILE, event_log)
        return response

    selected_porter = choose_nearest_porter(staff_data.get("staff", []), patient, rooms_by_id) if movement_needs_porter(movement) else None
    if movement_needs_porter(movement) and not selected_porter:
        response = {
            "accepted": False,
            "eventSeq": event_seq,
            "eventId": request.get("eventId"),
            "patientId": request.get("patientId"),
            "reasonCode": "PORTER_UNAVAILABLE",
            "message": "No available hallway porter found for this transfer.",
        }
        append_event(event_log, response, request)
        write_json(EVENT_LOG_FILE, event_log)
        return response

    release_source_bed = should_release_source_bed(movement, final_form, previous_bed_room_id, target_room)

    if release_source_bed:
        release_patient_bed(room_state, patient)
    if final_form == "bed" and is_care_room(target_room):
        assign_patient_bed(room_state, patient, target_room["id"])

    set_patient_room(patient, target_room["id"])
    set_patient_status(patient, final_status_for(final_form, target_room))
    set_patient_visual_form(patient, visual_form_for(final_form, target_room))
    set_patient_relative_position(
        patient,
        default_rel_x_for(patient["form"], target_room),
        default_rel_y_for(patient["form"], target_room),
    )
    if patient["form"] == "bed":
        patient["blanket"] = "#d46d8e" if target_room.get("kind") == "icu" else "#76c59d"
        patient["skin"] = patient.get("skin") or "#f2c799"

    porter_return = update_porter_after_transfer(staff_data, selected_porter, target_room) if selected_porter else None
    sanitize_patient_staff_references(patients, [normalize_staff_record(member) for member in staff_data.get("staff", [])])
    recompute_room_state(room_state, patients, rooms_by_id)
    patients_data["patients"] = patients
    write_json(PATIENTS_FILE, patients_data)
    if selected_porter:
        write_json(STAFF_FILE, staff_data)
    write_json(ROOM_STATE_FILE, room_state)

    response = {
        "accepted": True,
        "event_seq": event_seq,
        "eventSeq": event_seq,
        "event_id": rule.get("event_id") or rule.get("eventId"),
        "eventId": rule.get("eventId") or rule.get("event_id"),
        "patient_id": patient_identifier(patient),
        "patientId": patient.get("patientId"),
        "status_updates": {
            "patient_status": "TRANSFERRING",
            "from_room_released": previous_room is not None and not patient.get("bedRoomId") == previous_bed_room_id,
            "source_bed_retained": bool(previous_bed_room_id and patient.get("bedRoomId") == previous_bed_room_id),
            "target_reserved": bool(patient.get("bedRoomId") == target_room["id"]),
            "requested_target_room_id": to_room_id,
            "bed_room_id": patient.get("bedRoomId"),
            "bed_id": patient.get("bedId"),
        },
        "statusUpdates": {
            "patientStatus": "TRANSFERRING",
            "fromRoomReleased": previous_room is not None and not patient.get("bedRoomId") == previous_bed_room_id,
            "sourceBedRetained": bool(previous_bed_room_id and patient.get("bedRoomId") == previous_bed_room_id),
            "targetReserved": bool(patient.get("bedRoomId") == target_room["id"]),
            "requestedTargetRoomId": to_room_id,
            "bedRoomId": patient.get("bedRoomId"),
            "bedId": patient.get("bedId"),
        },
        "animation_plan": {
            "kind": "patient-move",
            "transport": movement.get("transport", "walking"),
            "escort_roles": movement.get("escort_roles") or movement.get("escortRoles", []),
            "equipment": movement.get("equipment", []),
            "from_room_id": from_room_id,
            "to_room_id": target_room["id"],
            "requested_to_room_id": to_room_id,
            "via_room_ids": resolved_via_rooms(movement, to_room_id, target_room["id"]),
            "final_form": final_form,
            "patient_form_during_move": movement.get("patient_form_during_move") or movement.get("patientFormDuringMove", movement.get("transport", "walking")),
            "porter_id": selected_porter.get("id") if selected_porter else None,
            "porter_staff_id": selected_porter.get("staffId") if selected_porter else None,
            "porter_name": selected_porter.get("name") if selected_porter else None,
            "porter_start": selected_porter.get("point") if selected_porter else None,
            "porter_return": porter_return,
        },
        "animationPlan": {
            "kind": "patient-move",
            "transport": movement.get("transport", "walking"),
            "escortRoles": movement.get("escort_roles") or movement.get("escortRoles", []),
            "equipment": movement.get("equipment", []),
            "fromRoomId": from_room_id,
            "toRoomId": target_room["id"],
            "requestedToRoomId": to_room_id,
            "viaRoomIds": resolved_via_rooms(movement, to_room_id, target_room["id"]),
            "finalForm": final_form,
            "patientFormDuringMove": movement.get("patient_form_during_move") or movement.get("patientFormDuringMove", movement.get("transport", "walking")),
            "porterId": selected_porter.get("id") if selected_porter else None,
            "porterStaffId": selected_porter.get("staffId") if selected_porter else None,
            "porterName": selected_porter.get("name") if selected_porter else None,
            "porterStart": selected_porter.get("point") if selected_porter else None,
            "porterReturn": porter_return,
        },
    }
    append_event(event_log, response, request)
    if previous_room and previous_room.get("id") != target_room["id"]:
        process_consult_queue_after_departure(event_log, patients, room_state, rooms_by_id, previous_room)
        patients_data["patients"] = patients
        recompute_room_state(room_state, patients, rooms_by_id)
        write_json(PATIENTS_FILE, patients_data)
        write_json(ROOM_STATE_FILE, room_state)
    write_json(EVENT_LOG_FILE, event_log)
    return response


def handle_delete_patient(patient_id):
    patients_data = read_json(PATIENTS_FILE)
    staff_data = read_json(STAFF_FILE)
    room_state = read_json(ROOM_STATE_FILE)
    event_log = read_json(EVENT_LOG_FILE)
    map_config = read_json(MAP_CONFIG)
    _, rooms = normalize_map(map_config)
    rooms_by_id = {room["id"]: room for room in rooms}
    patients = [normalize_patient_record(patient) for patient in patients_data.get("patients", [])]
    staff = [normalize_staff_record(member) for member in staff_data.get("staff", [])]
    recompute_room_state(room_state, patients, rooms_by_id)
    patient = find_patient(patients, patient_id)
    event_seq = next_event_seq(event_log)

    if not patient:
        response = {
            "accepted": False,
            "eventSeq": event_seq,
            "eventId": "PATIENT_DELETE",
            "patientId": patient_id,
            "reasonCode": "PATIENT_NOT_FOUND",
            "message": f"No patient found for {patient_id}.",
        }
        append_event(event_log, response, {"source": "console", "patientId": patient_id})
        write_json(EVENT_LOG_FILE, event_log)
        return response

    previous_room = rooms_by_id.get(patient.get("roomId"))
    release_patient_bed(room_state, patient)
    remove_patient_from_all_queues(room_state, patient_identifier(patient))
    patients = [item for item in patients if patient_identifier(item) != patient_identifier(patient)]
    sanitize_patient_staff_references(patients, staff)
    recompute_room_state(room_state, patients, rooms_by_id)
    patients_data["patients"] = patients
    write_json(PATIENTS_FILE, patients_data)
    write_json(ROOM_STATE_FILE, room_state)

    response = {
        "accepted": True,
        "eventSeq": event_seq,
        "eventId": "PATIENT_DELETE",
        "patientId": patient_identifier(patient),
        "removed": True,
        "message": f"Patient {patient_identifier(patient)} has been removed.",
    }
    append_event(event_log, response, {"source": "console", "patientId": patient_identifier(patient)})
    if previous_room:
        process_consult_queue_after_departure(event_log, patients, room_state, rooms_by_id, previous_room)
        patients_data["patients"] = patients
        recompute_room_state(room_state, patients, rooms_by_id)
        write_json(PATIENTS_FILE, patients_data)
        write_json(ROOM_STATE_FILE, room_state)
    write_json(EVENT_LOG_FILE, event_log)
    return response


def handle_department_patient_upsert(department_id, payload):
    patient_id = str(payload.get("patient_id") or "").strip() or f"P-{uuid.uuid4().hex[:8]}"
    if not patient_id:
        return {"accepted": False, "reasonCode": "MISSING_PATIENT_ID", "message": "patient_id is required."}

    patients_data = read_json(PATIENTS_FILE)
    map_config = read_json(MAP_CONFIG)
    _, rooms = normalize_map(map_config)
    rooms_by_id = {room["id"]: room for room in rooms}
    patients = [normalize_patient_record(patient) for patient in patients_data.get("patients", [])]
    patient = find_patient(patients, patient_id)
    default_room_id = default_room_for_department(department_id)
    clinical_summary = payload.get("summary") or payload.get("clinical_summary") or {}

    if patient:
        patient["name"] = payload.get("name") or payload.get("patient_name") or patient.get("name") or "Unknown Patient"
        patient["gender"] = payload.get("gender", patient.get("gender", "unknown"))
        patient["department_id"] = department_id
        patient["department"] = DEPARTMENT_DISPLAY.get(department_id, department_id)
        patient["status"] = payload.get("status") or patient.get("status") or "ARRIVED"
        patient.setdefault("clinical", {}).update({
            "status": patient["status"],
            "symptoms": payload.get("symptoms") or clinical_summary.get("chief_complaint") or patient.get("symptoms", ""),
            "department_payload": clinical_summary,
        })
    else:
        room_id = payload.get("room_id") or payload.get("roomId") or default_room_id
        patient = normalize_patient_record({
            "id": f"{department_id}-api-{patient_id.lower().replace('-', '')[-8:]}",
            "local_person_id": f"{department_id}-api-{patient_id.lower().replace('-', '')[-8:]}",
            "patient_id": patient_id,
            "patientId": patient_id,
            "type": "patient",
            "name": payload.get("name") or payload.get("patient_name") or "Unknown Patient",
            "gender": payload.get("gender", "unknown"),
            "department_id": department_id,
            "department": DEPARTMENT_DISPLAY.get(department_id, department_id),
            "symptoms": payload.get("symptoms") or clinical_summary.get("chief_complaint", ""),
            "status": payload.get("status") or "ARRIVED",
            "room_id": room_id,
            "roomId": room_id,
            "current_location": {"room_id": room_id},
            "home_bed": {},
            "form": payload.get("form") or default_form_for_room(rooms_by_id.get(room_id, {})),
            "baseForm": "walking",
            "base_form": "walking",
            "relX": 0.5,
            "relY": 0.58,
            "rel_x": 0.5,
            "rel_y": 0.58,
            "color": payload.get("color") or "#7899c6",
            "skin": payload.get("skin"),
            "blanket": payload.get("blanket"),
            "phase": 0,
            "clinical": {
                "status": payload.get("status") or "ARRIVED",
                "symptoms": payload.get("symptoms") or clinical_summary.get("chief_complaint", ""),
                "care_phase": payload.get("care_phase"),
                "ctas_level": payload.get("ctas_level"),
                "active_problems": payload.get("active_problems", []),
                "active_risks": payload.get("active_risks", []),
                "latest_interventions": payload.get("latest_interventions", []),
                "department_payload": clinical_summary,
            },
            "visual": {
                "form": payload.get("form") or default_form_for_room(rooms_by_id.get(room_id, {})),
                "base_form": "walking",
                "rel_x": 0.5,
                "rel_y": 0.58,
                "color": payload.get("color") or "#7899c6",
                "skin": payload.get("skin"),
                "blanket": payload.get("blanket"),
            },
        })
        patients.append(patient)

    patients_data["patients"] = patients
    write_json(PATIENTS_FILE, patients_data)
    response = append_core_event(
        event_id="DEPARTMENT_PATIENT_UPSERT",
        patient_id=patient_id,
        accepted=True,
        request=payload,
        message=f"Patient {patient_id} stored for {department_id}.",
        event_type="patient.upserted",
        snapshot_refresh=True,
    )
    return {
        **response,
        "accepted": True,
        "eventId": "DEPARTMENT_PATIENT_UPSERT",
        "patientId": patient_id,
        "patient": patient,
        "message": f"Patient {patient_id} stored for {department_id}.",
    }


def handle_department_encounter_open(department_id, payload):
    if not payload.get("patient_id"):
        return {"accepted": False, "reasonCode": "MISSING_PATIENT_ID", "message": "patient_id is required."}
    if not payload.get("encounter_id"):
        return {"accepted": False, "reasonCode": "MISSING_ENCOUNTER_ID", "message": "encounter_id is required."}
    upsert = handle_department_patient_upsert(department_id, payload)
    if not upsert.get("accepted"):
        return upsert
    return append_core_event(
        event_id="ENCOUNTER_OPENED",
        patient_id=payload.get("patient_id"),
        accepted=True,
        request=payload,
        message=f"Encounter {payload.get('encounter_id')} opened by {department_id}.",
        event_type="encounter.opened",
    )


def handle_department_movement(department_id, payload):
    required = ["patient_id", "event_id", "from_room_id", "to_room_id"]
    missing = [key for key in required if not payload.get(key)]
    if missing:
        return {"accepted": False, "reasonCode": f"MISSING_{missing[0].upper()}", "message": f"{missing[0]} is required."}
    rule_error = ensure_rule_allowed_for_department(department_id, "movement_request", payload.get("event_id"))
    if rule_error:
        return rule_error
    return handle_move_request({
        "request_id": payload.get("request_id") or payload.get("correlation_id"),
        "source": payload.get("producer") or DEPARTMENT_PRODUCERS.get(department_id),
        "operator_id": f"{department_id}-handler",
        "event_id": payload.get("event_id"),
        "patient_id": payload.get("patient_id"),
        "from_room_id": payload.get("from_room_id"),
        "to_room_id": payload.get("to_room_id"),
        "context": {
            "reason": payload.get("reason", ""),
            "department_id": department_id,
            "encounter_id": payload.get("encounter_id"),
            "handoff": payload.get("handoff") or payload.get("summary"),
        },
    })


def handle_department_transfer(department_id, payload):
    if not payload.get("patient_id"):
        return {"accepted": False, "reasonCode": "MISSING_PATIENT_ID", "message": "patient_id is required."}
    if not payload.get("from_room_id"):
        return {"accepted": False, "reasonCode": "MISSING_FROM_ROOM_ID", "message": "from_room_id is required."}
    target_department = str(payload.get("to_department_id") or payload.get("target_department_id") or "").strip().lower()
    event_id, target_room_id = transfer_rule_for(department_id, target_department)
    event_id = payload.get("event_id") or payload.get("eventId") or event_id
    rule_error = ensure_rule_allowed_for_department(department_id, "transfer_request", event_id)
    if rule_error:
        return rule_error
    rule = find_rule(event_id)
    rule_target_department = target_department_for_transfer_rule(rule)
    if target_department and rule_target_department and target_department != rule_target_department:
        return {
            "accepted": False,
            "reasonCode": "TRANSFER_RULE_TARGET_MISMATCH",
            "message": f"{event_id} targets {rule_target_department}, not {target_department}.",
            "ruleTargetDepartment": rule_target_department,
        }
    if not target_department:
        target_department = rule_target_department or ""
    target_room_id = payload.get("to_room_id") or payload.get("toRoomId") or target_room_id or example_room_for_rule_value(rule.get("movement", {}).get("to"), target_department, "to")
    if not event_id:
        return {
            "accepted": False,
            "reasonCode": "TRANSFER_ROUTE_UNSUPPORTED",
            "message": f"No Fullview transfer rule for {department_id} -> {target_department}.",
        }

    response = handle_move_request({
        "request_id": payload.get("request_id") or payload.get("correlation_id"),
        "source": payload.get("producer") or DEPARTMENT_PRODUCERS.get(department_id),
        "operator_id": f"{department_id}-handler",
        "event_id": event_id,
        "patient_id": payload.get("patient_id"),
        "from_room_id": payload.get("from_room_id"),
        "to_room_id": target_room_id,
        "context": {
            "reason": payload.get("reason", ""),
            "encounter_id": payload.get("encounter_id"),
            "to_department_id": target_department,
            "ctas_level": payload.get("ctas_level"),
            "requested_resources": payload.get("requested_resources", {}),
            "handoff_summary": payload.get("summary", {}),
        },
    })
    if not response.get("accepted") and target_department == "icu" and response.get("reasonCode") in {"NO_BED_AVAILABLE", "TARGET_ROOM_NOT_FOUND"}:
        response["reasonCode"] = "ICU_BED_UNAVAILABLE"
        response["message"] = "ICU has no available Fullview bed for this transfer."
    if not response.get("accepted") and target_department == "ward" and response.get("reasonCode") in {"NO_BED_AVAILABLE", "TARGET_ROOM_NOT_FOUND"}:
        response["reasonCode"] = "WARD_BED_UNAVAILABLE"
        response["message"] = "Ward has no available Fullview bed for this transfer."
    return response


def handle_department_discharge(department_id, payload):
    patient_id = payload.get("patient_id")
    if not patient_id:
        return {"accepted": False, "reasonCode": "MISSING_PATIENT_ID", "message": "patient_id is required."}
    event_id = payload.get("event_id") or payload.get("eventId") or discharge_event_id_for_department(department_id)
    rule_error = ensure_rule_allowed_for_department(department_id, "discharge_request", event_id)
    if rule_error:
        return rule_error

    patients_data = read_json(PATIENTS_FILE)
    staff_data = read_json(STAFF_FILE)
    room_state = read_json(ROOM_STATE_FILE)
    event_log = read_json(EVENT_LOG_FILE)
    map_config = read_json(MAP_CONFIG)
    _, rooms = normalize_map(map_config)
    rooms_by_id = {room["id"]: room for room in rooms}
    patients = [normalize_patient_record(patient) for patient in patients_data.get("patients", [])]
    staff = [normalize_staff_record(member) for member in staff_data.get("staff", [])]
    recompute_room_state(room_state, patients, rooms_by_id)
    patient = find_patient(patients, patient_id)
    event_seq = next_event_seq(event_log)

    if not patient:
        response = {
            "accepted": False,
            "eventSeq": event_seq,
            "eventId": event_id,
            "patientId": patient_id,
            "reasonCode": "PATIENT_NOT_FOUND",
            "message": f"No patient found for {patient_id}.",
        }
        append_event(event_log, response, payload)
        write_json(EVENT_LOG_FILE, event_log)
        return response

    previous_room_id = patient.get("roomId")
    rule = find_rule(event_id) or {}
    movement = rule.get("movement", {})
    visible_target_room_id = visible_discharge_target_room_id(movement, previous_room_id, rooms_by_id)
    release_patient_bed(room_state, patient)
    remove_patient_from_all_queues(room_state, patient_identifier(patient))
    set_patient_status(patient, "DISCHARGED")
    set_patient_visual_form(patient, "hidden")
    patient.setdefault("clinical", {})["discharge_summary"] = payload.get("summary", {})
    patient.setdefault("clinical", {})["discharge_reason"] = payload.get("reason", "")
    sanitize_patient_staff_references(patients, staff)
    recompute_room_state(room_state, patients, rooms_by_id)
    patients_data["patients"] = patients
    write_json(PATIENTS_FILE, patients_data)
    write_json(ROOM_STATE_FILE, room_state)

    response = {
        "accepted": True,
        "event_seq": event_seq,
        "eventSeq": event_seq,
        "event_id": event_id,
        "eventId": event_id,
        "patient_id": patient_identifier(patient),
        "patientId": patient_identifier(patient),
        "message": f"Patient {patient_identifier(patient)} discharged by {department_id}.",
        "statusUpdates": {
            "patientStatus": "DISCHARGED",
            "fromRoomReleased": True,
            "sourceBedRetained": False,
            "previousRoomId": previous_room_id,
        },
        "status_updates": {
            "patient_status": "DISCHARGED",
            "from_room_released": True,
            "source_bed_retained": False,
            "previous_room_id": previous_room_id,
        },
        "animation_plan": {
            "kind": "patient-move",
            "transport": movement.get("transport", "walking"),
            "escort_roles": movement.get("escort_roles") or movement.get("escortRoles", []),
            "equipment": movement.get("equipment", []),
            "from_room_id": previous_room_id,
            "to_room_id": visible_target_room_id,
            "requested_to_room_id": "exit",
            "via_room_ids": [
                room_id for room_id in movement.get("via", [])
                if room_id in rooms_by_id and room_id != visible_target_room_id
            ],
            "final_form": "hidden",
            "patient_form_during_move": movement.get("patient_form_during_move") or movement.get("patientFormDuringMove", movement.get("transport", "walking")),
        },
        "animationPlan": {
            "kind": "patient-move",
            "transport": movement.get("transport", "walking"),
            "escortRoles": movement.get("escort_roles") or movement.get("escortRoles", []),
            "equipment": movement.get("equipment", []),
            "fromRoomId": previous_room_id,
            "toRoomId": visible_target_room_id,
            "requestedToRoomId": "exit",
            "viaRoomIds": [
                room_id for room_id in movement.get("via", [])
                if room_id in rooms_by_id and room_id != visible_target_room_id
            ],
            "finalForm": "hidden",
            "patientFormDuringMove": movement.get("patient_form_during_move") or movement.get("patientFormDuringMove", movement.get("transport", "walking")),
        },
    }
    append_event(event_log, response, payload)
    write_json(EVENT_LOG_FILE, event_log)
    return response


def handle_department_clinical_event(department_id, payload):
    if not payload.get("patient_id"):
        return {"accepted": False, "reasonCode": "MISSING_PATIENT_ID", "message": "patient_id is required."}
    event_id = payload.get("event_id") or payload.get("event_type") or "clinical.summary_updated"
    staff_plan = None
    if event_id in {"WARD_NURSE_ORDER_VISIT", "WARD_DOCTOR_ROUND_VISIT"}:
        rule_error = ensure_rule_allowed_for_department(department_id, "clinical_event", event_id)
        if rule_error:
            return rule_error
        patients = [normalize_patient_record(patient) for patient in read_json(PATIENTS_FILE).get("patients", [])]
        patient = find_patient(patients, payload.get("patient_id"))
        if not patient:
            return {"accepted": False, "reasonCode": "PATIENT_NOT_FOUND", "message": f"No patient found for {payload.get('patient_id')}."}
        staff_result = build_staff_visit_plan(department_id, event_id, payload, patient)
        if staff_result.get("error"):
            return {"accepted": False, "reasonCode": staff_result["error"], "message": staff_result["message"]}
        staff_plan = staff_result["plan"]
    return append_core_event(
        event_id=str(event_id).upper().replace(".", "_"),
        patient_id=payload.get("patient_id"),
        accepted=True,
        request=payload,
        message=f"{department_id} clinical event stored.",
        event_type="staff.visit" if staff_plan else payload.get("event_type") or "clinical.summary_updated",
        staff_move_plan=staff_plan,
    )


def build_staff_visit_plan(department_id, event_id, payload, patient):
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
    rooms_by_id = {room["id"]: room for room in normalize_map(read_json(MAP_CONFIG))[1]}
    from_room_id = payload.get("fromRoomId") or payload.get("from_room_id") or default_staff_from_room(expected_role)
    to_room_id = payload.get("toRoomId") or payload.get("to_room_id") or patient.get("roomId")
    return_room_id = payload.get("returnRoomId") or payload.get("return_room_id") or default_staff_from_room(expected_role)
    for label, room_id in {"fromRoomId": from_room_id, "toRoomId": to_room_id, "returnRoomId": return_room_id}.items():
        if not room_id or not str(room_id).startswith("R-") or room_id not in rooms_by_id:
            return {"error": "ROOM_NOT_FOUND", "message": f"{label} must be an existing Fullview room id."}
    duration = int(payload.get("durationSeconds") or payload.get("duration_seconds") or (8 if expected_role == "nurse" else 9))
    plan = {
        "kind": "staff-visit",
        "staffId": staff.get("staff_id") or staff.get("employeeId") or staff_id,
        "fromRoomId": from_room_id,
        "toRoomId": to_room_id,
        "returnRoomId": return_room_id,
        "patientId": payload.get("patient_id"),
        "durationSeconds": duration,
        "reason": payload.get("reason") or ("nurse execute_immediate" if expected_role == "nurse" else "doctor ward round"),
    }
    return {"plan": plan}


def default_staff_from_room(role):
    return "R-WARD-NURSE-STATION" if role == "nurse" else "R-WARD-DOCTOR-OFFICE"


def find_standard_staff(staff_id):
    if not staff_id:
        return None
    staff_id = str(staff_id)
    for member in read_json(STAFF_FILE).get("staff", []):
        normalized = normalize_staff_record(dict(member))
        ids = {
            normalized.get("id"),
            normalized.get("staffId"),
            normalized.get("staff_id"),
            normalized.get("employeeId"),
            normalized.get("employee_id"),
        }
        if staff_id in {item for item in ids if item}:
            return normalized
    return None


def append_core_event(event_id, patient_id, accepted, request, message="", event_type=None, snapshot_refresh=False, staff_move_plan=None):
    event_log = read_json(EVENT_LOG_FILE)
    event_seq = next_event_seq(event_log)
    response = {
        "accepted": accepted,
        "event_seq": event_seq,
        "eventSeq": event_seq,
        "event_id": event_id,
        "eventId": event_id,
        "patient_id": patient_id,
        "patientId": patient_id,
        "message": message,
        "eventType": event_type or event_id.lower(),
        "event_type": event_type or event_id.lower(),
    }
    if staff_move_plan:
        response["staffMovePlan"] = staff_move_plan
        response["staff_move_plan"] = {
            "kind": staff_move_plan.get("kind"),
            "staff_id": staff_move_plan.get("staffId"),
            "from_room_id": staff_move_plan.get("fromRoomId"),
            "to_room_id": staff_move_plan.get("toRoomId"),
            "return_room_id": staff_move_plan.get("returnRoomId"),
            "patient_id": staff_move_plan.get("patientId"),
            "duration_seconds": staff_move_plan.get("durationSeconds"),
            "reason": staff_move_plan.get("reason"),
        }
    if snapshot_refresh:
        response["snapshotRefresh"] = True
        response["snapshot_refresh"] = True
    append_event(event_log, response, request)
    write_json(EVENT_LOG_FILE, event_log)
    return response


def transfer_rule_for(source_department, target_department):
    route = (source_department, target_department)
    rules = {
        ("emergency", "icu"): ("TRANSFER_ED_TO_ICU", "icu_admission"),
        ("emergency", "ward"): ("TRANSFER_ED_TO_WARD", "ward_admission"),
        ("outpatient", "emergency"): ("TRANSFER_OP_TO_ED", "ed_handoff"),
        ("outpatient", "ward"): ("TRANSFER_OP_TO_WARD", "ward_admission"),
        ("outpatient", "icu"): ("OP_TO_ICU_MOVE", "icu_admission"),
        ("icu", "ward"): ("TRANSFER_ICU_TO_WARD", "ward_admission"),
        ("icu", "emergency"): ("ICU_TO_ED_MOVE", "ed_red_resus"),
        ("ward", "icu"): ("TRANSFER_WARD_TO_ICU", "icu_admission"),
    }
    return rules.get(route, (None, None))


def discharge_event_id_for_department(department_id):
    preferred = {
        "icu": "ICU_PATIENT_EXIT_HOSPITAL",
        "ward": "WARD_DISCHARGE_EXIT_HOSPITAL",
    }.get(department_id)
    allowed = allowed_event_ids_for_request(department_id, "discharge_request")
    if preferred in allowed:
        return preferred
    return next(iter(sorted(allowed)), preferred or "PATIENT_DISCHARGE")


def visible_discharge_target_room_id(movement, previous_room_id, rooms_by_id):
    via = [
        room_id for room_id in movement.get("via", [])
        if room_id in rooms_by_id
    ]
    if via:
        return via[-1]
    if previous_room_id in rooms_by_id:
        return previous_room_id
    return "discharge_desk" if "discharge_desk" in rooms_by_id else next(iter(rooms_by_id.keys()), previous_room_id)


def default_room_for_department(department_id):
    return {
        "outpatient": "registration_2",
        "emergency": "ed_registration",
        "icu": "icu_admission",
        "mdt": "mdt_lounge",
        "ward": "ward_admission",
    }.get(department_id, "ed_entrance")


def default_form_for_room(room):
    if room.get("kind") in CARE_ROOM_KINDS:
        return "bed"
    if room.get("kind") == "waiting":
        return "waiting"
    return "walking"


def recent_department_requests(department_id, limit=20):
    data = read_json_default(DEPARTMENT_REQUESTS_FILE, {"requests": []})
    rows = [
        row for row in data.get("requests", [])
        if row.get("department_id") == department_id or row.get("departmentId") == department_id
    ]
    return list(reversed(rows[-limit:]))


def log_department_request(department_id, request_type, idempotency_key, raw_payload, normalized_payload, status, core_response, error_code, trace_id):
    data = read_json_default(DEPARTMENT_REQUESTS_FILE, {"requests": []})
    request_id = f"dreq_{uuid.uuid4().hex[:12]}"
    created_at = utc_now_iso()
    record = {
        "request_id": request_id,
        "requestId": request_id,
        "department_id": department_id,
        "departmentId": department_id,
        "request_type": request_type,
        "requestType": request_type,
        "idempotency_key": idempotency_key or None,
        "idempotencyKey": idempotency_key or None,
        "raw_payload": raw_payload,
        "rawPayload": raw_payload,
        "normalized_payload": normalized_payload,
        "normalizedPayload": normalized_payload,
        "status": status,
        "core_response": core_response,
        "coreResponse": core_response,
        "error_code": error_code,
        "errorCode": error_code,
        "correlation_id": normalized_payload.get("correlation_id"),
        "correlationId": normalized_payload.get("correlation_id"),
        "trace_id": trace_id,
        "traceId": trace_id,
        "created_at": created_at,
        "createdAt": created_at,
    }
    data.setdefault("requests", []).append(record)
    data["requests"] = data["requests"][-500:]
    write_json(DEPARTMENT_REQUESTS_FILE, data)


def idempotency_key_for(department_id, request_type, idempotency_key):
    return f"{department_id}:{request_type}:{idempotency_key}"


def idempotency_lookup(department_id, request_type, idempotency_key):
    data = read_json_default(IDEMPOTENCY_FILE, {"keys": {}})
    return data.get("keys", {}).get(idempotency_key_for(department_id, request_type, idempotency_key))


def idempotency_store(department_id, request_type, idempotency_key, response):
    data = read_json_default(IDEMPOTENCY_FILE, {"keys": {}})
    data.setdefault("keys", {})[idempotency_key_for(department_id, request_type, idempotency_key)] = response
    write_json(IDEMPOTENCY_FILE, data)


def api_ok(data, trace_id=None):
    return {"ok": True, "data": data, "error": None, "trace_id": trace_id or new_trace_id()}


def api_error(code, message, details=None, trace_id=None):
    return {
        "ok": False,
        "data": None,
        "error": {"code": code, "message": message, "details": details or {}},
        "trace_id": trace_id or new_trace_id(),
    }


def movement_escort_roles(movement):
    return movement.get("escort_roles") or movement.get("escortRoles", [])


def movement_needs_porter(movement):
    return "porter" in movement_escort_roles(movement)


def should_queue_for_busy_consult(target_room, patient, patients):
    if not is_consult_room(target_room):
        return False
    patient_id = patient_identifier(patient)
    return any(
        patient_identifier(candidate) != patient_id
        and candidate.get("roomId") == target_room["id"]
        and candidate.get("form") != "hidden"
        and candidate.get("status") != "DISCHARGED"
        for candidate in patients
    )


def enqueue_consult_patient(room_state, room_id, patient, from_room_id, event_id):
    patient_id = patient_identifier(patient)
    if not patient_id:
        return
    state = room_state.setdefault("rooms", {}).setdefault(room_id, {"roomId": room_id, "room_id": room_id, "queue": []})
    queue = normalized_room_queue(state.get("queue", []))
    queue = [entry for entry in queue if entry.get("patientId") != patient_id]
    queue.append({
        "patientId": patient_id,
        "patient_id": patient_id,
        "fromRoomId": from_room_id,
        "from_room_id": from_room_id,
        "eventId": event_id,
        "event_id": event_id,
    })
    state["queue"] = queue


def process_consult_queue_after_departure(event_log, patients, room_state, rooms_by_id, source_room):
    if not is_consult_room(source_room):
        return
    if should_queue_for_busy_consult(source_room, {}, patients):
        return

    state = room_state.setdefault("rooms", {}).setdefault(source_room["id"], {"roomId": source_room["id"], "room_id": source_room["id"], "queue": []})
    queue = normalized_room_queue(state.get("queue", []))
    while queue:
        entry = queue.pop(0)
        patient = find_patient(patients, entry.get("patientId"))
        if not patient or patient.get("form") == "hidden" or patient.get("status") == "DISCHARGED":
            continue
        from_room_id = patient.get("roomId")
        if from_room_id == source_room["id"]:
            continue

        set_patient_room(patient, source_room["id"])
        set_patient_status(patient, "IN_CONSULTATION")
        set_patient_visual_form(patient, "consultation")
        set_patient_relative_position(
            patient,
            default_rel_x_for("consultation", source_room),
            default_rel_y_for("consultation", source_room),
        )

        event_seq = next_event_seq(event_log)
        response = {
            "accepted": True,
            "eventSeq": event_seq,
            "eventId": "CONSULT_QUEUE_ADVANCE",
            "patientId": patient_identifier(patient),
            "queued": False,
            "message": f"Queued patient {patient_identifier(patient)} advanced to {source_room['id']}.",
            "animation_plan": {
                "kind": "patient-move",
                "transport": "walking",
                "escort_roles": [],
                "equipment": [],
                "from_room_id": from_room_id,
                "to_room_id": source_room["id"],
                "requested_to_room_id": source_room["id"],
                "via_room_ids": [],
                "final_form": "consultation",
                "patient_form_during_move": "walking",
            },
            "animationPlan": {
                "kind": "patient-move",
                "transport": "walking",
                "escortRoles": [],
                "equipment": [],
                "fromRoomId": from_room_id,
                "toRoomId": source_room["id"],
                "requestedToRoomId": source_room["id"],
                "viaRoomIds": [],
                "finalForm": "consultation",
                "patientFormDuringMove": "walking",
            },
        }
        append_event(event_log, response, {
            "source": "consult-queue",
            "operatorId": "hospital-backend",
            "eventId": entry.get("eventId") or "CONSULT_QUEUE_ADVANCE",
            "patientId": patient_identifier(patient),
            "fromRoomId": from_room_id,
            "toRoomId": source_room["id"],
        })
        break

    state["queue"] = queue


def normalized_room_queue(queue):
    normalized = []
    for entry in queue or []:
        if isinstance(entry, dict):
            patient_id = entry.get("patientId") or entry.get("patient_id")
            if not patient_id:
                continue
            normalized.append({
                "patientId": patient_id,
                "patient_id": patient_id,
                "fromRoomId": entry.get("fromRoomId") or entry.get("from_room_id"),
                "from_room_id": entry.get("fromRoomId") or entry.get("from_room_id"),
                "eventId": entry.get("eventId") or entry.get("event_id"),
                "event_id": entry.get("eventId") or entry.get("event_id"),
            })
        elif entry:
            normalized.append({"patientId": entry, "patient_id": entry})
    return normalized


def remove_patient_from_all_queues(room_state, patient_id):
    if not patient_id:
        return
    for state in room_state.setdefault("rooms", {}).values():
        state["queue"] = [
            entry for entry in normalized_room_queue(state.get("queue", []))
            if entry.get("patientId") != patient_id
        ]


def choose_nearest_porter(staff_records, patient, rooms_by_id):
    patient_point = patient_room_point(patient, rooms_by_id)
    if not patient_point:
        return None

    candidates = []
    normalized_staff = [normalize_staff_record(dict(member)) for member in staff_records]
    assign_hallway_staff_positions(normalized_staff, rooms_by_id)
    for normalized in normalized_staff:
        role = normalized.get("role") or normalized.get("type")
        if role != "porter" or not normalized.get("available", True):
            continue
        porter_point = staff_world_point(normalized, rooms_by_id)
        if not porter_point:
            continue
        floor_penalty = 0 if porter_point["floor"] == patient_point["floor"] else 100000
        distance = squared_distance(porter_point, patient_point) + floor_penalty
        candidates.append({
            "distance": distance,
            "id": normalized.get("id"),
            "staffId": normalized.get("staff_id"),
            "name": normalized.get("name"),
            "point": porter_point,
        })

    if not candidates:
        return None
    candidates.sort(key=lambda candidate: candidate["distance"])
    return candidates[0]


def patient_room_point(patient, rooms_by_id):
    room = rooms_by_id.get(patient.get("roomId"))
    if not room:
        return None
    return room_tile_center(room)


def assign_hallway_staff_positions(staff, rooms_by_id):
    groups = {}
    for member in staff:
        if not is_hallway_staff(member):
            continue
        floor = int(member.get("floor_id") or member.get("floor") or nested_get(member, ["current_location", "floor_id"]) or 0)
        if not floor:
            continue
        groups.setdefault(floor, []).append(member)

    for floor, members in groups.items():
        candidates = hallway_candidates_for_floor(floor, rooms_by_id)
        if not candidates:
            continue
        ordered_members = sorted(members, key=lambda member: stable_hash(member.get("id") or member.get("staff_id") or "staff"))
        chosen = []
        for index, member in enumerate(ordered_members):
            anchor_room_id = member.get("hallway_anchor_room_id") or nested_get(member, ["current_location", "anchor_room_id"])
            if anchor_room_id and anchor_room_id in rooms_by_id:
                member["_hallway_anchor_point"] = hallway_point_for_room(rooms_by_id[anchor_room_id])
            point = choose_hallway_point_for_member(member, candidates, chosen, index)
            member.pop("_hallway_anchor_point", None)
            chosen.append(point)
            set_staff_hallway_point(member, point)


def is_hallway_staff(member):
    location = member.get("current_location") or {}
    return (member.get("location_type") or member.get("locationType") or location.get("location_type") or location.get("kind")) == "hallway"


def choose_hallway_point_for_member(member, candidates, chosen, index):
    anchor = member.get("_hallway_anchor_point")
    seed = member.get("hallway_seed") or member.get("staff_id") or member.get("id") or f"staff-{index}"
    if anchor:
        ordered = sorted(
            candidates,
            key=lambda point: squared_distance(point, anchor) + stable_hash(f"{seed}:{point['tileX']}:{point['tileY']}") / 10**18,
        )
    else:
        ordered = sorted(candidates, key=lambda point: stable_hash(f"{seed}:{point['tileX']}:{point['tileY']}"))

    min_distances = [4.4, 3.5, 2.7, 1.9, 0]
    for min_distance in min_distances:
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
    rooms = [room for room in rooms_by_id.values() if room.get("floor") == floor]
    if not rooms:
        return []
    raw = []
    for room in rooms:
        layout = room_layout(room)
        if layout["w"] <= 0 or layout["h"] <= 0:
            continue
        for x in frange(layout["x"] + 1.4, layout["x"] + layout["w"] - 1.4, 2.6):
            raw.append({"floor": floor, "tileX": x, "tileY": layout["y"] - 1.55})
            raw.append({"floor": floor, "tileX": x, "tileY": layout["y"] + layout["h"] + 1.55})
        for y in frange(layout["y"] + 1.4, layout["y"] + layout["h"] - 1.4, 2.6):
            raw.append({"floor": floor, "tileX": layout["x"] - 1.55, "tileY": y})
            raw.append({"floor": floor, "tileX": layout["x"] + layout["w"] + 1.55, "tileY": y})

    bounds = floor_bounds(rooms)
    deduped = {}
    for point in raw:
        if not point_in_bounds(point, bounds):
            continue
        if point_inside_any_room(point, rooms, padding=0.9):
            continue
        key = (round(point["tileX"], 1), round(point["tileY"], 1))
        deduped[key] = world_point(floor, key[0], key[1])
    return list(deduped.values())


def frange(start, stop, step):
    value = start
    while value <= stop:
        yield round(value, 3)
        value += step


def floor_bounds(rooms):
    layouts = [room_layout(room) for room in rooms]
    min_x = min(layout["x"] for layout in layouts) - 2.6
    min_y = min(layout["y"] for layout in layouts) - 2.6
    max_x = max(layout["x"] + layout["w"] for layout in layouts) + 2.6
    max_y = max(layout["y"] + layout["h"] for layout in layouts) + 0.4
    return {"minX": min_x, "minY": min_y, "maxX": max_x, "maxY": max_y}


def point_in_bounds(point, bounds):
    return bounds["minX"] <= point["tileX"] <= bounds["maxX"] and bounds["minY"] <= point["tileY"] <= bounds["maxY"]


def point_inside_any_room(point, rooms, padding=0):
    return any(point_inside_room(point, room_layout(room), padding) for room in rooms)


def point_inside_room(point, layout, padding):
    return (
        layout["x"] - padding <= point["tileX"] <= layout["x"] + layout["w"] + padding
        and layout["y"] - padding <= point["tileY"] <= layout["y"] + layout["h"] + padding
    )


def world_point(floor, tile_x, tile_y):
    return {
        "floor": floor,
        "floorId": floor,
        "tileX": round(tile_x, 2),
        "tileY": round(tile_y, 2),
        "x": round(tile_x * TILE_SIZE, 2),
        "y": round(tile_y * TILE_SIZE, 2),
    }


def tile_distance(a, b):
    return ((a["tileX"] - b["tileX"]) ** 2 + (a["tileY"] - b["tileY"]) ** 2) ** 0.5


def stable_hash(value):
    return int(hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:16], 16)


def staff_world_point(member, rooms_by_id):
    location = member.get("current_location") or {}
    floor = int(location.get("floor_id") or member.get("floor_id") or member.get("floor") or 0)
    tile_x = location.get("tile_x") or member.get("tile_x")
    tile_y = location.get("tile_y") or member.get("tile_y")
    if floor and tile_x is not None and tile_y is not None:
        return {
            "floor": floor,
            "floorId": floor,
            "tileX": float(tile_x),
            "tileY": float(tile_y),
            "x": float(tile_x) * TILE_SIZE,
            "y": float(tile_y) * TILE_SIZE,
        }

    x = location.get("x") if location.get("x") is not None else member.get("x")
    y = location.get("y") if location.get("y") is not None else member.get("y")
    if floor and x is not None and y is not None:
        return {
            "floor": floor,
            "floorId": floor,
            "tileX": float(x) / TILE_SIZE,
            "tileY": float(y) / TILE_SIZE,
            "x": float(x),
            "y": float(y),
        }

    room_id = member.get("roomId") or member.get("room_id") or location.get("room_id")
    room = rooms_by_id.get(room_id)
    if not room:
        return None
    rel_x = float(member.get("relX", member.get("rel_x", 0.5)) or 0.5)
    rel_y = float(member.get("relY", member.get("rel_y", 0.58)) or 0.58)
    layout = room_layout(room)
    return {
        "floor": room["floor"],
        "floorId": room["floor"],
        "tileX": layout["x"] + layout["w"] * rel_x,
        "tileY": layout["y"] + layout["h"] * rel_y,
        "x": (layout["x"] + layout["w"] * rel_x) * TILE_SIZE,
        "y": (layout["y"] + layout["h"] * rel_y) * TILE_SIZE,
    }


def room_tile_center(room):
    layout = room_layout(room)
    return {
        "floor": room["floor"],
        "floorId": room["floor"],
        "tileX": layout["x"] + layout["w"] / 2,
        "tileY": layout["y"] + layout["h"] / 2,
        "x": (layout["x"] + layout["w"] / 2) * TILE_SIZE,
        "y": (layout["y"] + layout["h"] / 2) * TILE_SIZE,
    }


def room_layout(room):
    layout = room.get("layout") or {}
    return {
        "x": float(layout.get("x") if layout.get("x") is not None else room.get("x", 0)),
        "y": float(layout.get("y") if layout.get("y") is not None else room.get("y", 0)),
        "w": float(layout.get("w") if layout.get("w") is not None else room.get("w", 0)),
        "h": float(layout.get("h") if layout.get("h") is not None else room.get("h", 0)),
    }


def squared_distance(a, b):
    dx = a["tileX"] - b["tileX"]
    dy = a["tileY"] - b["tileY"]
    return dx * dx + dy * dy


def hallway_point_for_room(room):
    layout = room_layout(room)
    tile_x = layout["x"] + layout["w"] / 2
    if layout["y"] >= 26:
        tile_y = layout["y"] - 1.4
    else:
        tile_y = layout["y"] + layout["h"] + 1.4
    tile_x = max(3.5, min(64.5, tile_x))
    tile_y = max(3.5, min(36.5, tile_y))
    floor = room["floor"]
    return {
        "floor": floor,
        "floorId": floor,
        "tileX": round(tile_x, 2),
        "tileY": round(tile_y, 2),
        "x": round(tile_x * TILE_SIZE, 2),
        "y": round(tile_y * TILE_SIZE, 2),
    }


def update_porter_after_transfer(staff_data, selected_porter, target_room):
    if not selected_porter:
        return None
    return_point = hallway_point_for_room(target_room)
    porter_id = selected_porter.get("id")
    porter_staff_id = selected_porter.get("staffId")
    for member in staff_data.get("staff", []):
        member_id = member.get("id") or member.get("local_person_id")
        staff_id = member.get("staff_id") or member.get("employee_id") or member.get("employeeId")
        if member_id != porter_id and staff_id != porter_staff_id:
            continue
        member["roomId"] = None
        member["room_id"] = None
        member["locationType"] = "hallway"
        member["location_type"] = "hallway"
        member["floor"] = return_point["floor"]
        member["floor_id"] = return_point["floor"]
        member.pop("tile_x", None)
        member.pop("tile_y", None)
        member.pop("x", None)
        member.pop("y", None)
        member["hallway_anchor_room_id"] = target_room["id"]
        member["hallway_seed"] = f"{staff_id or member_id}:{target_room['id']}"
        member["pose"] = "walking"
        member["current_location"] = {
            "kind": "hallway",
            "location_type": "hallway",
            "floor_id": return_point["floor"],
            "anchor_room_id": target_room["id"],
        }
        member["visual"] = {
            **(member.get("visual") or {}),
            "pose": "walking",
        }
        member.setdefault("availability", {})["available"] = True
        member["available"] = True
        return return_point
    return return_point


def resolve_final_target_room(movement, requested_target_room, room_state, rooms_by_id):
    final_form = movement.get("final_form") or movement.get("finalForm", "walking")
    if final_form != "bed":
        return requested_target_room
    if is_care_room(requested_target_room):
        return requested_target_room
    requested_id = requested_target_room.get("id")
    if requested_id == "ward_admission":
        return first_available_care_room("ward", room_state, rooms_by_id)
    if requested_id == "icu_admission":
        return first_available_care_room("icu", room_state, rooms_by_id, preferred_ids=["icu_beds_a", "icu_beds_b", "icu_isolation"])
    return requested_target_room


def first_available_care_room(kind, room_state, rooms_by_id, preferred_ids=None):
    rooms = []
    if preferred_ids:
        rooms.extend([rooms_by_id[room_id] for room_id in preferred_ids if room_id in rooms_by_id])
    rooms.extend([
        room for room in rooms_by_id.values()
        if room.get("kind") == kind and room not in rooms and room.get("capacityBeds", 0) > 0
    ])
    for room in rooms:
        state = room_state.get("rooms", {}).get(room["id"], {})
        bed_ids = state.get("bedIds") or state.get("bed_ids") or room.get("bedIds", [])
        capacity = max(int(state.get("capacityBeds", 0) or 0), int(room.get("capacityBeds", 0) or 0), len(bed_ids))
        assignments = normalize_bed_assignments(state.get("bedAssignments", []), bed_ids)
        if capacity > len(assignments):
            return room
    return None


def resolved_via_rooms(movement, requested_target_room_id, final_target_room_id):
    via = list(movement.get("via", []))
    if requested_target_room_id != final_target_room_id and requested_target_room_id not in via:
        via.append(requested_target_room_id)
    return via


def handle_admit_patient(request):
    department = str(request.get("department") or request.get("department_id") or request.get("kind") or "").strip().lower()
    if department in {"er", "ed"}:
        department = "emergency"
    if department in {"op", "outpatient"}:
        department = "outpatient"
    if department not in {"emergency", "outpatient"}:
        return {
            "accepted": False,
            "reasonCode": "UNSUPPORTED_ENTRY_DEPARTMENT",
            "message": "New entry patients must enter through emergency or outpatient.",
        }

    patients_data = read_json(PATIENTS_FILE)
    staff_data = read_json(STAFF_FILE)
    room_state = read_json(ROOM_STATE_FILE)
    map_config = read_json(MAP_CONFIG)
    _, rooms = normalize_map(map_config)
    rooms_by_id = {room["id"]: room for room in rooms}
    patients = [normalize_patient_record(patient) for patient in patients_data.get("patients", [])]
    staff = [normalize_staff_record(member) for member in staff_data.get("staff", [])]
    sanitize_patient_staff_references(patients, staff)
    recompute_room_state(room_state, patients, rooms_by_id)

    patient = make_entry_patient(department, patients, rooms_by_id)
    patients.append(patient)
    sanitize_patient_staff_references(patients, staff)
    patients_data["patients"] = patients
    write_json(PATIENTS_FILE, patients_data)
    write_json(ROOM_STATE_FILE, room_state)

    move_request = intake_move_request(department, patient, rooms_by_id, patients, request)
    move_response = handle_move_request(move_request)
    created_patient = find_patient(
        [normalize_patient_record(item) for item in read_json(PATIENTS_FILE).get("patients", [])],
        patient_identifier(patient),
    )
    return {
        "accepted": bool(move_response.get("accepted")),
        "patient": created_patient or patient,
        "move": move_response,
        "eventSeq": move_response.get("eventSeq"),
        "event_seq": move_response.get("event_seq") or move_response.get("eventSeq"),
        "reasonCode": move_response.get("reasonCode"),
        "message": move_response.get("message"),
    }


def make_entry_patient(department, patients, rooms_by_id):
    if department == "emergency":
        patient_id = next_patient_id(patients, "P-ER")
        sequence = int(patient_id.rsplit("-", 1)[-1])
        room_id = "ed_registration"
        name, symptoms = entry_patient_profile("emergency", sequence)
        status = "REGISTERED"
        color = "#c85f67" if sequence % 3 == 0 else "#5f8ec9"
    else:
        patient_id = next_patient_id(patients, "P-OP")
        sequence = int(patient_id.rsplit("-", 1)[-1])
        room_id = "registration_2"
        name, symptoms = entry_patient_profile("outpatient", sequence)
        status = "REGISTERED"
        color = "#7899c6" if sequence % 2 == 0 else "#8f7ed0"

    local_id = f"intake-{department}-{sequence:03d}"
    patient = {
        "id": local_id,
        "local_person_id": local_id,
        "patientId": patient_id,
        "patient_id": patient_id,
        "type": "patient",
        "name": name,
        "gender": "female" if sequence % 2 else "male",
        "department": DEPARTMENT_DISPLAY[department],
        "department_id": department,
        "symptoms": symptoms,
        "status": status,
        "roomId": room_id,
        "room_id": room_id,
        "current_location": {"room_id": room_id},
        "home_bed": {},
        "form": "walking",
        "baseForm": "walking",
        "base_form": "walking",
        "relX": 0.5,
        "relY": 0.58,
        "rel_x": 0.5,
        "rel_y": 0.58,
        "color": color,
        "skin": None,
        "blanket": None,
        "phase": 0,
        "clinical": {
            "status": status,
            "symptoms": symptoms,
            "care_phase": "entry_triage",
            "ctas_level": None,
            "active_problems": [],
            "active_risks": [],
            "latest_interventions": [],
        },
        "visual": {
            "form": "walking",
            "base_form": "walking",
            "rel_x": 0.5,
            "rel_y": 0.58,
            "color": color,
            "skin": None,
            "blanket": None,
        },
    }
    return normalize_patient_record(patient)


def intake_move_request(department, patient, rooms_by_id, patients, request):
    if department == "emergency":
        target_room_id = first_triage_target(
            patients,
            primary_room_id="ed_triage",
            waiting_room_id="ed_waiting",
            primary_limit=2,
        )
        event_id = "ED_REGISTRATION_TO_TRIAGE_OR_WAITING"
    else:
        target_room_id = first_triage_target(
            patients,
            primary_room_id="triage_2",
            waiting_room_id="outpatient_waiting",
            primary_limit=2,
        )
        event_id = "OP_REGISTRATION_TO_TRIAGE_OR_WAITING"

    return {
        "requestId": request.get("requestId") or request.get("request_id") or f"intake-{patient_identifier(patient)}",
        "source": request.get("source") or "console-intake",
        "operatorId": request.get("operatorId") or request.get("operator_id") or "manual-admin",
        "eventId": event_id,
        "patientId": patient_identifier(patient),
        "fromRoomId": patient.get("roomId"),
        "toRoomId": target_room_id,
        "context": {
            "reason": request.get("reason") or request.get("context", {}).get("reason") or "new patient intake triage",
            "entryDepartment": department,
        },
    }


def first_triage_target(patients, primary_room_id, waiting_room_id, primary_limit):
    active_primary = [
        patient for patient in patients
        if patient.get("roomId") == primary_room_id and patient.get("form") != "hidden" and patient.get("status") != "DISCHARGED"
    ]
    return primary_room_id if len(active_primary) < primary_limit else waiting_room_id


def next_patient_id(patients, prefix):
    max_number = 0
    full_prefix = f"{prefix}-"
    for patient in patients:
        patient_id = patient_identifier(patient) or ""
        if not patient_id.startswith(full_prefix):
            continue
        tail = patient_id.removeprefix(full_prefix)
        if tail.isdigit():
            max_number = max(max_number, int(tail))
    return f"{prefix}-{max_number + 1:03d}"


def entry_patient_profile(department, sequence):
    emergency_profiles = [
        ("陈安然", "胸闷伴轻度呼吸困难"),
        ("Lucas Bennett", "右下腹痛，需急诊分诊"),
        ("周明", "发热寒战，疑似感染"),
        ("Nora Evans", "头晕乏力，血压偏低"),
        ("林佳怡", "外伤后疼痛，等待急诊评估"),
    ]
    outpatient_profiles = [
        ("王若溪", "慢性咳嗽复诊"),
        ("Mason Clark", "高血压用药随访"),
        ("赵子涵", "腹痛门诊初诊"),
        ("Emma Rivera", "皮疹与低热，需门诊分诊"),
        ("刘亦辰", "术后复查与检验申请"),
    ]
    profiles = emergency_profiles if department == "emergency" else outpatient_profiles
    return profiles[(sequence - 1) % len(profiles)]


def validate_move_request(request, patient, rule, rooms_by_id, room_state):
    if not request.get("eventId"):
        return error("MISSING_EVENT_ID", "eventId is required.")
    if not rule:
        return error("RULE_NOT_FOUND", f"No movement rule found for {request.get('eventId')}.")
    if not patient:
        return error("PATIENT_NOT_FOUND", f"No patient found for {request.get('patientId')}.")
    if not request.get("fromRoomId") or patient.get("roomId") != request.get("fromRoomId"):
        return error("PATIENT_ROOM_MISMATCH", "Patient current room does not match fromRoomId.")
    if request.get("toRoomId") not in rooms_by_id:
        return error("TARGET_ROOM_NOT_FOUND", f"Unknown target room: {request.get('toRoomId')}.")
    if not target_allowed(rule.get("movement", {}), request.get("toRoomId")):
        return error("TARGET_NOT_ALLOWED", "Target room is not allowed by the selected movement rule.")
    symbolic_error = validate_symbolic_target(rule.get("movement", {}), request.get("toRoomId"), patient, rooms_by_id)
    if symbolic_error:
        return symbolic_error
    if not source_allowed(rule.get("movement", {}), request.get("fromRoomId")):
        return error("SOURCE_NOT_ALLOWED", "Source room is not allowed by the selected movement rule.")
    symbolic_source_error = validate_symbolic_source(rule.get("movement", {}), request.get("fromRoomId"), patient, rooms_by_id)
    if symbolic_source_error:
        return symbolic_source_error

    target_room = rooms_by_id[request.get("toRoomId")]
    if is_care_room(target_room):
        state = room_state.get("rooms", {}).get(target_room["id"], {})
        assignments = state.get("bedAssignments", [])
        if patient_identifier(patient) not in assignment_patient_ids(assignments) and state.get("capacityBeds", 0) <= len(assignments):
            return error("NO_BED_AVAILABLE", "Target care room has no available bed.")

    movement = rule.get("movement", {})
    if movement.get("escort_required") or movement.get("escortRequired"):
        missing = [
            role for role in (movement.get("escort_roles") or movement.get("escortRoles", []))
            if room_state.get("escortResources", {}).get(role, {}).get("available", 0) <= 0
        ]
        if missing:
            return error("ESCORT_UNAVAILABLE", f"Missing escort resource: {', '.join(missing)}.")

    return None


def validate_symbolic_target(movement, to_room_id, patient, rooms_by_id):
    target = movement.get("to")
    targets = target if isinstance(target, list) else [target]
    target_room = rooms_by_id.get(to_room_id)
    if not target_room:
        return None

    if "source_ward_room" in targets or "source_icu_bed_room" in targets:
        if patient.get("bedRoomId") != to_room_id:
            return error("TARGET_NOT_ASSIGNED_BED", "Return target must be the patient's assigned bed room.")
    if "target_ward_room" in targets and target_room.get("kind") != "ward":
        return error("TARGET_NOT_WARD_ROOM", "Target must be an inpatient ward room.")
    return None


def validate_symbolic_source(movement, from_room_id, patient, rooms_by_id):
    source = movement.get("from")
    sources = source if isinstance(source, list) else [source]
    room = rooms_by_id.get(from_room_id)
    if not room:
        return None

    checks = {
        "current_ward_room": lambda: room.get("kind") == "ward",
        "source_ward_room": lambda: patient.get("bedRoomId") == from_room_id,
        "current_icu_bed_room": lambda: from_room_id in {"icu_beds_a", "icu_beds_b", "icu_isolation"},
        "source_icu_bed_room": lambda: patient.get("bedRoomId") == from_room_id,
        "current_icu_exam_room": lambda: from_room_id in {"intervention_bay", "icu_equipment"},
        "current_ed_room": lambda: room.get("floor") == 1,
        "current_ed_bed_room": lambda: room.get("floor") == 1 and room.get("capacityBeds", 0) > 0,
        "current_op_room": lambda: room.get("floor") == 2,
        "current_consult_room": lambda: room.get("kind") in {"consultation", "internal_medicine", "surgery", "pediatrics", "fever", "obgyn"},
        "current_room": lambda: True,
    }
    for source_id in sources:
        check = checks.get(source_id)
        if check and not check():
            return error("SOURCE_SYMBOLIC_MISMATCH", f"Patient is not in a valid source room for {source_id}.")
    return None


def append_event(event_log, response, request):
    event_log["lastSeq"] = response["eventSeq"]
    event = {
        "event_seq": response["eventSeq"],
        "eventSeq": response["eventSeq"],
        "accepted": response["accepted"],
        "event_id": response.get("event_id") or response.get("eventId"),
        "eventId": response.get("eventId"),
        "patient_id": response.get("patient_id") or response.get("patientId"),
        "patientId": response.get("patientId"),
        "request": request,
    }
    if response.get("animationPlan"):
        event["animation_plan"] = response.get("animation_plan") or response["animationPlan"]
        event["animationPlan"] = response["animationPlan"]
    if response.get("staffMovePlan"):
        event["staffMovePlan"] = response["staffMovePlan"]
        event["staff_move_plan"] = response.get("staff_move_plan")
    if response.get("snapshotRefresh") or response.get("snapshot_refresh"):
        event["snapshotRefresh"] = True
        event["snapshot_refresh"] = True
    if response.get("reasonCode"):
        event["reasonCode"] = response["reasonCode"]
        event["message"] = response.get("message", "")
    event_log.setdefault("events", []).append(event)


def find_rule(event_id):
    if not event_id:
        return None
    index = read_json(RULES_DIR / "index.json")
    for category in index.get("categories", []):
        rules_path = RULES_DIR / category.get("file", "")
        if not rules_path.exists():
            continue
        for rule in read_json(rules_path).get("rules", []):
            if rule.get("event_id") == event_id or rule.get("eventId") == event_id:
                return rule
    return None


def find_patient(patients, patient_id):
    return next((
        patient for patient in patients
        if patient_identifier(patient) == patient_id or patient.get("patientId") == patient_id or patient.get("id") == patient_id
    ), None)


def source_allowed(movement, room_id):
    source = movement.get("from")
    if source is None:
        return True
    if isinstance(source, list):
        return room_id in source or any(is_symbolic_room(value) for value in source)
    return room_id == source or is_symbolic_room(source) or source == "outside"


def target_allowed(movement, room_id):
    target = movement.get("to")
    if target is None:
        return True
    if isinstance(target, list):
        return room_id in target or any(is_symbolic_room(value) for value in target)
    return room_id == target or is_symbolic_room(target) or target == "exit"


def is_symbolic_room(value):
    return isinstance(value, str) and (
        value.startswith("current_") or
        value.startswith("source_") or
        value.startswith("target_")
    )


def normalize_move_request(request):
    if not isinstance(request, dict):
        return {}
    normalized = dict(request)
    normalized.setdefault("requestId", request.get("request_id"))
    normalized.setdefault("operatorId", request.get("operator_id"))
    normalized.setdefault("eventId", request.get("event_id"))
    normalized.setdefault("patientId", request.get("patient_id"))
    normalized.setdefault("fromRoomId", request.get("from_room_id"))
    normalized.setdefault("toRoomId", request.get("to_room_id"))
    return normalized


def normalize_patient_record(patient):
    patient_id = patient.get("patient_id") or patient.get("patientId") or patient.get("id")
    local_id = patient.get("local_person_id") or patient.get("id") or patient_id
    room_id = patient.get("room_id") or patient.get("roomId") or nested_get(patient, ["current_location", "room_id"])
    bed_room_id = (
        patient.get("bed_room_id") or
        patient.get("bedRoomId") or
        nested_get(patient, ["home_bed", "room_id"])
    )
    bed_id = patient.get("bed_id") or patient.get("bedId") or nested_get(patient, ["home_bed", "bed_id"])
    status = patient.get("status") or nested_get(patient, ["clinical", "status"]) or "ARRIVED"
    visual = dict(patient.get("visual") or {})
    clinical = dict(patient.get("clinical") or {})
    location = dict(patient.get("current_location") or {})
    home_bed = dict(patient.get("home_bed") or {})

    patient["id"] = local_id
    patient["patient_id"] = patient_id
    patient["patientId"] = patient_id
    patient["type"] = patient.get("type") or "patient"
    patient["status"] = status
    patient["department_id"] = patient.get("department_id") or department_id_from_name(patient.get("department"))
    patient["department"] = patient.get("department") or DEPARTMENT_DISPLAY.get(patient["department_id"], patient["department_id"])
    patient["symptoms"] = patient.get("symptoms") or clinical.get("symptoms") or ""
    if room_id:
        patient["room_id"] = room_id
        patient["roomId"] = room_id
        location["room_id"] = room_id
    if bed_room_id:
        patient["bed_room_id"] = bed_room_id
        patient["bedRoomId"] = bed_room_id
        home_bed["room_id"] = bed_room_id
    if bed_id:
        patient["bed_id"] = bed_id
        patient["bedId"] = bed_id
        home_bed["bed_id"] = bed_id

    clinical.setdefault("status", status)
    clinical.setdefault("symptoms", patient.get("symptoms", ""))
    clinical.setdefault("care_phase", patient.get("care_phase"))
    clinical.setdefault("active_problems", [])
    clinical.setdefault("active_risks", [])
    clinical.setdefault("latest_interventions", [])
    visual.setdefault("form", patient.get("form", "walking"))
    visual.setdefault("base_form", patient.get("base_form") or patient.get("baseForm", visual["form"]))
    visual.setdefault("rel_x", patient.get("rel_x", patient.get("relX", 0.5)))
    visual.setdefault("rel_y", patient.get("rel_y", patient.get("relY", 0.58)))
    visual.setdefault("color", patient.get("color"))
    visual.setdefault("skin", patient.get("skin"))
    visual.setdefault("blanket", patient.get("blanket"))

    patient["clinical"] = clinical
    patient["current_location"] = location
    patient["home_bed"] = home_bed if bed_room_id or bed_id else home_bed
    patient["visual"] = visual
    patient["form"] = visual["form"]
    patient["baseForm"] = visual["base_form"]
    patient["base_form"] = visual["base_form"]
    patient["relX"] = visual["rel_x"]
    patient["relY"] = visual["rel_y"]
    patient["rel_x"] = visual["rel_x"]
    patient["rel_y"] = visual["rel_y"]
    return patient


def sanitize_patient_staff_references(patients, staff):
    staff_by_id = {}
    doctors_by_room = {}
    for member in staff:
        identifiers = [
            member.get("id"),
            member.get("staff_id"),
            member.get("employee_id"),
            member.get("employeeId"),
        ]
        for identifier in identifiers:
            if identifier:
                staff_by_id[identifier] = member
        role = member.get("role") or member.get("type")
        room_id = member.get("roomId") or member.get("room_id")
        if role == "doctor" and room_id:
            doctors_by_room.setdefault(room_id, []).append(member)

    for patient in patients:
        doctor_id = patient.get("doctorProfileId") or patient.get("doctor_profile_id")
        if doctor_id and doctor_id in staff_by_id:
            doctor = staff_by_id[doctor_id]
            patient["doctorProfileId"] = doctor.get("id") or doctor.get("staff_id")
            patient["doctor_profile_id"] = patient["doctorProfileId"]
            if doctor.get("gender"):
                patient["doctorGender"] = doctor["gender"]
                patient["doctor_gender"] = doctor["gender"]
            continue

        room_id = patient.get("roomId") or patient.get("room_id")
        replacement = doctors_by_room.get(room_id, [None])[0]
        if replacement and patient.get("form") == "consultation":
            patient["doctorProfileId"] = replacement.get("id") or replacement.get("staff_id")
            patient["doctor_profile_id"] = patient["doctorProfileId"]
            if replacement.get("gender"):
                patient["doctorGender"] = replacement["gender"]
                patient["doctor_gender"] = replacement["gender"]
        else:
            remove_patient_doctor_reference(patient)


def remove_patient_doctor_reference(patient):
    for key in ["doctorProfileId", "doctor_profile_id", "doctorGender", "doctor_gender"]:
        patient.pop(key, None)


def normalize_staff_record(member):
    staff_id = member.get("staff_id") or member.get("employee_id") or member.get("employeeId") or member.get("id")
    local_id = member.get("local_person_id") or member.get("id") or staff_id
    room_id = member.get("room_id") or member.get("roomId") or nested_get(member, ["current_location", "room_id"])
    visual = dict(member.get("visual") or {})
    location = dict(member.get("current_location") or {})
    availability = dict(member.get("availability") or {})
    location_type = member.get("location_type") or member.get("locationType") or location.get("location_type") or location.get("kind")

    member["id"] = local_id
    member["staff_id"] = staff_id
    member["employee_id"] = staff_id
    member["employeeId"] = staff_id
    member["provider_id"] = member.get("provider_id") or staff_id
    member["department_id"] = member.get("department_id") or department_id_from_name(member.get("department"))
    member["department"] = member.get("department") or DEPARTMENT_DISPLAY.get(member["department_id"], member["department_id"])
    if room_id:
        member["room_id"] = room_id
        member["roomId"] = room_id
        location["room_id"] = room_id
    elif location_type == "hallway":
        floor_id = int(location.get("floor_id") or member.get("floor_id") or member.get("floor") or 0)
        tile_x = location.get("tile_x") if location.get("tile_x") is not None else member.get("tile_x")
        tile_y = location.get("tile_y") if location.get("tile_y") is not None else member.get("tile_y")
        x = location.get("x") if location.get("x") is not None else member.get("x")
        y = location.get("y") if location.get("y") is not None else member.get("y")
        if tile_x is None and x is not None:
            tile_x = float(x) / TILE_SIZE
        if tile_y is None and y is not None:
            tile_y = float(y) / TILE_SIZE
        if x is None and tile_x is not None:
            x = float(tile_x) * TILE_SIZE
        if y is None and tile_y is not None:
            y = float(tile_y) * TILE_SIZE
        member["room_id"] = None
        member["roomId"] = None
        member["location_type"] = "hallway"
        member["locationType"] = "hallway"
        member["floor_id"] = floor_id
        member["floor"] = floor_id
        if tile_x is not None:
            member["tile_x"] = float(tile_x)
        if tile_y is not None:
            member["tile_y"] = float(tile_y)
        if x is not None:
            member["x"] = float(x)
        if y is not None:
            member["y"] = float(y)
        location_payload = {
            "kind": "hallway",
            "location_type": "hallway",
            "floor_id": floor_id,
        }
        if tile_x is not None:
            location_payload["tile_x"] = member["tile_x"]
        if tile_y is not None:
            location_payload["tile_y"] = member["tile_y"]
        if x is not None:
            location_payload["x"] = member["x"]
        if y is not None:
            location_payload["y"] = member["y"]
        if member.get("hallway_anchor_room_id"):
            location_payload["anchor_room_id"] = member["hallway_anchor_room_id"]
        location.update(location_payload)

    visual.setdefault("pose", member.get("pose", "standing"))
    visual.setdefault("rel_x", member.get("rel_x", member.get("relX", 0.5)))
    visual.setdefault("rel_y", member.get("rel_y", member.get("relY", 0.58)))
    availability.setdefault("available", bool(member.get("available", True)))

    member["current_location"] = location
    member["visual"] = visual
    member["availability"] = availability
    member["pose"] = visual["pose"]
    member["relX"] = visual["rel_x"]
    member["relY"] = visual["rel_y"]
    member["rel_x"] = visual["rel_x"]
    member["rel_y"] = visual["rel_y"]
    member["available"] = availability["available"]
    return member


def nested_get(source, keys):
    value = source
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def department_id_from_name(name):
    raw = str(name or "").strip().lower()
    if not raw:
        return "hospital"
    if "emergency" in raw or raw in {"er", "ed"}:
        return "emergency"
    if "outpatient" in raw or "registration" in raw or "triage" in raw:
        return "outpatient"
    if "lab" in raw:
        return "laboratory"
    if "pharmacy" in raw:
        return "pharmacy"
    if "icu" in raw:
        return "icu"
    if "ward" in raw or "inpatient" in raw:
        return "ward"
    if "mdt" in raw or "imaging review" in raw:
        return "mdt"
    if "internal medicine" in raw or "surgery" in raw or "pediatrics" in raw:
        return "outpatient"
    return raw.replace(" ", "_")


def department_id_for_room(room, floor_id):
    kind = room.get("kind", "")
    if kind in ROOM_DEPARTMENT_BY_KIND:
        return ROOM_DEPARTMENT_BY_KIND[kind]
    if room.get("id") in {"lab_2"}:
        return "laboratory"
    if room.get("id") in {"pharmacy_2"}:
        return "pharmacy"
    return FLOOR_DEPARTMENTS.get(floor_id, "hospital")


def set_patient_room(patient, room_id):
    patient["roomId"] = room_id
    patient["room_id"] = room_id
    patient.setdefault("current_location", {})["room_id"] = room_id


def set_patient_status(patient, status):
    patient["status"] = status
    patient.setdefault("clinical", {})["status"] = status


def set_patient_visual_form(patient, form):
    patient["form"] = form
    patient.setdefault("visual", {})["form"] = form


def set_patient_relative_position(patient, rel_x, rel_y):
    patient["relX"] = rel_x
    patient["relY"] = rel_y
    patient["rel_x"] = rel_x
    patient["rel_y"] = rel_y
    patient.setdefault("visual", {})["rel_x"] = rel_x
    patient.setdefault("visual", {})["rel_y"] = rel_y


def normalize_map(map_config):
    floors = []
    rooms = []
    floor_counts = {}
    for floor in map_config.get("floors", []):
        floor_id = int(floor.get("id"))
        floor_room_ids = []
        for room in floor.get("rooms", []):
            floor_counts[floor_id] = floor_counts.get(floor_id, 0) + 1
            room_id = room.get("id")
            items = room.get("items", [])
            capacity_beds = room.get("maxBeds") if room.get("maxBeds") is not None else count_items(items, "bed")
            department_id = room.get("department_id") or department_id_for_room(room, floor_id)
            room_code = room.get("roomCode") or room.get("display_room_id") or f"{floor_id}F-Room{floor_counts[floor_id]}"
            normalized = {
                "id": room_id,
                "room_id": room_id,
                "roomId": room_id,
                "roomCode": room_code,
                "display_room_id": room_code,
                "floor": floor_id,
                "floor_id": floor_id,
                "department_id": department_id,
                "kind": room.get("kind", "room"),
                "label": room.get("label", room_id),
                "display_name": room.get("display_name") or room.get("label", room_id),
                "protected": bool(room.get("protected") or room.get("kind") == "elevator"),
                "features": summarize_items(items),
                "capacityBeds": capacity_beds,
                "capacity_beds": capacity_beds,
                "bedIds": bed_ids_for_room(room_id, items, capacity_beds),
                "bed_ids": bed_ids_for_room(room_id, items, capacity_beds),
                "layout": {
                    "x": room.get("x"),
                    "y": room.get("y"),
                    "w": room.get("w"),
                    "h": room.get("h"),
                },
            }
            rooms.append(normalized)
            floor_room_ids.append(room_id)
        floors.append({
            "id": floor_id,
            "floor_id": floor_id,
            "label": floor.get("label", f"{floor_id}F"),
            "shortLabel": floor.get("shortLabel", f"{floor_id}F"),
            "short_label": floor.get("shortLabel", f"{floor_id}F"),
            "departmentKinds": floor.get("departmentKinds", []),
            "department_kinds": floor.get("departmentKinds", []),
            "rooms": floor_room_ids,
        })
    return floors, rooms


def decorate_room(room, patients, staff, room_state):
    state = room_state.get("rooms", {}).get(room["id"], {})
    patients_by_id = {patient_identifier(patient): patient for patient in patients if patient_identifier(patient)}
    room_patients = [patient for patient in patients if patient.get("roomId") == room["id"]]
    room_staff = [member for member in staff if member.get("roomId") == room["id"]]
    return {
        **room,
        "patients": room_patients,
        "staff": room_staff,
        "patientCount": len(room_patients),
        "patient_count": len(room_patients),
        "staffCount": len(room_staff),
        "staff_count": len(room_staff),
        "occupiedBeds": state.get("occupiedBeds", 0),
        "occupied_beds": state.get("occupiedBeds", 0),
        "availableBeds": max(0, state.get("capacityBeds", room.get("capacityBeds", 0)) - state.get("occupiedBeds", 0)),
        "available_beds": max(0, state.get("capacityBeds", room.get("capacityBeds", 0)) - state.get("occupiedBeds", 0)),
        "bedAssignments": state.get("bedAssignments", []),
        "bed_assignments": state.get("bedAssignments", []),
        "beds": beds_for_room(room, state, patients_by_id),
        "reservedBy": state.get("reservedBy"),
        "reserved_by": state.get("reservedBy"),
        "queue": state.get("queue", []),
    }


def recompute_room_state(room_state, patients, rooms_by_id):
    room_state.setdefault("rooms", {})
    patients_by_id = {patient_identifier(patient): patient for patient in patients if patient_identifier(patient)}
    for room in rooms_by_id.values():
        state = room_state["rooms"].setdefault(room["id"], {"roomId": room["id"], "room_id": room["id"], "reservedBy": None, "reserved_by": None, "queue": []})
        state["room_id"] = room["id"]
        state["roomId"] = room["id"]
        state["queue"] = [
            entry for entry in normalized_room_queue(state.get("queue", []))
            if entry.get("patientId") in patients_by_id
            and patients_by_id[entry.get("patientId")].get("form") != "hidden"
            and patients_by_id[entry.get("patientId")].get("status") != "DISCHARGED"
        ]
        state["capacityBeds"] = max(
            int(state.get("capacityBeds", 0) or 0),
            int(room.get("capacityBeds", 0) or 0),
            len(state.get("bedIds", []) or state.get("bed_ids", []) or room.get("bedIds", [])),
        )
        state["capacity_beds"] = state["capacityBeds"]
        state["bedIds"] = room.get("bedIds", [])
        state["bed_ids"] = state["bedIds"]
        assignments = []
        used_bed_ids = set()
        for assignment in normalize_bed_assignments(state.get("bedAssignments", []), state["bedIds"]):
            patient_id = assignment.get("patient_id") or assignment.get("patientId")
            patient = patients_by_id.get(patient_id)
            if not patient or patient.get("form") == "hidden" or patient.get("status") == "DISCHARGED":
                continue
            if patient.get("bedRoomId") and patient.get("bedRoomId") != room["id"]:
                continue
            bed_id = assignment.get("bedId") if assignment.get("bedId") in state["bedIds"] else next_available_bed_id(state["bedIds"], used_bed_ids)
            if not bed_id:
                continue
            patient["bedRoomId"] = room["id"]
            patient["bedId"] = bed_id
            patient["bed_room_id"] = room["id"]
            patient["bed_id"] = bed_id
            patient.setdefault("home_bed", {})["room_id"] = room["id"]
            patient.setdefault("home_bed", {})["bed_id"] = bed_id
            assignments.append({"bedId": bed_id, "patientId": patient_id, "bed_id": bed_id, "patient_id": patient_id})
            used_bed_ids.add(bed_id)
        state["bedAssignments"] = unique_list(assignments)
        state["bed_assignments"] = state["bedAssignments"]
    for patient in patients:
        patient_id = patient_identifier(patient)
        if not patient_id:
            continue
        if patient.get("form") == "hidden" or patient.get("status") == "DISCHARGED":
            release_patient_bed(room_state, patient)
            continue
        bed_room_id = patient.get("bedRoomId")
        if bed_room_id and is_care_room(rooms_by_id.get(bed_room_id)):
            assign_patient_bed(room_state, patient, bed_room_id)
            continue
        room = rooms_by_id.get(patient.get("roomId"))
        if room and is_care_room(room) and patient.get("form") == "bed":
            assign_patient_bed(room_state, patient, room["id"])
    for room in rooms_by_id.values():
        state = room_state["rooms"].setdefault(room["id"], {"roomId": room["id"], "room_id": room["id"], "reservedBy": None, "reserved_by": None, "queue": []})
        state["room_id"] = room["id"]
        state["roomId"] = room["id"]
        state["bedIds"] = room.get("bedIds", [])
        state["bed_ids"] = state["bedIds"]
        state["bedAssignments"] = unique_list(state.get("bedAssignments", []))
        state["bed_assignments"] = state["bedAssignments"]
        state["occupiedBeds"] = len(state["bedAssignments"])
        state["occupied_beds"] = state["occupiedBeds"]


def patient_identifier(patient):
    if not patient:
        return None
    return patient.get("patient_id") or patient.get("patientId") or patient.get("id")


def unique_list(values):
    result = []
    for value in values:
        if value not in result:
            result.append(value)
    return result


def bed_ids_for_room(room_id, items, capacity_beds):
    bed_items = [item for item in items if item.get("type") == "bed"]
    ids = []
    for index in range(int(capacity_beds or 0)):
        item = bed_items[index] if index < len(bed_items) else {}
        ids.append(item.get("id") or f"{room_id}-bed-{index + 1:02d}")
    return ids


def normalize_bed_assignments(assignments, bed_ids):
    normalized = []
    fallback_index = 0
    for assignment in assignments or []:
        if isinstance(assignment, dict):
            patient_id = assignment.get("patient_id") or assignment.get("patientId")
            bed_id = assignment.get("bed_id") or assignment.get("bedId")
        else:
            patient_id = assignment
            bed_id = None
        if not patient_id:
            continue
        if not bed_id and fallback_index < len(bed_ids):
            bed_id = bed_ids[fallback_index]
            fallback_index += 1
        normalized.append({"bedId": bed_id, "patientId": patient_id, "bed_id": bed_id, "patient_id": patient_id})
    return normalized


def assignment_patient_ids(assignments):
    return [
        (assignment.get("patient_id") or assignment.get("patientId")) if isinstance(assignment, dict) else assignment
        for assignment in assignments or []
    ]


def next_available_bed_id(bed_ids, used_bed_ids):
    for bed_id in bed_ids:
        if bed_id not in used_bed_ids:
            return bed_id
    return None


def beds_for_room(room, state, patients_by_id):
    assignments = normalize_bed_assignments(state.get("bedAssignments", []), state.get("bedIds", room.get("bedIds", [])))
    by_bed_id = {assignment.get("bedId"): assignment.get("patientId") for assignment in assignments if assignment.get("bedId")}
    beds = []
    for bed_id in state.get("bedIds", room.get("bedIds", [])):
        patient_id = by_bed_id.get(bed_id)
        patient = patients_by_id.get(patient_id)
        beds.append({
            "bed_id": bed_id,
            "bedId": bed_id,
            "occupied": bool(patient_id),
            "patient_id": patient_id,
            "patientId": patient_id,
            "patientName": patient.get("name") if patient else None,
            "patient_name": patient.get("name") if patient else None,
            "patientStatus": patient.get("status") if patient else None,
            "patient_status": patient.get("status") if patient else None,
            "patientCurrentRoomId": patient.get("roomId") if patient else None,
            "patient_current_room_id": patient.get("roomId") if patient else None,
            "patientAway": bool(patient and patient.get("roomId") != room["id"]),
            "patient_away": bool(patient and patient.get("roomId") != room["id"]),
        })
    return beds


def is_care_room(room):
    return bool(room and room.get("kind") in CARE_ROOM_KINDS)


def is_consult_room(room):
    return bool(room and room.get("kind") in CONSULT_ROOM_KINDS)


def assign_patient_bed(room_state, patient, room_id):
    patient_id = patient_identifier(patient)
    if not patient_id:
        return
    release_patient_bed(room_state, patient, except_room_id=room_id)
    state = room_state.setdefault("rooms", {}).setdefault(room_id, {"roomId": room_id, "reservedBy": None, "queue": []})
    bed_ids = expanded_bed_ids(room_id, state)
    state["bedIds"] = bed_ids
    state["bed_ids"] = bed_ids
    assignments = normalize_bed_assignments(state.get("bedAssignments", []), bed_ids)
    existing = next((assignment for assignment in assignments if (assignment.get("patient_id") or assignment.get("patientId")) == patient_id), None)
    if existing:
        bed_id = existing.get("bedId")
    else:
        used_bed_ids = {assignment.get("bed_id") or assignment.get("bedId") for assignment in assignments if assignment.get("bed_id") or assignment.get("bedId")}
        bed_id = next_available_bed_id(bed_ids, used_bed_ids)
        if not bed_id:
            return
        assignments.append({"bedId": bed_id, "patientId": patient_id, "bed_id": bed_id, "patient_id": patient_id})
    state["bedAssignments"] = assignments
    state["bed_assignments"] = assignments
    patient["bedRoomId"] = room_id
    patient["bedId"] = bed_id
    patient["bed_room_id"] = room_id
    patient["bed_id"] = bed_id
    patient.setdefault("home_bed", {})["room_id"] = room_id
    patient.setdefault("home_bed", {})["bed_id"] = bed_id
    state["occupiedBeds"] = len(assignments)
    state["occupied_beds"] = len(assignments)


def expanded_bed_ids(room_id, state):
    bed_ids = list(state.get("bedIds") or state.get("bed_ids") or [])
    capacity = max(int(state.get("capacityBeds", 0) or 0), int(state.get("capacity_beds", 0) or 0), len(bed_ids))
    index = 1
    while len(bed_ids) < capacity:
        candidate = f"{room_id}-bed-{index:02d}"
        if candidate not in bed_ids:
            bed_ids.append(candidate)
        index += 1
    return bed_ids


def release_patient_bed(room_state, patient, except_room_id=None):
    patient_id = patient_identifier(patient)
    if not patient_id:
        return
    for room_id, state in room_state.setdefault("rooms", {}).items():
        if room_id == except_room_id:
            continue
        assignments = normalize_bed_assignments(state.get("bedAssignments", []), state.get("bedIds", []))
        if patient_id in assignment_patient_ids(assignments):
            state["bedAssignments"] = [value for value in assignments if (value.get("patient_id") or value.get("patientId")) != patient_id]
            state["bed_assignments"] = state["bedAssignments"]
            state["occupiedBeds"] = len(state["bedAssignments"])
            state["occupied_beds"] = len(state["bedAssignments"])
    if patient.get("bedRoomId") != except_room_id:
        patient.pop("bedRoomId", None)
        patient.pop("bedId", None)
        patient.pop("bed_room_id", None)
        patient.pop("bed_id", None)
        patient["home_bed"] = {}


def should_release_source_bed(movement, final_form, previous_bed_room_id, target_room):
    if not previous_bed_room_id:
        return False
    policy = movement.get("resourcePolicy", {})
    if policy.get("retainSourceBed") is True:
        return False
    if policy.get("releaseSourceBed") is True:
        return True
    if final_form == "hidden":
        return True
    if is_care_room(target_room) and target_room.get("id") != previous_bed_room_id:
        return True
    return False


def build_department_status(floors, rooms, patients):
    departments = {}
    room_to_department = {}
    for floor in floors:
        department = floor["departmentKinds"][0] if floor.get("departmentKinds") else "hospital"
        for room_id in floor.get("rooms", []):
            room_to_department[room_id] = department
    for patient in patients:
        department = room_to_department.get(patient.get("roomId"), patient.get("department", "hospital"))
        departments.setdefault(department, {"patients": 0, "transferring": 0})
        departments[department]["patients"] += 1
        if patient.get("status") == "TRANSFERRING":
            departments[department]["transferring"] += 1
    return departments


def final_status_for(final_form, target_room):
    if final_form == "hidden":
        return "DISCHARGED"
    if target_room.get("kind") in ["icu", "ward"] or final_form == "bed":
        return "ADMITTED"
    if final_form == "consultation":
        return "IN_CONSULTATION"
    if final_form == "stretcher":
        return "IN_EXAM"
    if target_room.get("kind") == "waiting":
        return "WAITING"
    return "ARRIVED"


def visual_form_for(final_form, target_room):
    if final_form in ["bed", "stretcher", "consultation", "waiting"]:
        return final_form
    if target_room.get("kind") == "waiting":
        return "waiting"
    if target_room.get("kind") in ["icu", "ward"]:
        return "bed"
    return "walking"


def default_rel_x_for(form, room):
    if form == "bed":
        return 0.2
    if form == "consultation":
        return 0.72
    return 0.5


def default_rel_y_for(form, room):
    if form == "bed":
        return 0.4
    if form == "waiting":
        return 0.62
    return 0.58


def summarize_items(items):
    counts = {}
    for item in items:
        item_type = item.get("type", "item")
        counts[item_type] = counts.get(item_type, 0) + 1
    return counts


def count_items(items, item_type):
    return sum(1 for item in items if item.get("type") == item_type)


def next_event_seq(event_log):
    return int(event_log.get("lastSeq", 0)) + 1


def error(code, message):
    return {"code": code, "message": message}


def first_query_value(query, key, default=""):
    value = query.get(key, [default])
    return value[0] if value else default


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def read_json_default(path, default):
    if not path.exists():
        return json.loads(json.dumps(default))
    try:
        return read_json(path)
    except json.JSONDecodeError:
        return json.loads(json.dumps(default))


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def safe_rule_file(name):
    filename = unquote(name)
    if "/" in filename or "\\" in filename or not filename.endswith(".json"):
        return RULES_DIR / "__invalid__"
    return RULES_DIR / filename


def refresh_rule_index():
    index_path = RULES_DIR / "index.json"
    if not index_path.exists():
        return
    index = read_json(index_path)
    for category in index.get("categories", []):
        rule_file = RULES_DIR / category.get("file", "")
        if rule_file.exists():
            category["ruleCount"] = len(read_json(rule_file).get("rules", []))
    write_json(index_path, index)


def mirror_rule_index():
    source = RULES_DIR / "index.json"
    target = ROOT / "event-rules" / "index.json"
    if source.exists() and target.parent.exists():
        write_json(target, read_json(source))


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    try:
        import uvicorn

        print(f"Serving full hospital view with FastAPI Core at http://127.0.0.1:{port}/")
        print("SQLite source of truth: hospital/full_view/backend-data/fullview.sqlite")
        print("Static UI: hospital/full_view/*.html")
        uvicorn.run("backend.app.main:app", host="127.0.0.1", port=port, reload=False)
    except Exception as error:
        print(f"FastAPI Core failed to start ({error}); falling back to legacy JSON dev server.")
        server = ThreadingHTTPServer(("127.0.0.1", port), HospitalViewHandler)
        print(f"Serving legacy full hospital view at http://127.0.0.1:{port}/")
        server.serve_forever()
