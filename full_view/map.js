export const TILE = 32;

export const WORLD = {
  width: 84 * TILE,
  height: 48 * TILE,
};

export const FLOOR_PLATE = {
  x: 4,
  y: 4,
  w: 74,
  h: 40,
};

const ELEVATOR = {
  x: 62,
  y: 32,
  w: 10,
  h: 10,
};

const ELEVATOR_SPAWN = {
  x: (ELEVATOR.x + ELEVATOR.w / 2) * TILE,
  y: (ELEVATOR.y + ELEVATOR.h / 2) * TILE,
};

export const FLOORS = [
  {
    id: 1,
    label: "1F Emergency",
    shortLabel: "1F",
    subtitle: "Aligned emergency floor with intake, rescue, consult rooms, entrance, and bottom-right elevator.",
    spawn: ELEVATOR_SPAWN,
    departmentKinds: ["emergency"],
  },
  {
    id: 2,
    label: "2F Outpatient",
    shortLabel: "2F",
    subtitle: "Outpatient office grid aligned with registration, triage, consultation, lab, and pharmacy nodes.",
    spawn: ELEVATOR_SPAWN,
    departmentKinds: ["outpatient", "pharmacy", "lab"],
  },
  {
    id: 3,
    label: "3F ICU",
    shortLabel: "3F",
    subtitle: "Aligned ICU floor with station, monitored beds, support, and bottom-right elevator.",
    spawn: ELEVATOR_SPAWN,
    departmentKinds: ["icu"],
  },
  {
    id: 4,
    label: "4F MDT",
    shortLabel: "4F",
    subtitle: "Aligned MDT floor with meeting, imaging review, specialist planning, and elevator.",
    spawn: ELEVATOR_SPAWN,
    departmentKinds: ["mdt"],
  },
  {
    id: 5,
    label: "5F Ward",
    shortLabel: "5F",
    subtitle: "Aligned inpatient floor with nurse station, wards, doctor office, and elevator.",
    spawn: ELEVATOR_SPAWN,
    departmentKinds: ["ward"],
  },
];

export const ROOM_KIND_LABELS = {
  entrance: "Entrance",
  elevator: "Elevator",
  waiting: "Waiting",
  emergency: "Emergency",
  rescue: "Rescue Bay",
  emergency_consult: "ER Consult",
  registration: "Registration",
  triage: "Triage",
  consultation: "Consultation",
  doctor_entry: "Doctor Entry",
  internal_medicine: "Internal Med",
  surgery: "Surgery",
  pediatrics: "Pediatrics",
  obgyn: "OB-GYN",
  outpatient: "Outpatient",
  pharmacy: "Pharmacy",
  pharmacy_pickup: "Pharmacy",
  lab: "Lab",
  icu: "ICU Beds",
  icu_station: "ICU Station",
  monitor: "Monitor",
  mdt: "MDT Center",
  mdt_meeting: "Conference",
  imaging_review: "Imaging Review",
  specialist: "Specialist",
  ward: "Ward Rooms",
  nurse_station: "Nurse Station",
  doctor_office: "Doctor Office",
};

export const DEPARTMENT_STATUS = {
  emergency: { status: "Ready", patients: 3, accent: "#d85e5e" },
  outpatient: { status: "Open", patients: 12, accent: "#4b79d8" },
  pharmacy: { status: "Dispensing", patients: 5, accent: "#87b96b" },
  lab: { status: "Testing", patients: 7, accent: "#55b8c8" },
  icu: { status: "Monitoring", patients: 4, accent: "#d46d8e" },
  mdt: { status: "Consulting", patients: 2, accent: "#9b87f5" },
  ward: { status: "Admitted", patients: 18, accent: "#66bfa2" },
};

export const ROOMS = [
  // 1F Emergency: same aligned macro grid as 3F-5F.
  room(1, "emergency_intake", "emergency", "Emergency Intake", 6, 6, 18, 11, "#d85e5e"),
  room(1, "rescue_bay", "rescue", "Rescue Bay", 27, 6, 18, 11, "#e05f5f"),
  room(1, "emergency_consult", "emergency_consult", "ER Consultation", 48, 6, 18, 11, "#c96b58"),
  room(1, "entrance_1", "entrance", "Main Entrance", 6, 21, 18, 11, "#b99163"),
  room(1, "observation_1", "emergency", "Emergency Observation", 27, 21, 18, 11, "#d9736d"),
  room(1, "emergency_support", "waiting", "Emergency Waiting", 48, 21, 18, 11, "#e7d1a1"),
  elevatorRoom(1),

  // 2F Outpatient: smaller office grid aligned with the outpatient demo's workflow rooms.
  room(2, "registration_2", "registration", "Registration", 6, 6, 13, 8, "#6d8fe8"),
  room(2, "triage_2", "triage", "Triage", 21, 6, 13, 8, "#74a7e8"),
  room(2, "consultation_a_2", "consultation", "Consultation A", 36, 6, 13, 8, "#6d8fe8"),
  room(2, "consultation_b_2", "consultation", "Consultation B", 51, 6, 13, 8, "#6d8fe8"),
  room(2, "internal_2", "internal_medicine", "Internal Medicine", 6, 17, 13, 8, "#7f9ee8"),
  room(2, "surgery_2", "surgery", "Surgery Clinic", 21, 17, 13, 8, "#7f9ee8"),
  room(2, "pediatrics_2", "pediatrics", "Pediatrics", 36, 17, 13, 8, "#7f9ee8"),
  room(2, "doctor_entry_2", "doctor_entry", "Doctor Entry", 51, 17, 13, 8, "#6f8fd7"),
  room(2, "lab_2", "lab", "Laboratory", 6, 29, 13, 8, "#55b8c8"),
  room(2, "pharmacy_2", "pharmacy_pickup", "Pharmacy Pickup", 21, 29, 13, 8, "#87b96b"),
  room(2, "outpatient_waiting", "waiting", "Outpatient Waiting", 36, 29, 24, 8, "#e7d1a1"),
  elevatorRoom(2),

  // 3F ICU.
  room(3, "icu_station", "icu_station", "ICU Nurse Station", 6, 6, 18, 11, "#d46d8e"),
  room(3, "icu_beds_a", "icu", "ICU Beds A", 27, 6, 18, 11, "#db7895"),
  room(3, "icu_beds_b", "icu", "ICU Beds B", 48, 6, 18, 11, "#db7895"),
  room(3, "monitor_center", "monitor", "Monitoring Center", 6, 21, 18, 11, "#79bcc8"),
  room(3, "icu_support", "waiting", "Family Support", 27, 21, 18, 11, "#e7d1a1"),
  room(3, "icu_isolation", "icu", "Isolation Beds", 48, 21, 18, 11, "#cf6f8c"),
  elevatorRoom(3),

  // 4F MDT.
  room(4, "mdt_center", "mdt", "MDT Center", 6, 6, 18, 11, "#9b87f5"),
  room(4, "mdt_meeting", "mdt_meeting", "Conference Room", 27, 6, 18, 11, "#a992f7"),
  room(4, "imaging_review", "imaging_review", "Imaging Review", 48, 6, 18, 11, "#67b7cf"),
  room(4, "specialist_room", "specialist", "Specialist Planning", 6, 21, 18, 11, "#dca768"),
  room(4, "mdt_records", "doctor_office", "Records Office", 27, 21, 18, 11, "#c79b69"),
  room(4, "mdt_lounge", "waiting", "Consult Waiting", 48, 21, 18, 11, "#e7d1a1"),
  elevatorRoom(4),

  // 5F Ward.
  room(5, "nurse_station", "nurse_station", "Nurse Station", 6, 6, 18, 11, "#66bfa2"),
  room(5, "ward_rooms_a", "ward", "Ward Rooms A", 27, 6, 18, 11, "#76c59d"),
  room(5, "ward_rooms_b", "ward", "Ward Rooms B", 48, 6, 18, 11, "#76c59d"),
  room(5, "doctor_office", "doctor_office", "Doctor Office", 6, 21, 18, 11, "#dca768"),
  room(5, "ward_rooms_c", "ward", "Ward Rooms C", 27, 21, 18, 11, "#76c59d"),
  room(5, "ward_support", "waiting", "Family Waiting", 48, 21, 18, 11, "#e7d1a1"),
  elevatorRoom(5),
];

export const DOORS = [
  // 1F
  door("emergency_intake", "bottom", 7.5, 3),
  door("rescue_bay", "bottom", 7.5, 3),
  door("emergency_consult", "bottom", 7.5, 3),
  door("entrance_1", "top", 7.5, 3),
  door("observation_1", "top", 7.5, 3),
  door("emergency_support", "top", 7.5, 3),
  door("elevator_1", "top", 3.5, 3),

  // 2F
  door("registration_2", "bottom", 5, 3),
  door("triage_2", "bottom", 5, 3),
  door("consultation_a_2", "bottom", 5, 3),
  door("consultation_b_2", "bottom", 5, 3),
  door("internal_2", "bottom", 5, 3),
  door("surgery_2", "bottom", 5, 3),
  door("pediatrics_2", "bottom", 5, 3),
  door("doctor_entry_2", "bottom", 5, 3),
  door("lab_2", "top", 5, 3),
  door("pharmacy_2", "top", 5, 3),
  door("outpatient_waiting", "top", 12.5, 3),
  door("elevator_2", "top", 3.5, 3),

  // 3F
  door("icu_station", "bottom", 7.5, 3),
  door("icu_beds_a", "bottom", 7.5, 3),
  door("icu_beds_b", "bottom", 7.5, 3),
  door("monitor_center", "top", 7.5, 3),
  door("icu_support", "top", 7.5, 3),
  door("icu_isolation", "top", 7.5, 3),
  door("elevator_3", "top", 3.5, 3),

  // 4F
  door("mdt_center", "bottom", 7.5, 3),
  door("mdt_meeting", "bottom", 7.5, 3),
  door("imaging_review", "bottom", 7.5, 3),
  door("specialist_room", "top", 7.5, 3),
  door("mdt_records", "top", 7.5, 3),
  door("mdt_lounge", "top", 7.5, 3),
  door("elevator_4", "top", 3.5, 3),

  // 5F
  door("nurse_station", "bottom", 7.5, 3),
  door("ward_rooms_a", "bottom", 7.5, 3),
  door("ward_rooms_b", "bottom", 7.5, 3),
  door("doctor_office", "top", 7.5, 3),
  door("ward_rooms_c", "top", 7.5, 3),
  door("ward_support", "top", 7.5, 3),
  door("elevator_5", "top", 3.5, 3),
];

export const PROPS = [
  // Emergency
  prop(1, 10, 9, 5, 1.5, "reception"),
  prop(1, 32, 9, 3.4, 1.4, "bed"),
  prop(1, 38, 9, 3.4, 1.4, "bed"),
  prop(1, 53, 9, 3.5, 1.3, "desk"),
  prop(1, 10, 24, 4, 1.4, "desk"),
  prop(1, 32, 24, 3.4, 1.4, "bed"),
  prop(1, 53, 24, 3.5, 1.3, "sofa"),
  elevatorProp(1),

  // Outpatient office grid
  prop(2, 9, 9, 3.4, 1.2, "reception"),
  prop(2, 24, 9, 3.4, 1.2, "desk"),
  prop(2, 39, 9, 3.4, 1.2, "desk"),
  prop(2, 54, 9, 3.4, 1.2, "desk"),
  prop(2, 9, 20, 3.2, 1.2, "desk"),
  prop(2, 24, 20, 3.2, 1.2, "desk"),
  prop(2, 39, 20, 3.2, 1.2, "desk"),
  prop(2, 54, 20, 3.2, 1.2, "screen"),
  prop(2, 10, 32, 3.4, 1.3, "screen"),
  prop(2, 24, 32, 4.2, 1.4, "cabinet"),
  prop(2, 43, 32, 3.5, 1.2, "sofa"),
  prop(2, 52, 32, 3.5, 1.2, "sofa"),
  elevatorProp(2),

  // ICU
  prop(3, 11, 10, 4.2, 1.4, "reception"),
  prop(3, 32, 9, 3.4, 1.3, "bed"),
  prop(3, 38, 9, 3.4, 1.3, "bed"),
  prop(3, 53, 9, 3.4, 1.3, "bed"),
  prop(3, 11, 24, 3.4, 1.3, "screen"),
  prop(3, 33, 24, 3.5, 1.2, "sofa"),
  prop(3, 53, 24, 3.4, 1.3, "bed"),
  elevatorProp(3),

  // MDT
  prop(4, 11, 10, 5, 1.8, "table"),
  prop(4, 32, 10, 5, 1.8, "table"),
  prop(4, 53, 10, 5, 1.6, "screen"),
  prop(4, 11, 24, 4, 1.4, "desk"),
  prop(4, 32, 24, 4, 1.4, "cabinet"),
  prop(4, 53, 24, 4, 1.4, "sofa"),
  elevatorProp(4),

  // Ward
  prop(5, 11, 10, 4.2, 1.4, "reception"),
  prop(5, 32, 9, 3.4, 1.3, "bed"),
  prop(5, 38, 9, 3.4, 1.3, "bed"),
  prop(5, 53, 9, 3.4, 1.3, "bed"),
  prop(5, 11, 24, 4.2, 1.4, "desk"),
  prop(5, 32, 24, 3.4, 1.3, "bed"),
  prop(5, 53, 24, 3.5, 1.2, "sofa"),
  elevatorProp(5),
];

function room(floor, id, kind, label, x, y, w, h, accent) {
  return { floor, id, kind, label, x, y, w, h, accent };
}

function elevatorRoom(floor) {
  return room(floor, `elevator_${floor}`, "elevator", "Elevator", ELEVATOR.x, ELEVATOR.y, ELEVATOR.w, ELEVATOR.h, "#d7b07b");
}

function door(roomId, side, offset, length) {
  return { roomId, side, offset, length };
}

function prop(floor, x, y, w, h, type) {
  return { floor, x, y, w, h, type };
}

function elevatorProp(floor) {
  return prop(floor, ELEVATOR.x + 3.2, ELEVATOR.y + 3.7, 3.6, 1.6, "elevator");
}

export function getFloor(id) {
  return FLOORS.find((floor) => floor.id === id) || FLOORS[0];
}

export function getRoomsForFloor(floorId) {
  return ROOMS.filter((room) => room.floor === floorId);
}

export function getPropsForFloor(floorId) {
  return PROPS.filter((item) => item.floor === floorId);
}
