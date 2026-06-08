import { FLOOR_PLATE, PROPS, ROOMS, TILE, WORLD, getFloor, getPropsForFloor, getRoomsForFloor } from "./map.js";
import {
  beginFloorTransition,
  buildGeometry,
  buildPropColliders,
  createCamera,
  createPlayer,
  roomAtPoint,
  updateCamera,
  updateFloorTransition,
  updatePlayer,
} from "./runtime.js";
import {
  clearCanvas,
  departmentLabels,
  drawFloorScene,
  drawMinimap,
  drawTransitionWash,
  minimapPointToWorld,
  renderStatusRows,
} from "./render.js";

const canvas = document.getElementById("hospitalCanvas");
const ctx = canvas.getContext("2d");
const floorTitle = document.getElementById("floorTitle");
const floorSubtitle = document.getElementById("floorSubtitle");
const roomReadout = document.getElementById("roomReadout");
const departmentSnapshot = document.getElementById("departmentSnapshot");
const floorButtons = Array.from(document.querySelectorAll("[data-floor]"));
const zoomInButton = document.getElementById("zoomIn");
const zoomOutButton = document.getElementById("zoomOut");
const zoomFitButton = document.getElementById("zoomFit");
const zoomLabel = document.getElementById("zoomLabel");
const labels = departmentLabels();

const MAX_ZOOM = 1.65;
const ZOOM_STEP = 0.16;

const geometry = buildGeometry();
const propColliders = buildPropColliders(PROPS);
const initialFloor = getFloor(1);
const player = createPlayer(initialFloor.spawn, initialFloor.id);
const state = {
  activeFloor: initialFloor.id,
  camera: createCamera(initialFloor.spawn),
  cameraControl: {
    mode: "follow",
    drag: null,
    flight: null,
  },
  geometry,
  keys: new Set(),
  player,
  selectedRoomId: null,
  transition: null,
};

let lastFrame = performance.now();
let hudFloor = null;

syncHud();
requestAnimationFrame(loop);

window.addEventListener("keydown", (event) => {
  if (isMovementKey(event.code)) {
    event.preventDefault();
    state.cameraControl.mode = "follow";
    state.cameraControl.flight = null;
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
    const preserveFit = state.cameraControl.mode === "fit";
    resetCameraControl(preserveFit ? "fit" : "follow");
    beginFloorTransition(state, targetFloor, floor.spawn);
    if (preserveFit) applyFitView();
    syncHud(targetFloor);
  });
});

zoomInButton.addEventListener("click", () => {
  setZoom(state.camera.zoom + ZOOM_STEP);
});

zoomOutButton.addEventListener("click", () => {
  setZoom(state.camera.zoom - ZOOM_STEP);
});

zoomFitButton.addEventListener("click", () => {
  fitWholeFloor();
});

canvas.addEventListener("pointerdown", (event) => {
  if (state.transition) return;
  const point = canvasPoint(event);
  const minimapHit = minimapPointToWorld(canvas, point);
  if (minimapHit?.insidePanel) {
    state.cameraControl.minimapPress = { point, startedAt: performance.now() };
    return;
  }

  state.cameraControl.drag = {
    pointerId: event.pointerId,
    lastX: event.clientX,
    lastY: event.clientY,
    moved: false,
  };
  state.cameraControl.mode = "free";
  state.cameraControl.flight = null;
  canvas.classList.add("is-dragging");
  canvas.setPointerCapture(event.pointerId);
});

canvas.addEventListener("pointermove", (event) => {
  const drag = state.cameraControl.drag;
  if (!drag || drag.pointerId !== event.pointerId) return;
  const rect = canvas.getBoundingClientRect();
  const dx = (((event.clientX - drag.lastX) / rect.width) * canvas.width) / state.camera.zoom;
  const dy = (((event.clientY - drag.lastY) / rect.height) * canvas.height) / state.camera.zoom;
  state.camera.x -= dx;
  state.camera.y -= dy;
  clampCamera(state.camera);
  drag.lastX = event.clientX;
  drag.lastY = event.clientY;
  drag.moved = true;
});

canvas.addEventListener("pointerup", (event) => {
  const press = state.cameraControl.minimapPress;
  if (press) {
    const point = canvasPoint(event);
    state.cameraControl.minimapPress = null;
    if (distance(point, press.point) < 8) handleMinimapClick(point);
    return;
  }
  finishDrag(event.pointerId);
});

canvas.addEventListener("pointercancel", (event) => {
  state.cameraControl.minimapPress = null;
  finishDrag(event.pointerId);
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
    movementLocked: Boolean(state.transition),
  });
  updateCameraControl(now);

  render(transition, transitionProgress);
  const previousFloor = state.activeFloor;
  updateFloorTransition(state, now);
  if (previousFloor !== state.activeFloor || !state.transition) syncHud(state.activeFloor);

  requestAnimationFrame(loop);
}

function render(transition, progress) {
  const visibleFloor = transition ? transition.toFloor : state.activeFloor;
  clearCanvas(ctx, canvas, visibleFloor);

  if (transition) {
    drawFloorScene(ctx, canvas, sceneForFloor(transition.fromFloor, 1 - progress, false));
    drawFloorScene(ctx, canvas, sceneForFloor(transition.toFloor, progress, true));
    drawTransitionWash(ctx, canvas, progress);
    drawMinimap(ctx, canvas, {
      floorId: transition.toFloor,
      rooms: getRoomsForFloor(transition.toFloor),
      player: state.player,
      selectedRoomId: state.selectedRoomId,
    });
    return;
  }

  drawFloorScene(ctx, canvas, sceneForFloor(state.activeFloor, 1, true));
  drawMinimap(ctx, canvas, {
    floorId: state.activeFloor,
    rooms: getRoomsForFloor(state.activeFloor),
    player: state.player,
    selectedRoomId: state.selectedRoomId,
  });
  updateRoomReadout();
}

function sceneForFloor(floorId, alpha, drawPlayer) {
  return {
    alpha,
    camera: state.camera,
    doors: state.geometry.doors,
    drawPlayer,
    floorId,
    player: state.player,
    props: getPropsForFloor(floorId),
    rooms: getRoomsForFloor(floorId),
    walls: state.geometry.walls,
  };
}

function setZoom(nextZoom) {
  const zoom = clamp(nextZoom, minZoom(), MAX_ZOOM);
  state.camera.zoom = Number(zoom.toFixed(3));
  state.cameraControl.flight = null;
  state.cameraControl.mode = state.cameraControl.mode === "follow" ? "follow" : "free";
  clampCamera(state.camera);
  updateZoomControls();
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
  if (state.cameraControl.mode === "fit") {
    const transitionSuffix = state.transition ? " · switching floors" : "";
    roomReadout.textContent = `Current view: Full floor${transitionSuffix}`;
    return;
  }

  const room = roomAtPoint(ROOMS, state.player);
  const selectedRoom = ROOMS.find((item) => item.id === state.selectedRoomId);
  const prefix = selectedRoom ? "Focused area" : "Current area";
  const area = selectedRoom ? selectedRoom.label : room ? room.label : "Hallway";
  const transitionSuffix = state.transition ? " · switching floors" : "";
  roomReadout.textContent = `${prefix}: ${area}${transitionSuffix}`;
}

function isMovementKey(code) {
  return ["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "KeyW", "KeyA", "KeyS", "KeyD"].includes(code);
}

function updateCameraControl(now) {
  if (state.transition || state.cameraControl.drag) return;

  if (state.cameraControl.mode === "fit") {
    applyFitView();
    return;
  }

  const flight = state.cameraControl.flight;
  if (flight) {
    const progress = Math.min(1, (now - flight.startedAt) / flight.duration);
    const eased = easeInOutCubic(progress);
    state.camera.x = lerp(flight.fromX, flight.toX, eased);
    state.camera.y = lerp(flight.fromY, flight.toY, eased);
    clampCamera(state.camera);
    if (progress >= 1) {
      state.cameraControl.flight = null;
      state.cameraControl.mode = "free";
    }
    return;
  }

  if (state.cameraControl.mode === "follow") {
    updateCamera(state.camera, state.player);
    clampCamera(state.camera);
  }
}

function handleMinimapClick(point) {
  const hit = minimapPointToWorld(canvas, point);
  if (!hit?.world) return;

  const targetRoom = roomAtWorldPoint(state.activeFloor, hit.world.x, hit.world.y);
  if (!targetRoom) return;

  const target = roomCenter(targetRoom);
  state.selectedRoomId = targetRoom.id;
  state.cameraControl.mode = "flight";
  state.cameraControl.flight = {
    fromX: state.camera.x,
    fromY: state.camera.y,
    toX: clampCameraValue(target.x, "x"),
    toY: clampCameraValue(target.y, "y"),
    startedAt: performance.now(),
    duration: 720,
  };
  updateRoomReadout();
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

function canvasPoint(event) {
  const rect = canvas.getBoundingClientRect();
  return {
    x: ((event.clientX - rect.left) / rect.width) * canvas.width,
    y: ((event.clientY - rect.top) / rect.height) * canvas.height,
  };
}

function finishDrag(pointerId) {
  const drag = state.cameraControl.drag;
  if (!drag || drag.pointerId !== pointerId) return;
  state.cameraControl.drag = null;
  canvas.classList.remove("is-dragging");
  if (canvas.hasPointerCapture(pointerId)) canvas.releasePointerCapture(pointerId);
}

function resetCameraControl(mode = "follow") {
  state.selectedRoomId = null;
  state.cameraControl.mode = mode;
  state.cameraControl.flight = null;
  state.cameraControl.drag = null;
  state.cameraControl.minimapPress = null;
  canvas.classList.remove("is-dragging");
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
  zoomOutButton.disabled = zoom <= minZoom() + 0.001;
  zoomInButton.disabled = zoom >= MAX_ZOOM - 0.001;
  zoomFitButton.classList.toggle("is-active", state.cameraControl.mode === "fit");
}

function distance(a, b) {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

function easeInOutCubic(t) {
  return t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2;
}

function lerp(a, b, t) {
  return a + (b - a) * t;
}

function clamp(value, min, max) {
  if (max < min) return (min + max) / 2;
  return Math.min(max, Math.max(min, value));
}
