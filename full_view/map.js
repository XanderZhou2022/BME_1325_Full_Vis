import { FLOORS } from "./floors.js";
import { FLOOR_PLATE, TILE, WORLD } from "./layout.js";
import { DEPARTMENT_STATUS, ROOM_KIND_LABELS } from "./status.js";

import * as emergency from "./departments/emergency.js";
import * as outpatient from "./departments/outpatient.js";
import * as icu from "./departments/icu.js";
import * as mdt from "./departments/mdt.js";
import * as ward from "./departments/ward.js";

const departmentMaps = [emergency, outpatient, icu, mdt, ward];

export { DEPARTMENT_STATUS, FLOOR_PLATE, FLOORS, ROOM_KIND_LABELS, TILE, WORLD };

export const ROOMS = departmentMaps.flatMap((department) => department.rooms);
export const DOORS = departmentMaps.flatMap((department) => department.doors);
export const PROPS = departmentMaps.flatMap((department) => department.props);

export function getFloor(id) {
  return FLOORS.find((floor) => floor.id === id) || FLOORS[0];
}

export function getRoomsForFloor(floorId) {
  return ROOMS.filter((room) => room.floor === floorId);
}

export function getPropsForFloor(floorId) {
  return PROPS.filter((item) => item.floor === floorId);
}
