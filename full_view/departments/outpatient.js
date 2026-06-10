import { door, elevatorProp, elevatorRoom, prop, room } from "../layout.js";

export const rooms = [
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
];

export const doors = [
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
];

export const props = [
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
];
