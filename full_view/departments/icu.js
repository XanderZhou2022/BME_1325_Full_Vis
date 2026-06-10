import { door, elevatorProp, elevatorRoom, prop, room } from "../layout.js";

export const rooms = [
  room(3, "icu_station", "icu_station", "ICU Nurse Station", 6, 6, 18, 11, "#d46d8e"),
  room(3, "icu_beds_a", "icu", "ICU Beds A", 27, 6, 18, 11, "#db7895"),
  room(3, "icu_beds_b", "icu", "ICU Beds B", 48, 6, 18, 11, "#db7895"),
  room(3, "monitor_center", "monitor", "Monitoring Center", 6, 21, 18, 11, "#79bcc8"),
  room(3, "icu_support", "waiting", "Family Support", 27, 21, 18, 11, "#e7d1a1"),
  room(3, "icu_isolation", "icu", "Isolation Beds", 48, 21, 18, 11, "#cf6f8c"),
  elevatorRoom(3),
];

export const doors = [
  door("icu_station", "bottom", 7.5, 3),
  door("icu_beds_a", "bottom", 7.5, 3),
  door("icu_beds_b", "bottom", 7.5, 3),
  door("monitor_center", "top", 7.5, 3),
  door("icu_support", "top", 7.5, 3),
  door("icu_isolation", "top", 7.5, 3),
  door("elevator_3", "top", 3.5, 3),
];

export const props = [
  prop(3, 11, 10, 4.2, 1.4, "reception"),
  prop(3, 32, 9, 3.4, 1.3, "bed"),
  prop(3, 38, 9, 3.4, 1.3, "bed"),
  prop(3, 53, 9, 3.4, 1.3, "bed"),
  prop(3, 11, 24, 3.4, 1.3, "screen"),
  prop(3, 33, 24, 3.5, 1.2, "sofa"),
  prop(3, 53, 24, 3.4, 1.3, "bed"),
  elevatorProp(3),
];
