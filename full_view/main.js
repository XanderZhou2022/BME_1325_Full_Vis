import { FLOOR_PLATE, PROPS, ROOMS, TILE, WORLD, getFloor, getPropsForFloor, getRoomsForFloor } from "./map.js?v=fit-minimap-player-20260610n";
import { fetchPersonProfile } from "./mock-backend.js?v=fit-minimap-player-20260610n";
import { getPatientsForFloor } from "./patients.js?v=fit-minimap-player-20260610n";
import { getStaffForFloor } from "./staff.js?v=fit-minimap-player-20260610n";
import {
  beginFloorTransition,
  buildGeometry,
  buildPropColliders,
  createCamera,
  createPlayer,
  roomAtPoint,
  updateFloorTransition,
  updatePlayer,
} from "./runtime.js?v=fit-minimap-player-20260610n";
import {
  clearCanvas,
  departmentLabels,
  drawFloorScene,
  drawMinimap,
  drawTransitionWash,
  minimapPointToWorld,
  renderStatusRows,
} from "./render.js?v=fit-minimap-player-20260610n";

const canvas = document.getElementById("hospitalCanvas");
const ctx = canvas.getContext("2d");
const miniMapCanvas = document.getElementById("miniMapCanvas");
const miniMapCtx = miniMapCanvas.getContext("2d");
const floorTitle = document.getElementById("floorTitle");
const floorSubtitle = document.getElementById("floorSubtitle");
const roomReadout = document.getElementById("roomReadout");
const departmentSnapshot = document.getElementById("departmentSnapshot");
const personInfo = document.getElementById("personInfo");
const floorButtons = Array.from(document.querySelectorAll("[data-floor]"));
const zoomInButton = document.getElementById("zoomIn");
const zoomOutButton = document.getElementById("zoomOut");
const zoomFitButton = document.getElementById("zoomFit");
const zoomLabel = document.getElementById("zoomLabel");
const labels = departmentLabels();

const geometry = buildGeometry();
const propColliders = buildPropColliders(PROPS);
const initialFloor = getFloor(1);
const player = createPlayer(initialFloor.spawn, initialFloor.id);
const state = {
  activeFloor: initialFloor.id,
  camera: createCamera(initialFloor.spawn),
  cameraControl: {
    mode: "fit",
    flight: null,
  },
  geometry,
  keys: new Set(),
  player,
  playerTravel: null,
  selectedEntityId: null,
  selectedRoomId: null,
  transition: null,
};

let lastFrame = performance.now();
let hudFloor = null;
let profileRequestId = 0;

applyFitView();
syncHud();
requestAnimationFrame(loop);

window.addEventListener("keydown", (event) => {
  if (isMovementKey(event.code)) {
    event.preventDefault();
    state.playerTravel = null;
    state.selectedRoomId = null;
    state.keys.add(event.code);
  }
});

window.addEventListener("keyup", (event) => {
  if (isMovementKey(event.code)) state.keys.delete(event.code);
});

floorButtons.forEach((button) => {
  button.addEventListener("click", () => {
    const targetFloor = Number(button.dataset.floor);
    const floor = getFloor(targetFloor);
    resetCameraControl();
    beginFloorTransition(state, targetFloor, floor.spawn);
    applyFitView();
    syncHud(targetFloor);
  });
});

zoomInButton.addEventListener("click", () => {
  fitWholeFloor();
});

zoomOutButton.addEventListener("click", () => {
  fitWholeFloor();
});

zoomFitButton.addEventListener("click", () => {
  fitWholeFloor();
});

canvas.addEventListener("pointerdown", (event) => {
  if (state.transition) return;
  event.preventDefault();
});

canvas.addEventListener("click", (event) => {
  if (state.transition) return;
  handleCanvasClick(canvasPoint(event));
});

miniMapCanvas.addEventListener("click", (event) => {
  if (state.transition) return;
  handleMinimapClick(canvasPoint(event, miniMapCanvas), miniMapCanvas);
});

function loop(now) {
  const delta = Math.min(0.033, (now - lastFrame) / 1000);
  lastFrame = now;

  const transition = state.transition;
  const transitionProgress = transition ? Math.min(1, (now - transition.startedAt) / transition.duration) : 0;
  const collisions = [...state.geometry.walls, ...propColliders];

  updatePlayer({
    player: state.player,
    keys: state.keys,
    delta,
    collisions,
    movementLocked: Boolean(state.transition) || Boolean(state.playerTravel),
  });
  updatePlayerTravel(delta);
  updateCameraControl(now);

  render(transition, transitionProgress, now);
  const previousFloor = state.activeFloor;
  updateFloorTransition(state, now);
  if (previousFloor !== state.activeFloor || !state.transition) syncHud(state.activeFloor);

  requestAnimationFrame(loop);
}

function render(transition, progress, now) {
  const visibleFloor = transition ? transition.toFloor : state.activeFloor;
  clearCanvas(ctx, canvas, visibleFloor);

  if (transition) {
    drawFloorScene(ctx, canvas, sceneForFloor(transition.fromFloor, 1 - progress, false, now));
    drawFloorScene(ctx, canvas, sceneForFloor(transition.toFloor, progress, true, now));
    drawTransitionWash(ctx, canvas, progress);
    renderMiniMap(transition.toFloor);
    return;
  }

  drawFloorScene(ctx, canvas, sceneForFloor(state.activeFloor, 1, true, now));
  renderMiniMap(state.activeFloor);
  updateRoomReadout();
}

function renderMiniMap(floorId) {
  miniMapCtx.clearRect(0, 0, miniMapCanvas.width, miniMapCanvas.height);
  drawMinimap(miniMapCtx, miniMapCanvas, {
    floorId,
    rooms: getRoomsForFloor(floorId),
    player: state.player,
    selectedRoomId: state.selectedRoomId,
  });
}

function sceneForFloor(floorId, alpha, drawPlayer, now) {
  return {
    alpha,
    camera: state.camera,
    doors: state.geometry.doors,
    drawPlayer,
    floorId,
    now,
    patients: getPatientsForFloor(floorId),
    player: state.player,
    props: getPropsForFloor(floorId),
    rooms: getRoomsForFloor(floorId),
    selectedEntityId: state.selectedEntityId,
    staff: getStaffForFloor(floorId),
    walls: state.geometry.walls,
  };
}

function fitWholeFloor() {
  state.cameraControl.mode = "fit";
  state.cameraControl.flight = null;
  state.selectedRoomId = null;
  applyFitView();
  updateZoomControls();
  updateRoomReadout();
}

function syncHud(previewFloor = state.activeFloor) {
  hudFloor = previewFloor;

  const floor = getFloor(previewFloor);
  floorTitle.textContent = floor.label;
  floorSubtitle.textContent = floor.subtitle;
  renderStatusRows(departmentSnapshot, floor, labels);

  floorButtons.forEach((button) => {
    const isActive = Number(button.dataset.floor) === previewFloor;
    button.classList.toggle("is-active", isActive);
    button.disabled = Boolean(state.transition);
  });

  updateRoomReadout();
  updateZoomControls();
}

function updateRoomReadout() {
  const selectedRoom = ROOMS.find((item) => item.id === state.selectedRoomId);
  if (state.cameraControl.mode === "fit") {
    const transitionSuffix = state.transition ? " · switching floors" : "";
    if (selectedRoom) {
      const prefix = state.playerTravel ? "Moving player to" : "Player target";
      roomReadout.textContent = `${prefix}: ${selectedRoom.label}${transitionSuffix}`;
      return;
    }
    roomReadout.textContent = `Current view: Full floor${transitionSuffix}`;
    return;
  }

  const room = roomAtPoint(ROOMS, state.player);
  const prefix = selectedRoom ? "Focused area" : "Current area";
  const area = selectedRoom ? selectedRoom.label : room ? room.label : "Hallway";
  const transitionSuffix = state.transition ? " · switching floors" : "";
  roomReadout.textContent = `${prefix}: ${area}${transitionSuffix}`;
}

function isMovementKey(code) {
  return ["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "KeyW", "KeyA", "KeyS", "KeyD"].includes(code);
}

function updateCameraControl() {
  if (state.transition) return;

  state.cameraControl.mode = "fit";
  applyFitView();
}

function handleMinimapClick(point, targetCanvas) {
  const hit = minimapPointToWorld(targetCanvas, point);
  if (!hit?.world) return;

  const targetRoom = roomAtWorldPoint(state.activeFloor, hit.world.x, hit.world.y);
  if (!targetRoom) return;

  const target = roomCenter(targetRoom);
  state.selectedRoomId = targetRoom.id;
  state.keys.clear();
  state.playerTravel = {
    roomId: targetRoom.id,
    targetX: target.x,
    targetY: target.y,
    speed: 260,
  };
  state.cameraControl.mode = "fit";
  state.cameraControl.flight = null;
  updateRoomReadout();
}

function handleCanvasClick(point) {
  const hitEntity = entityAtCanvasPoint(point);
  if (!hitEntity) {
    clearPersonSelection();
    return;
  }

  state.selectedEntityId = hitEntity.id;
  state.selectedRoomId = null;
  renderPersonLoading(hitEntity);
  const requestId = ++profileRequestId;
  fetchPersonProfile(hitEntity.id).then((profile) => {
    if (requestId !== profileRequestId) return;
    renderPersonProfile(profile, hitEntity);
  });
}

function entityAtCanvasPoint(point) {
  const world = worldPointFromCanvas(point);
  const entities = [
    ...getStaffForFloor(state.activeFloor).map((entity) => ({ ...entity, entityType: entity.role })),
    ...clickablePatientsForFloor(state.activeFloor),
  ];

  return entities
    .map((entity) => ({ entity, score: entityHitScore(entity, world) }))
    .filter((hit) => hit.score <= 1)
    .sort((a, b) => a.score - b.score)[0]?.entity || null;
}

function entityHitScore(entity, world) {
  const shape = entity.hitShape || (entity.form === "bed"
    ? { rx: 36, ry: 18 }
    : entity.form === "waiting"
      ? { rx: 26, ry: 24 }
      : { rx: 24, ry: 28 });
  const dx = world.x - entity.x;
  const dy = world.y - entity.y;
  return (dx / shape.rx) ** 2 + (dy / shape.ry) ** 2;
}

function clickablePatientsForFloor(floorId) {
  return getPatientsForFloor(floorId).flatMap((patient) => {
    if (patient.form !== "consultation") return [{ ...patient, entityType: "patient" }];
    return [
      {
        ...patient,
        entityType: "patient",
        x: patient.x - 24,
        y: patient.y + 8,
        hitShape: { rx: 18, ry: 24 },
      },
      {
        id: patient.doctorProfileId,
        floor: patient.floor,
        entityType: "doctor",
        x: patient.x + 26,
        y: patient.y + 8,
        hitShape: { rx: 18, ry: 24 },
      },
    ];
  });
}

function worldPointFromCanvas(point) {
  const zoom = state.camera.zoom || 1;
  return {
    x: (point.x - canvas.width / 2) / zoom + state.camera.x,
    y: (point.y - canvas.height / 2) / zoom + state.camera.y,
  };
}

function clearPersonSelection() {
  state.selectedEntityId = null;
  profileRequestId += 1;
  personInfo.className = "person-info person-info--empty";
  personInfo.textContent = "Click a doctor, nurse, or patient.";
}

function renderPersonLoading(entity) {
  personInfo.className = "person-info person-info--empty";
  personInfo.textContent = `Loading ${roleLabel(entity.entityType)} info...`;
}

function renderPersonProfile(profile, entity) {
  if (!profile) {
    personInfo.className = "person-info person-info--empty";
    personInfo.textContent = "No mock profile found.";
    return;
  }

  personInfo.className = "person-info";
  const rows = [
    infoRow("Role", roleLabel(profile.type)),
    infoRow("Department", profile.department),
    infoRow("Name", profile.name),
  ];
  if (profile.type === "patient") {
    rows.splice(1, 0, infoRow("Patient ID", profile.patientId));
    rows.push(infoRow("Symptoms", profile.symptoms));
  } else {
    rows.splice(1, 0, infoRow("Employee ID", profile.employeeId));
  }
  personInfo.innerHTML = rows.join("");
}

function infoRow(label, value) {
  return `
    <div class="person-info__row">
      <span class="person-info__label">${label}</span>
      <span class="person-info__value">${value}</span>
    </div>
  `;
}

function roleLabel(type) {
  return {
    doctor: "Doctor",
    nurse: "Nurse",
    patient: "Patient",
  }[type] || "Person";
}

function updatePlayerTravel(delta) {
  const travel = state.playerTravel;
  if (!travel) return;

  const dx = travel.targetX - state.player.x;
  const dy = travel.targetY - state.player.y;
  const distanceToTarget = Math.hypot(dx, dy);
  if (distanceToTarget < 4) {
    state.player.x = travel.targetX;
    state.player.y = travel.targetY;
    state.playerTravel = null;
    updateRoomReadout();
    return;
  }

  const step = Math.min(distanceToTarget, travel.speed * delta);
  state.player.x += (dx / distanceToTarget) * step;
  state.player.y += (dy / distanceToTarget) * step;
  if (Math.abs(dx) > Math.abs(dy)) state.player.facing = dx < 0 ? "left" : "right";
  else state.player.facing = dy < 0 ? "up" : "down";
}

function roomAtWorldPoint(floorId, x, y) {
  return getRoomsForFloor(floorId).find((room) => {
    const rx = room.x * TILE;
    const ry = room.y * TILE;
    const rw = room.w * TILE;
    const rh = room.h * TILE;
    return x >= rx && x <= rx + rw && y >= ry && y <= ry + rh;
  }) || null;
}

function roomCenter(room) {
  return {
    x: (room.x + room.w / 2) * TILE,
    y: (room.y + room.h / 2) * TILE,
  };
}

function canvasPoint(event, targetCanvas = canvas) {
  const rect = targetCanvas.getBoundingClientRect();
  return {
    x: ((event.clientX - rect.left) / rect.width) * targetCanvas.width,
    y: ((event.clientY - rect.top) / rect.height) * targetCanvas.height,
  };
}

function resetCameraControl() {
  state.selectedRoomId = null;
  state.selectedEntityId = null;
  state.cameraControl.mode = "fit";
  state.cameraControl.flight = null;
  state.playerTravel = null;
  clearPersonSelection();
}

function applyFitView() {
  state.camera.zoom = minZoom();
  const center = floorPlateCenter();
  state.camera.x = center.x;
  state.camera.y = center.y;
  clampCamera(state.camera);
}

function clampCamera(camera) {
  camera.x = clampCameraValue(camera.x, "x");
  camera.y = clampCameraValue(camera.y, "y");
}

function clampCameraValue(value, axis) {
  const zoom = state.camera.zoom || 1;
  const viewportSize = axis === "x" ? canvas.width / zoom : canvas.height / zoom;
  const worldSize = axis === "x" ? WORLD.width : WORLD.height;
  if (viewportSize >= worldSize) return worldSize / 2;
  return clamp(value, viewportSize / 2, worldSize - viewportSize / 2);
}

function minZoom() {
  const plateWidth = FLOOR_PLATE.w * TILE;
  const plateHeight = FLOOR_PLATE.h * TILE;
  return Number((Math.min(canvas.width / plateWidth, canvas.height / plateHeight) * 0.96).toFixed(3));
}

function floorPlateCenter() {
  return {
    x: (FLOOR_PLATE.x + FLOOR_PLATE.w / 2) * TILE,
    y: (FLOOR_PLATE.y + FLOOR_PLATE.h / 2) * TILE,
  };
}

function updateZoomControls() {
  const zoom = state.camera.zoom || 1;
  zoomLabel.textContent = `${Math.round(zoom * 100)}%`;
  zoomOutButton.disabled = true;
  zoomInButton.disabled = true;
  zoomFitButton.classList.add("is-active");
}

function clamp(value, min, max) {
  if (max < min) return (min + max) / 2;
  return Math.min(max, Math.max(min, value));
}
