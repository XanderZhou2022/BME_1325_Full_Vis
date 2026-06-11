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
    patients = read_json(PATIENTS_FILE).get("patients", [])
    staff = read_json(STAFF_FILE).get("staff", [])
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
    patients_data = read_json(PATIENTS_FILE)
    room_state = read_json(ROOM_STATE_FILE)
    event_log = read_json(EVENT_LOG_FILE)
    map_config = read_json(MAP_CONFIG)
    _, rooms = normalize_map(map_config)
    rooms_by_id = {room["id"]: room for room in rooms}
    patients = patients_data.get("patients", [])
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
    final_form = movement.get("finalForm", "walking")

    patient["roomId"] = to_room_id
    patient["status"] = final_status_for(final_form, target_room)
    patient["form"] = visual_form_for(final_form, target_room)
    patient["relX"] = default_rel_x_for(patient["form"], target_room)
    patient["relY"] = default_rel_y_for(patient["form"], target_room)
    if patient["form"] == "bed":
        patient["blanket"] = "#d46d8e" if target_room.get("kind") == "icu" else "#76c59d"
        patient["skin"] = patient.get("skin") or "#f2c799"

    recompute_room_state(room_state, patients, rooms_by_id)
    write_json(PATIENTS_FILE, patients_data)
    write_json(ROOM_STATE_FILE, room_state)

    response = {
        "accepted": True,
        "eventSeq": event_seq,
        "eventId": rule.get("eventId"),
        "patientId": patient.get("patientId"),
        "statusUpdates": {
            "patientStatus": "TRANSFERRING",
            "fromRoomReleased": previous_room is not None,
            "targetReserved": True,
        },
        "animationPlan": {
            "kind": "patient-move",
            "transport": movement.get("transport", "walking"),
            "escortRoles": movement.get("escortRoles", []),
            "equipment": movement.get("equipment", []),
            "fromRoomId": from_room_id,
            "toRoomId": to_room_id,
            "viaRoomIds": movement.get("via", []),
            "finalForm": final_form,
            "patientFormDuringMove": movement.get("patientFormDuringMove", movement.get("transport", "walking")),
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
    if not source_allowed(rule.get("movement", {}), request.get("fromRoomId")):
        return error("SOURCE_NOT_ALLOWED", "Source room is not allowed by the selected movement rule.")

    target_room = rooms_by_id[request.get("toRoomId")]
    if target_room.get("kind") in ["icu", "ward"]:
        state = room_state.get("rooms", {}).get(target_room["id"], {})
        if state.get("capacityBeds", 0) <= state.get("occupiedBeds", 0):
            return error("NO_BED_AVAILABLE", "Target care room has no available bed.")

    movement = rule.get("movement", {})
    if movement.get("escortRequired"):
        missing = [
            role for role in movement.get("escortRoles", [])
            if room_state.get("escortResources", {}).get(role, {}).get("available", 0) <= 0
        ]
        if missing:
            return error("ESCORT_UNAVAILABLE", f"Missing escort resource: {', '.join(missing)}.")

    return None


def append_event(event_log, response, request):
    event_log["lastSeq"] = response["eventSeq"]
    event = {
        "eventSeq": response["eventSeq"],
        "accepted": response["accepted"],
        "eventId": response.get("eventId"),
        "patientId": response.get("patientId"),
        "request": request,
    }
    if response.get("animationPlan"):
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
            if rule.get("eventId") == event_id:
                return rule
    return None


def find_patient(patients, patient_id):
    return next((patient for patient in patients if patient.get("patientId") == patient_id or patient.get("id") == patient_id), None)


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
            normalized = {
                "id": room_id,
                "roomId": room_id,
                "roomCode": room.get("roomCode") or f"{floor_id}F-Room{floor_counts[floor_id]}",
                "floor": floor_id,
                "kind": room.get("kind", "room"),
                "label": room.get("label", room_id),
                "protected": bool(room.get("protected") or room.get("kind") == "elevator"),
                "features": summarize_items(items),
                "capacityBeds": room.get("maxBeds") if room.get("maxBeds") is not None else count_items(items, "bed"),
            }
            rooms.append(normalized)
            floor_room_ids.append(room_id)
        floors.append({
            "id": floor_id,
            "label": floor.get("label", f"{floor_id}F"),
            "shortLabel": floor.get("shortLabel", f"{floor_id}F"),
            "departmentKinds": floor.get("departmentKinds", []),
            "rooms": floor_room_ids,
        })
    return floors, rooms


def decorate_room(room, patients, staff, room_state):
    state = room_state.get("rooms", {}).get(room["id"], {})
    room_patients = [patient for patient in patients if patient.get("roomId") == room["id"]]
    room_staff = [member for member in staff if member.get("roomId") == room["id"]]
    return {
        **room,
        "patients": room_patients,
        "staff": room_staff,
        "patientCount": len(room_patients),
        "staffCount": len(room_staff),
        "occupiedBeds": state.get("occupiedBeds", 0),
        "availableBeds": max(0, state.get("capacityBeds", room.get("capacityBeds", 0)) - state.get("occupiedBeds", 0)),
        "reservedBy": state.get("reservedBy"),
        "queue": state.get("queue", []),
    }


def recompute_room_state(room_state, patients, rooms_by_id):
    room_state.setdefault("rooms", {})
    for room in rooms_by_id.values():
        state = room_state["rooms"].setdefault(room["id"], {"roomId": room["id"], "reservedBy": None, "queue": []})
        state["capacityBeds"] = state.get("capacityBeds", room.get("capacityBeds", 0))
        state["occupiedBeds"] = 0
    for patient in patients:
        room = rooms_by_id.get(patient.get("roomId"))
        if room and patient.get("form") == "bed":
            room_state["rooms"][room["id"]]["occupiedBeds"] += 1


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
