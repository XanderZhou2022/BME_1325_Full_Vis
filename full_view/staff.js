import { placeInRoom } from "./placement.js";

export const STAFF = [
  nurse("nurse-er-a", "R-ED-REGISTRATION", "female", 0.46, 0.58, "standing"),
  nurse("nurse-er-b", "R-ED-BEDSIDE-NURSE", "male", 0.30, 0.60, "walking"),
  doctor("doctor-er-a", "R-ED-DOCTOR-ROOM", "male", 0.28, 0.58, "standing"),
  doctor("doctor-er-b", "R-ED-RED-RESUS", "female", 0.50, 0.58, "standing"),

  nurse("nurse-op-reg", "R-OP-REGISTRATION", "female", 0.56, 0.58, "standing"),
  nurse("nurse-op-triage", "R-OP-TRIAGE", "male", 0.56, 0.58, "standing"),
  doctor("doctor-op-a", "R-OP-CONSULTATION-A", "female", 0.84, 0.58, "seated"),
  doctor("doctor-op-b", "R-OP-CONSULTATION-B", "male", 0.84, 0.58, "seated"),
  doctor("doctor-op-internal", "R-OP-INTERNAL", "male", 0.56, 0.58, "seated"),
  doctor("doctor-op-surgery", "R-OP-SURGERY", "female", 0.56, 0.58, "standing"),
  nurse("nurse-op-queue", "R-OP-QUEUE-INTERNAL", "female", 0.45, 0.60, "walking"),

  nurse("nurse-icu-station-a", "R-ICU-STATION", "female", 0.30, 0.58, "standing"),
  nurse("nurse-icu-station-b", "R-ICU-STATION", "male", 0.62, 0.58, "standing"),
  doctor("doctor-icu-bed-a", "R-ICU-BEDS-A", "female", 0.58, 0.58, "monitoring"),
  doctor("doctor-icu-bed-b", "R-ICU-BEDS-B", "male", 0.58, 0.58, "monitoring"),
  nurse("nurse-icu-isolation", "R-ICU-ISOLATION", "female", 0.58, 0.58, "monitoring"),

  doctor("doctor-mdt-a", "R-MDT-HEAD-DOCTOR", "female", 0.50, 0.58, "seated"),
  doctor("doctor-mdt-b", "R-MDT-MEETING", "male", 0.50, 0.58, "seated"),
  doctor("doctor-mdt-c", "R-MDT-IMAGING-REVIEW", "female", 0.50, 0.58, "standing"),
  nurse("nurse-mdt-coord", "R-MDT-FINAL-PLAN", "female", 0.50, 0.58, "standing"),

  nurse("nurse-ward-station-a", "R-WARD-NURSE-STATION", "female", 0.30, 0.58, "standing"),
  nurse("nurse-ward-station-b", "R-WARD-NURSE-STATION", "male", 0.62, 0.58, "walking"),
  doctor("doctor-ward-office", "R-WARD-DOCTOR-OFFICE", "male", 0.28, 0.58, "standing"),
  doctor("doctor-ward-round", "R-WARD-RESP", "female", 0.42, 0.58, "monitoring"),
  nurse("nurse-ward-room-c", "R-WARD-GENSURG", "female", 0.28, 0.58, "monitoring"),
];

export function getStaffForFloor(floorId) {
  return STAFF.filter((staff) => staff.floor === floorId);
}

export function reflowStaffPlacements() {
  STAFF.forEach((member) => {
    try {
      const placement = placeInRoom(member.roomId, member.relX, member.relY);
      member.floor = placement.floor;
      member.x = placement.x;
      member.y = placement.y;
    } catch {
      member.floor = -1;
    }
  });
}

function doctor(id, roomId, gender, relX, relY, pose) {
  return staff(id, roomId, "doctor", gender, relX, relY, pose);
}

function nurse(id, roomId, gender, relX, relY, pose) {
  return staff(id, roomId, "nurse", gender, relX, relY, pose);
}

function staff(id, roomId, role, gender, relX, relY, pose) {
  const placement = placeInRoom(roomId, relX, relY);
  return {
    id,
    floor: placement.floor,
    role,
    gender,
    pose,
    roomId,
    relX,
    relY,
    x: placement.x,
    y: placement.y,
    phase: id.length * 0.29,
  };
}
