import assert from "node:assert/strict";
import { cp, mkdtemp, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const sourceRoot = path.resolve(
  process.env.FULLVIEW_SOURCE_ROOT
    || path.resolve(path.dirname(fileURLToPath(import.meta.url)), ".."),
);
const tempRoot = await mkdtemp(path.join(os.tmpdir(), "fullview-path-test-"));

const consultToQueue = {
  "R-OP-INTERNAL": "R-OP-QUEUE-INTERNAL",
  "R-OP-INTERNAL-B": "R-OP-QUEUE-INTERNAL",
  "R-OP-SURGERY": "R-OP-QUEUE-SURGERY",
  "R-OP-SURGERY-B": "R-OP-QUEUE-SURGERY",
  "R-OP-PEDIATRICS": "R-OP-QUEUE-PEDIATRICS",
  "R-OP-FEVER": "R-OP-QUEUE-FEVER",
  "R-OP-OBGYN": "R-OP-QUEUE-OBGYN",
  "R-OP-OPHTHALMOLOGY": "R-OP-QUEUE-OPHTHALMOLOGY",
  "R-OP-ENT": "R-OP-QUEUE-ENT",
  "R-OP-DENTISTRY": "R-OP-QUEUE-DENTISTRY",
  "R-OP-DERMATOLOGY": "R-OP-QUEUE-DERMATOLOGY",
  "R-OP-PSYCHIATRY": "R-OP-QUEUE-PSYCHIATRY",
  "R-OP-REHABILITATION": "R-OP-QUEUE-REHABILITATION",
  "R-OP-PAIN": "R-OP-QUEUE-PAIN",
};
const outpatientQueues = [...new Set(Object.values(consultToQueue))];

try {
  for (const file of [
    "layout.js",
    "map.js",
    "map-config.json",
    "pathfinding.js",
    "runtime.js",
    "status.js",
  ]) {
    await cp(path.join(sourceRoot, file), path.join(tempRoot, file));
  }
  await writeFile(path.join(tempRoot, "package.json"), '{"type":"module"}\n');

  const map = await import(pathToFileURL(path.join(tempRoot, "map.js")));
  const runtime = await import(pathToFileURL(path.join(tempRoot, "runtime.js")));
  const pathfinding = await import(pathToFileURL(path.join(tempRoot, "pathfinding.js")));

  const geometry = runtime.buildGeometry();
  const collisions = [
    ...geometry.walls,
    ...runtime.buildPropColliders(map.PROPS),
  ];
  const roomById = (roomId) => {
    const room = map.ROOMS.find((candidate) => candidate.id === roomId);
    assert.ok(room, `missing room ${roomId}`);
    return room;
  };
  const roomCenter = (room) => ({
    x: (room.x + room.w / 2) * map.TILE,
    y: (room.y + room.h / 2) * map.TILE,
  });
  const route = (fromRoomId, toRoomId) => {
    const fromRoom = roomById(fromRoomId);
    const toRoom = roomById(toRoomId);
    return pathfinding.createRoomPath({
      floorId: fromRoom.floor,
      start: roomCenter(fromRoom),
      targetRoom: toRoom,
      targetPoint: roomCenter(toRoom),
      collisions,
    });
  };
  const routeFromPoint = (fromRoom, start, toRoomId) => {
    const toRoom = roomById(toRoomId);
    return pathfinding.createRoomPath({
      floorId: fromRoom.floor,
      start,
      targetRoom: toRoom,
      targetPoint: roomCenter(toRoom),
      collisions,
    });
  };
  const routeBetweenPoints = (fromRoom, start, toRoom, targetPoint) => {
    return pathfinding.createRoomPath({
      floorId: fromRoom.floor,
      start,
      targetRoom: toRoom,
      targetPoint,
      collisions,
    });
  };

  for (const [consultRoomId, queueRoomId] of Object.entries(consultToQueue)) {
    const consultRoom = roomById(consultRoomId);
    assert.ok(
      route(queueRoomId, consultRoomId)?.length,
      `${queueRoomId} cannot reach ${consultRoomId}`,
    );
    assert.ok(
      route(consultRoomId, "R-OP-PAYMENT")?.length,
      `${consultRoomId} cannot reach R-OP-PAYMENT; the frontend would snapshot-jump`,
    );
    for (const [relX, relY] of [[0.25, 0.58], [0.5, 0.68], [0.75, 0.78]]) {
      const start = {
        x: (consultRoom.x + consultRoom.w * relX) * map.TILE,
        y: (consultRoom.y + consultRoom.h * relY) * map.TILE,
      };
      assert.ok(
        routeFromPoint(consultRoom, start, "R-OP-PAYMENT")?.length,
        `${consultRoomId} placement ${relX},${relY} cannot exit to payment`,
      );
    }
  }

  const requiredRoutes = [
    ["R-OP-PAYMENT", "R-OP-LAB", "payment to diagnostic center"],
    ...Object.keys(consultToQueue).map((consultRoomId) => [
      consultRoomId,
      "R-OP-PHARMACY",
      "consult room to pharmacy",
    ]),
    ...Object.keys(consultToQueue).map((consultRoomId) => [
      consultRoomId,
      "R-OP-QUEUE-SURGERY",
      "consult room to surgery procedure queue",
    ]),
    ...outpatientQueues.map((queueRoomId) => [
      "R-OP-LAB",
      queueRoomId,
      "diagnostic center back to specialty queue",
    ]),
  ];

  const unreachableRoutes = requiredRoutes
    .filter(([fromRoomId, toRoomId]) => !route(fromRoomId, toRoomId)?.length)
    .map(([fromRoomId, toRoomId, label]) => `${label}: ${fromRoomId} -> ${toRoomId}`);
  assert.deepEqual(
    unreachableRoutes,
    [],
    `outpatient routes would snapshot-jump:\n${unreachableRoutes.join("\n")}`,
  );

  const procedureRoom = roomById("R-OP-SURGERY-PROCEDURE");
  const procedureBedPoints = map.PROPS
    .filter((item) => item.roomId === procedureRoom.id && item.type === "bed")
    .map((item) => ({
      x: item.x * map.TILE,
      y: (item.y + 0.2) * map.TILE,
    }));
  assert.ok(procedureBedPoints.length, "surgery procedure room has no bed placement points");
  for (const bedPoint of procedureBedPoints) {
    assert.ok(
      routeBetweenPoints(
        roomById("R-OP-QUEUE-SURGERY"),
        roomCenter(roomById("R-OP-QUEUE-SURGERY")),
        procedureRoom,
        bedPoint,
      )?.length,
      "surgery queue cannot reach a procedure bed",
    );
    for (const queueRoomId of outpatientQueues) {
      assert.ok(
        routeFromPoint(procedureRoom, bedPoint, queueRoomId)?.length,
        `surgery procedure bed cannot return to ${queueRoomId}`,
      );
    }
  }

  console.log(
    `PASS: ${Object.keys(consultToQueue).length} consult rooms and ${requiredRoutes.length + procedureBedPoints.length * (outpatientQueues.length + 1)} payment/pharmacy/procedure routes avoid snapshot fallback.`,
  );
} finally {
  await rm(tempRoot, { recursive: true, force: true });
}
