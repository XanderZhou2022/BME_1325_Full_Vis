import { door, elevatorProp, elevatorRoom, prop, room } from "../layout.js";

export const rooms = [
  room(5, "nurse_station", "nurse_station", "Nurse Station", 6, 6, 18, 11, "#66bfa2"),
  room(5, "ward_rooms_a", "ward", "Ward Rooms1", 27, 6, 18, 11, "#76c59d"),
  room(5, "ward_rooms_b", "ward", "Ward Rooms2", 48, 6, 18, 11, "#76c59d"),
  room(5, "doctor_office", "doctor_office", "Doctor Office", 6, 21, 18, 11, "#dca768"),
  room(5, "ward_rooms_c", "ward", "Ward Rooms3", 27, 21, 18, 11, "#76c59d"),
  room(5, "ward_support", "waiting", "Family Waiting", 48, 21, 18, 11, "#e7d1a1"),
  elevatorRoom(5),
];

export const doors = [
  door("nurse_station", "bottom", 7.5, 3),
  door("ward_rooms_a", "bottom", 7.5, 3),
  door("ward_rooms_b", "bottom", 7.5, 3),
  door("doctor_office", "top", 7.5, 3),
  door("ward_rooms_c", "top", 7.5, 3),
  door("ward_support", "top", 7.5, 3),
  door("elevator_5", "top", 3.5, 3),
];

export const props = [
  prop(5, 11, 10, 4.2, 1.4, "reception"),
  prop(5, 32, 9, 3.4, 1.3, "bed"),
  prop(5, 38, 9, 3.4, 1.3, "bed"),
  prop(5, 32, 12, 3.4, 1.3, "bed"),
  prop(5, 38, 12, 3.4, 1.3, "bed"),
  prop(5, 53, 9, 3.4, 1.3, "bed"),
  prop(5, 59, 9, 3.4, 1.3, "bed"),
  prop(5, 53, 12, 3.4, 1.3, "bed"),
  prop(5, 59, 12, 3.4, 1.3, "bed"),
  prop(5, 11, 24, 4.2, 1.4, "desk"),
  prop(5, 32, 24, 3.4, 1.3, "bed"),
  prop(5, 38, 24, 3.4, 1.3, "bed"),
  prop(5, 32, 27, 3.4, 1.3, "bed"),
  prop(5, 38, 27, 3.4, 1.3, "bed"),
  prop(5, 53, 24, 3.5, 1.2, "sofa"),
  elevatorProp(5),
];
