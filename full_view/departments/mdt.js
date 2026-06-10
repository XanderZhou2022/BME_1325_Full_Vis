import { door, elevatorProp, elevatorRoom, prop, room } from "../layout.js";

export const rooms = [
  room(4, "mdt_center", "mdt", "MDT Center", 6, 6, 18, 11, "#9b87f5"),
  room(4, "mdt_meeting", "mdt_meeting", "Conference Room", 27, 6, 18, 11, "#a992f7"),
  room(4, "imaging_review", "imaging_review", "Imaging Review", 48, 6, 18, 11, "#67b7cf"),
  room(4, "specialist_room", "specialist", "Specialist Planning", 6, 21, 18, 11, "#dca768"),
  room(4, "mdt_records", "doctor_office", "Records Office", 27, 21, 18, 11, "#c79b69"),
  room(4, "mdt_lounge", "waiting", "Consult Waiting", 48, 21, 18, 11, "#e7d1a1"),
  elevatorRoom(4),
];

export const doors = [
  door("mdt_center", "bottom", 7.5, 3),
  door("mdt_meeting", "bottom", 7.5, 3),
  door("imaging_review", "bottom", 7.5, 3),
  door("specialist_room", "top", 7.5, 3),
  door("mdt_records", "top", 7.5, 3),
  door("mdt_lounge", "top", 7.5, 3),
  door("elevator_4", "top", 3.5, 3),
];

export const props = [
  prop(4, 11, 10, 5, 1.8, "table"),
  prop(4, 32, 10, 5, 1.8, "table"),
  prop(4, 53, 10, 5, 1.6, "screen"),
  prop(4, 11, 24, 4, 1.4, "desk"),
  prop(4, 32, 24, 4, 1.4, "cabinet"),
  prop(4, 53, 24, 4, 1.4, "sofa"),
  elevatorProp(4),
];
