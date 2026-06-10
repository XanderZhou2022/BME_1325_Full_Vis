import { TILE } from "./layout.js";

export const PATIENTS = [
  // Walking patients in open circulation space.
  walkingPatient("walk-er-1", 1, 56, 27, "#5f8ec9"),
  walkingPatient("walk-op-1", 2, 58, 27, "#5f8ec9"),
  walkingPatient("walk-mdt-1", 4, 59, 27, "#8f7ed0"),

  // Waiting patients in waiting areas.
  waitingPatient("wait-er-1", 1, 53, 26, "#7899c6"),
  waitingPatient("wait-er-2", 1, 57, 26, "#c69072"),
  waitingPatient("wait-op-1", 2, 42, 33, "#7899c6"),
  waitingPatient("wait-op-2", 2, 50, 33, "#c69072"),
  waitingPatient("wait-ward-1", 5, 53, 26, "#7fa98f"),

  // Outpatient consultation scenes.
  consultationPatient("consult-a", 2, 41, 10, "#5f8ec9", "female", "doctor-consult-a"),
  consultationPatient("consult-b", 2, 56, 10, "#8a79c9", "male", "doctor-consult-b"),
  consultationPatient("consult-int", 2, 11, 21, "#5f8ec9", "male", "doctor-consult-int"),

  // Bed patients in ICU and ward.
  bedPatient("icu-bed-a", 3, 32, 9.2, "#f2c799", "#d46d8e"),
  bedPatient("icu-bed-b", 3, 38, 9.2, "#f2c799", "#d46d8e"),
  bedPatient("icu-isolation", 3, 53, 24.2, "#f2c799", "#cf6f8c"),
  bedPatient("ward-bed-a", 5, 32, 9.2, "#f2c799", "#76c59d"),
  bedPatient("ward-bed-b", 5, 38, 9.2, "#f2c799", "#76c59d"),
  bedPatient("ward-bed-c", 5, 32, 24.2, "#f2c799", "#76c59d"),
];

export function getPatientsForFloor(floorId) {
  return PATIENTS.filter((patient) => patient.floor === floorId);
}

function bedPatient(id, floor, x, y, skin, blanket) {
  return basePatient(id, floor, "bed", x, y, { skin, blanket });
}

function consultationPatient(id, floor, x, y, color, doctorGender, doctorProfileId) {
  return basePatient(id, floor, "consultation", x, y, { color, doctorGender, doctorProfileId });
}

function waitingPatient(id, floor, x, y, color) {
  return basePatient(id, floor, "waiting", x, y, { color });
}

function walkingPatient(id, floor, x, y, color) {
  return basePatient(id, floor, "walking", x, y, { color, phase: id.length * 0.37 });
}

function basePatient(id, floor, form, x, y, style) {
  return {
    id,
    floor,
    form,
    x: x * TILE,
    y: y * TILE,
    ...style,
  };
}
