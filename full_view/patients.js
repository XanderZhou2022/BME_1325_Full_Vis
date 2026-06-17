import { placeInRoom } from "./placement.js";

export const PATIENTS = [
  // Walking patients use room-relative anchors so layout edits keep them inside valid areas.
  walkingPatient("walk-er-1", "R-ED-PAGER", 0.55, 0.52, "#5f8ec9"),
  walkingPatient("walk-op-1", "R-OP-QUEUE-INTERNAL", 0.78, 0.55, "#5f8ec9"),
  walkingPatient("walk-mdt-1", "R-MDT-LOUNGE", 0.62, 0.55, "#8f7ed0"),

  // Waiting patients in waiting areas.
  waitingPatient("wait-er-1", "R-ED-WAITING", 0.36, 0.62, "#7899c6"),
  waitingPatient("wait-er-2", "R-ED-WAITING", 0.64, 0.62, "#c69072"),
  waitingPatient("wait-op-1", "R-OP-QUEUE-INTERNAL", 0.32, 0.62, "#7899c6"),
  waitingPatient("wait-op-2", "R-OP-QUEUE-SURGERY", 0.58, 0.62, "#c69072"),
  waitingPatient("wait-ward-1", "R-WARD-WARD-ADMISSION", 0.72, 0.58, "#7fa98f"),

  // Outpatient consultation scenes.
  consultationPatient("consult-a", "R-OP-CONSULTATION-A", 0.72, 0.56, "#5f8ec9", "female", "doctor-op-a"),
  consultationPatient("consult-b", "R-OP-CONSULTATION-B", 0.72, 0.56, "#8a79c9", "male", "doctor-op-b"),
  consultationPatient("consult-int", "R-OP-INTERNAL", 0.42, 0.58, "#5f8ec9", "male", "doctor-op-internal"),

  // Bed patients in ICU and ward.
  bedPatient("icu-bed-a", "R-ICU-BEDS-A", 0.20, 0.40, "#f2c799", "#d46d8e"),
  bedPatient("icu-bed-b", "R-ICU-BEDS-B", 0.20, 0.40, "#f2c799", "#d46d8e"),
  bedPatient("icu-isolation", "R-ICU-ISOLATION", 0.20, 0.40, "#f2c799", "#cf6f8c"),
  bedPatient("ward-bed-a", "R-WARD-RESP", 0.20, 0.40, "#f2c799", "#76c59d"),
  bedPatient("ward-bed-b", "R-WARD-CARD", 0.20, 0.40, "#f2c799", "#76c59d"),
  bedPatient("ward-bed-c", "R-WARD-PEDS", 0.20, 0.40, "#f2c799", "#76c59d"),
];

export function getPatientsForFloor(floorId) {
  return PATIENTS.filter((patient) => patient.floor === floorId);
}

function bedPatient(id, roomId, relX, relY, skin, blanket) {
  return basePatient(id, roomId, "bed", relX, relY, { skin, blanket });
}

function consultationPatient(id, roomId, relX, relY, color, doctorGender, doctorProfileId) {
  return basePatient(id, roomId, "consultation", relX, relY, { color, doctorGender, doctorProfileId });
}

function waitingPatient(id, roomId, relX, relY, color) {
  return basePatient(id, roomId, "waiting", relX, relY, { color });
}

function walkingPatient(id, roomId, relX, relY, color) {
  return basePatient(id, roomId, "walking", relX, relY, { color, phase: id.length * 0.37 });
}

function basePatient(id, roomId, form, relX, relY, style) {
  const placement = placeInRoom(roomId, relX, relY);
  return {
    id,
    floor: placement.floor,
    form,
    roomId,
    relX,
    relY,
    x: placement.x,
    y: placement.y,
    ...style,
  };
}
