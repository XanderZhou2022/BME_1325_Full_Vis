import { TILE } from "./layout.js";

export const STAFF = [
  nurse("nurse-er-a", 1, "female", 14, 10, "standing"),
  nurse("nurse-er-b", 1, "male", 55, 26, "walking"),
  doctor("doctor-er-a", 1, "male", 35, 10, "standing"),
  doctor("doctor-er-b", 1, "female", 56, 10, "standing"),

  nurse("nurse-op-reg", 2, "female", 13, 10, "standing"),
  nurse("nurse-op-triage", 2, "male", 28, 10, "standing"),
  doctor("doctor-op-a", 2, "female", 43, 10, "seated"),
  doctor("doctor-op-b", 2, "male", 58, 10, "seated"),
  doctor("doctor-op-internal", 2, "male", 13, 21, "seated"),
  doctor("doctor-op-surgery", 2, "female", 28, 21, "standing"),
  nurse("nurse-op-wait", 2, "female", 48, 33, "walking"),

  nurse("nurse-icu-station-a", 3, "female", 14, 10, "standing"),
  nurse("nurse-icu-station-b", 3, "male", 17, 10, "standing"),
  doctor("doctor-icu-bed-a", 3, "female", 35, 10, "monitoring"),
  doctor("doctor-icu-bed-b", 3, "male", 56, 10, "monitoring"),
  nurse("nurse-icu-isolation", 3, "female", 57, 25, "monitoring"),

  doctor("doctor-mdt-a", 4, "female", 14, 10, "seated"),
  doctor("doctor-mdt-b", 4, "male", 35, 10, "seated"),
  doctor("doctor-mdt-c", 4, "female", 56, 10, "standing"),
  nurse("nurse-mdt-coord", 4, "female", 56, 25, "standing"),

  nurse("nurse-ward-station-a", 5, "female", 14, 10, "standing"),
  nurse("nurse-ward-station-b", 5, "male", 17, 10, "walking"),
  doctor("doctor-ward-office", 5, "male", 14, 25, "standing"),
  doctor("doctor-ward-round", 5, "female", 35, 10, "monitoring"),
  nurse("nurse-ward-room-c", 5, "female", 35, 25, "monitoring"),
];

export function getStaffForFloor(floorId) {
  return STAFF.filter((staff) => staff.floor === floorId);
}

function doctor(id, floor, gender, x, y, pose) {
  return staff(id, floor, "doctor", gender, x, y, pose);
}

function nurse(id, floor, gender, x, y, pose) {
  return staff(id, floor, "nurse", gender, x, y, pose);
}

function staff(id, floor, role, gender, x, y, pose) {
  return {
    id,
    floor,
    role,
    gender,
    pose,
    x: x * TILE,
    y: y * TILE,
    phase: id.length * 0.29,
  };
}
