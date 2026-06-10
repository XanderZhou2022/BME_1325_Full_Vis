import { door, elevatorProp, elevatorRoom, prop, room } from "../layout.js";

export const rooms = [
  room(1, "emergency_intake", "emergency", "Emergency Intake", 6, 6, 18, 11, "#d85e5e"),
  room(1, "rescue_bay", "rescue", "Rescue Bay", 27, 6, 18, 11, "#e05f5f"),
  room(1, "emergency_consult", "emergency_consult", "ER Consultation", 48, 6, 18, 11, "#c96b58"),
  room(1, "entrance_1", "entrance", "Main Entrance", 6, 21, 18, 11, "#b99163"),
  room(1, "observation_1", "emergency", "Emergency Observation", 27, 21, 18, 11, "#d9736d"),
  room(1, "emergency_support", "waiting", "Emergency Waiting", 48, 21, 18, 11, "#e7d1a1"),
  elevatorRoom(1),
];

export const doors = [
  door("emergency_intake", "bottom", 7.5, 3),
  door("rescue_bay", "bottom", 7.5, 3),
  door("emergency_consult", "bottom", 7.5, 3),
  door("entrance_1", "top", 7.5, 3),
  door("observation_1", "top", 7.5, 3),
  door("emergency_support", "top", 7.5, 3),
  door("elevator_1", "top", 3.5, 3),
];

export const props = [
  prop(1, 10, 9, 5, 1.5, "reception"),
  prop(1, 32, 9, 3.4, 1.4, "bed"),
  prop(1, 38, 9, 3.4, 1.4, "bed"),
  prop(1, 53, 9, 3.5, 1.3, "desk"),
  prop(1, 10, 24, 4, 1.4, "desk"),
  prop(1, 32, 24, 3.4, 1.4, "bed"),
  prop(1, 53, 24, 3.5, 1.3, "sofa"),
  elevatorProp(1),
];
