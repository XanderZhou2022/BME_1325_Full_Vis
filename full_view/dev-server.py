from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import sys
from urllib.parse import parse_qs, unquote, urlparse


ROOT = Path(__file__).resolve().parent
MAP_CONFIG = ROOT / "map-config.json"
RULES_DIR = ROOT.parent / "rules" / "event-rules"
BACKEND_DATA = ROOT / "backend-data"
PATIENTS_FILE = BACKEND_DATA / "patients.json"
STAFF_FILE = BACKEND_DATA / "staff.json"
ROOM_STATE_FILE = BACKEND_DATA / "room-state.json"
EVENT_LOG_FILE = BACKEND_DATA / "event-log.json"
CARE_ROOM_KINDS = {"icu", "ward"}
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
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


def build_snapshot():
    map_config = read_json(MAP_CONFIG)
    patients = [normalize_patient_record(patient) for patient in read_json(PATIENTS_FILE).get("patients", [])]
    staff = [normalize_staff_record(member) for member in read_json(STAFF_FILE).get("staff", [])]
    room_state = read_json(ROOM_STATE_FILE)
    floors, rooms = normalize_map(map_config)
    rooms_by_id = {room["id"]: room for room in rooms}
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
    target_room = rooms_by_id[to_room_id]
    previous_room = rooms_by_id.get(patient.get("roomId"))
    previous_bed_room_id = patient.get("bedRoomId")
    final_form = movement.get("final_form") or movement.get("finalForm", "walking")
    release_source_bed = should_release_source_bed(movement, final_form, previous_bed_room_id, target_room)

    if release_source_bed:
        release_patient_bed(room_state, patient)
    if final_form == "bed" and is_care_room(target_room):
        assign_patient_bed(room_state, patient, target_room["id"])

    set_patient_room(patient, to_room_id)
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

    recompute_room_state(room_state, patients, rooms_by_id)
    patients_data["patients"] = patients
    write_json(PATIENTS_FILE, patients_data)
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
            "target_reserved": bool(patient.get("bedRoomId") == to_room_id),
            "bed_room_id": patient.get("bedRoomId"),
            "bed_id": patient.get("bedId"),
        },
        "statusUpdates": {
            "patientStatus": "TRANSFERRING",
            "fromRoomReleased": previous_room is not None and not patient.get("bedRoomId") == previous_bed_room_id,
            "sourceBedRetained": bool(previous_bed_room_id and patient.get("bedRoomId") == previous_bed_room_id),
            "targetReserved": bool(patient.get("bedRoomId") == to_room_id),
            "bedRoomId": patient.get("bedRoomId"),
            "bedId": patient.get("bedId"),
        },
        "animation_plan": {
            "kind": "patient-move",
            "transport": movement.get("transport", "walking"),
            "escort_roles": movement.get("escort_roles") or movement.get("escortRoles", []),
            "equipment": movement.get("equipment", []),
            "from_room_id": from_room_id,
            "to_room_id": to_room_id,
            "via_room_ids": movement.get("via", []),
            "final_form": final_form,
            "patient_form_during_move": movement.get("patient_form_during_move") or movement.get("patientFormDuringMove", movement.get("transport", "walking")),
        },
        "animationPlan": {
            "kind": "patient-move",
            "transport": movement.get("transport", "walking"),
            "escortRoles": movement.get("escort_roles") or movement.get("escortRoles", []),
            "equipment": movement.get("equipment", []),
            "fromRoomId": from_room_id,
            "toRoomId": to_room_id,
            "viaRoomIds": movement.get("via", []),
            "finalForm": final_form,
            "patientFormDuringMove": movement.get("patient_form_during_move") or movement.get("patientFormDuringMove", movement.get("transport", "walking")),
        },
    }
    append_event(event_log, response, request)
    write_json(EVENT_LOG_FILE, event_log)
    return response


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


def normalize_staff_record(member):
    staff_id = member.get("staff_id") or member.get("employee_id") or member.get("employeeId") or member.get("id")
    local_id = member.get("local_person_id") or member.get("id") or staff_id
    room_id = member.get("room_id") or member.get("roomId") or nested_get(member, ["current_location", "room_id"])
    visual = dict(member.get("visual") or {})
    location = dict(member.get("current_location") or {})
    availability = dict(member.get("availability") or {})

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
        state["capacityBeds"] = state.get("capacityBeds", room.get("capacityBeds", 0))
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


def assign_patient_bed(room_state, patient, room_id):
    patient_id = patient_identifier(patient)
    if not patient_id:
        return
    release_patient_bed(room_state, patient, except_room_id=room_id)
    state = room_state.setdefault("rooms", {}).setdefault(room_id, {"roomId": room_id, "reservedBy": None, "queue": []})
    assignments = normalize_bed_assignments(state.get("bedAssignments", []), state.get("bedIds", []))
    existing = next((assignment for assignment in assignments if (assignment.get("patient_id") or assignment.get("patientId")) == patient_id), None)
    if existing:
        bed_id = existing.get("bedId")
    else:
        used_bed_ids = {assignment.get("bed_id") or assignment.get("bedId") for assignment in assignments if assignment.get("bed_id") or assignment.get("bedId")}
        bed_id = next_available_bed_id(state.get("bedIds", []), used_bed_ids)
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
    server = ThreadingHTTPServer(("127.0.0.1", port), HospitalViewHandler)
    print(f"Serving full hospital view at http://127.0.0.1:{port}/")
    print("Map editor writes to hospital/full_view/map-config.json")
    print("Rules editor writes to hospital/rules/event-rules/*.json")
    print("Hospital APIs read/write hospital/full_view/backend-data/*.json")
    server.serve_forever()
