/**
 * Generate simple .glb 3D models for Cesium entities.
 * Creates: airplane.glb, ship.glb, satellite.glb
 *
 * These are minimal glTF 2.0 binary files with colored geometry.
 * No external dependencies needed — builds raw glTF JSON + binary buffers.
 */
import { writeFileSync } from "fs";
import { join, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const outDir = join(__dirname, "..", "public", "models");

// ─── glTF Builder Helpers ───

function createGLB(gltfJson, binBuffer) {
  const jsonStr = JSON.stringify(gltfJson);
  // Pad JSON to 4-byte alignment
  const jsonPadded = jsonStr + " ".repeat((4 - (jsonStr.length % 4)) % 4);
  const jsonBuf = Buffer.from(jsonPadded, "utf8");
  // Pad binary to 4-byte alignment
  const binPad = Buffer.alloc((4 - (binBuffer.length % 4)) % 4);
  const binBuf = Buffer.concat([binBuffer, binPad]);

  const headerSize = 12;
  const jsonChunkSize = 8 + jsonBuf.length;
  const binChunkSize = 8 + binBuf.length;
  const totalSize = headerSize + jsonChunkSize + binChunkSize;

  const glb = Buffer.alloc(totalSize);
  let offset = 0;

  // Header
  glb.writeUInt32LE(0x46546c67, offset); offset += 4; // "glTF"
  glb.writeUInt32LE(2, offset); offset += 4;           // version
  glb.writeUInt32LE(totalSize, offset); offset += 4;

  // JSON chunk
  glb.writeUInt32LE(jsonBuf.length, offset); offset += 4;
  glb.writeUInt32LE(0x4e4f534a, offset); offset += 4; // "JSON"
  jsonBuf.copy(glb, offset); offset += jsonBuf.length;

  // Binary chunk
  glb.writeUInt32LE(binBuf.length, offset); offset += 4;
  glb.writeUInt32LE(0x004e4942, offset); offset += 4; // "BIN\0"
  binBuf.copy(glb, offset);

  return glb;
}

function float32Array(arr) {
  return Buffer.from(new Float32Array(arr).buffer);
}

function uint16Array(arr) {
  return Buffer.from(new Uint16Array(arr).buffer);
}

function computeBounds(positions) {
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  for (let i = 0; i < positions.length; i += 3) {
    for (let j = 0; j < 3; j++) {
      min[j] = Math.min(min[j], positions[i + j]);
      max[j] = Math.max(max[j], positions[i + j]);
    }
  }
  return { min, max };
}

function buildSimpleModel(positions, indices, color, scale = 1) {
  const scaledPositions = positions.map(p => p * scale);
  const bounds = computeBounds(scaledPositions);

  const posBuf = float32Array(scaledPositions);
  const idxBuf = uint16Array(indices);
  const binBuffer = Buffer.concat([posBuf, idxBuf]);

  const gltf = {
    asset: { version: "2.0", generator: "cerebro-model-gen" },
    scene: 0,
    scenes: [{ nodes: [0] }],
    nodes: [{ mesh: 0 }],
    meshes: [{
      primitives: [{
        attributes: { POSITION: 0 },
        indices: 1,
        material: 0,
      }],
    }],
    accessors: [
      {
        bufferView: 0,
        componentType: 5126, // FLOAT
        count: scaledPositions.length / 3,
        type: "VEC3",
        min: bounds.min,
        max: bounds.max,
      },
      {
        bufferView: 1,
        componentType: 5123, // UNSIGNED_SHORT
        count: indices.length,
        type: "SCALAR",
        min: [Math.min(...indices)],
        max: [Math.max(...indices)],
      },
    ],
    bufferViews: [
      { buffer: 0, byteOffset: 0, byteLength: posBuf.length, target: 34962 },
      { buffer: 0, byteOffset: posBuf.length, byteLength: idxBuf.length, target: 34963 },
    ],
    buffers: [{ byteLength: binBuffer.length }],
    materials: [{
      pbrMetallicRoughness: {
        baseColorFactor: color,
        metallicFactor: 0.3,
        roughnessFactor: 0.7,
      },
      emissiveFactor: [color[0] * 0.2, color[1] * 0.2, color[2] * 0.2],
    }],
  };

  return createGLB(gltf, binBuffer);
}

// ─── Airplane Model ───
// Simple jet shape: fuselage (elongated diamond) + wings + tail
function createAirplane() {
  // Oriented: nose = +Y (north in Cesium), wings along X, up = +Z
  const positions = [
    // Fuselage (elongated octagonal prism, simplified to diamond cross-section)
    0, 5, 0,       // 0: nose
    0.4, 1, 0.2,   // 1: front-top-right
    -0.4, 1, 0.2,  // 2: front-top-left
    0.4, 1, -0.1,  // 3: front-bottom-right
    -0.4, 1, -0.1, // 4: front-bottom-left
    0.3, -3, 0.15, // 5: rear-top-right
    -0.3, -3, 0.15,// 6: rear-top-left
    0.3, -3, -0.1, // 7: rear-bottom-right
    -0.3, -3, -0.1,// 8: rear-bottom-left
    0, -4, 0,      // 9: tail point

    // Wings (flat triangles at y=0)
    5, -0.5, 0,    // 10: right wingtip
    -5, -0.5, 0,   // 11: left wingtip
    1.5, 1, 0,     // 12: right wing root front
    -1.5, 1, 0,    // 13: left wing root front
    0.8, -1.5, 0,  // 14: right wing root rear
    -0.8, -1.5, 0, // 15: left wing root rear

    // Tail fin (vertical)
    0, -3, 0.15,   // 16: tail fin base
    0, -4, 1.2,    // 17: tail fin top
    0, -2, 0.15,   // 18: tail fin front

    // Horizontal stabilizers
    2, -3.5, 0,    // 19: right stab tip
    -2, -3.5, 0,   // 20: left stab tip
    0.3, -2.5, 0,  // 21: right stab root
    -0.3, -2.5, 0, // 22: left stab root
  ];

  const indices = [
    // Nose cone
    0, 1, 2,  0, 3, 1,  0, 2, 4,  0, 4, 3,
    // Fuselage sides
    1, 5, 6,  1, 6, 2,  3, 7, 5,  3, 5, 1,  4, 8, 7,  4, 7, 3,  2, 6, 8,  2, 8, 4,
    // Tail cone
    5, 9, 6,  7, 9, 5,  8, 9, 7,  6, 9, 8,
    // Right wing
    12, 10, 14,  12, 14, 3,
    // Left wing
    13, 15, 11,  13, 4, 15,
    // Tail fin
    16, 17, 18,  16, 18, 17,
    // Right stabilizer
    21, 19, 5,
    // Left stabilizer
    22, 6, 20,
  ];

  return buildSimpleModel(positions, indices, [0.85, 0.85, 0.9, 1.0], 50); // ~500m model scaled for visibility
}

// ─── Ship Model ───
// Simple hull + superstructure
function createShip() {
  // Oriented: bow = +Y, port = -X, starboard = +X, up = +Z
  const positions = [
    // Hull bottom
    0, 6, -0.5,    // 0: bow bottom
    1.5, 2, -0.5,  // 1: starboard mid bottom
    -1.5, 2, -0.5, // 2: port mid bottom
    1.5, -4, -0.5, // 3: starboard aft bottom
    -1.5, -4, -0.5,// 4: port aft bottom
    0, -5, -0.5,   // 5: stern bottom

    // Hull top (deck level)
    0, 6.5, 0.5,   // 6: bow top
    2, 2, 0.5,     // 7: starboard mid top
    -2, 2, 0.5,    // 8: port mid top
    2, -4, 0.5,    // 9: starboard aft top
    -2, -4, 0.5,   // 10: port aft top
    0, -5.5, 0.5,  // 11: stern top

    // Superstructure (bridge)
    1, -1, 0.5,    // 12: bridge front-right
    -1, -1, 0.5,   // 13: bridge front-left
    1, -3, 0.5,    // 14: bridge rear-right
    -1, -3, 0.5,   // 15: bridge rear-left
    1, -1, 2.5,    // 16: bridge top front-right
    -1, -1, 2.5,   // 17: bridge top front-left
    1, -3, 2.5,    // 18: bridge top rear-right
    -1, -3, 2.5,   // 19: bridge top rear-left

    // Mast
    0, -2, 2.5,    // 20: mast base
    0, -2, 4,      // 21: mast top
  ];

  const indices = [
    // Hull sides
    0, 6, 7,  0, 7, 1,  0, 2, 8,  0, 8, 6,
    1, 7, 9,  1, 9, 3,  2, 4, 10, 2, 10, 8,
    3, 9, 11, 3, 11, 5,  4, 5, 11, 4, 11, 10,
    // Hull bottom
    0, 1, 3,  0, 3, 5,  0, 5, 4,  0, 4, 2,
    // Deck
    6, 8, 7,  7, 8, 10, 7, 10, 9, 9, 10, 11,
    // Bridge walls
    12, 16, 17, 12, 17, 13,  // front
    14, 18, 16, 14, 16, 12,  // right
    15, 19, 18, 15, 18, 14,  // back
    13, 17, 19, 13, 19, 15,  // left
    // Bridge roof
    16, 18, 19, 16, 19, 17,
  ];

  return buildSimpleModel(positions, indices, [0.6, 0.65, 0.7, 1.0], 80); // ~800m model for visibility
}

// ─── Satellite Model ───
// Solar panels + central body
function createSatellite() {
  const positions = [
    // Central body (cube-ish)
    -0.5, -0.5, -0.3, // 0
    0.5, -0.5, -0.3,  // 1
    0.5, 0.5, -0.3,   // 2
    -0.5, 0.5, -0.3,  // 3
    -0.5, -0.5, 0.3,  // 4
    0.5, -0.5, 0.3,   // 5
    0.5, 0.5, 0.3,    // 6
    -0.5, 0.5, 0.3,   // 7

    // Right solar panel
    0.8, -1.5, -0.05,  // 8
    4, -1.5, -0.05,    // 9
    4, 1.5, -0.05,     // 10
    0.8, 1.5, -0.05,   // 11
    0.8, -1.5, 0.05,   // 12
    4, -1.5, 0.05,     // 13
    4, 1.5, 0.05,      // 14
    0.8, 1.5, 0.05,    // 15

    // Left solar panel
    -0.8, -1.5, -0.05, // 16
    -4, -1.5, -0.05,   // 17
    -4, 1.5, -0.05,    // 18
    -0.8, 1.5, -0.05,  // 19
    -0.8, -1.5, 0.05,  // 20
    -4, -1.5, 0.05,    // 21
    -4, 1.5, 0.05,     // 22
    -0.8, 1.5, 0.05,   // 23

    // Antenna dish (cone approximation)
    0, 0, 0.3,         // 24: dish base center
    0.3, 0, 0.8,       // 25
    0, 0.3, 0.8,       // 26
    -0.3, 0, 0.8,      // 27
    0, -0.3, 0.8,      // 28
  ];

  const indices = [
    // Central body
    0, 1, 2,  0, 2, 3,  // bottom
    4, 6, 5,  4, 7, 6,  // top
    0, 4, 5,  0, 5, 1,  // front
    2, 6, 7,  2, 7, 3,  // back
    1, 5, 6,  1, 6, 2,  // right
    0, 3, 7,  0, 7, 4,  // left

    // Right solar panel
    8, 9, 10,  8, 10, 11,   // bottom
    12, 14, 13, 12, 15, 14, // top
    8, 12, 13,  8, 13, 9,   // front
    10, 14, 15, 10, 15, 11, // back

    // Left solar panel
    16, 17, 18, 16, 18, 19,     // bottom
    20, 22, 21, 20, 23, 22,     // top
    16, 20, 21, 16, 21, 17,     // front
    18, 22, 23, 18, 23, 19,     // back

    // Antenna
    24, 25, 26,  24, 26, 27,  24, 27, 28,  24, 28, 25,
  ];

  return buildSimpleModel(positions, indices, [0.3, 0.45, 0.7, 1.0], 5000); // 5km scale for orbital visibility
}

// ─── Generate all models ───
console.log("Generating 3D models...");

const airplane = createAirplane();
writeFileSync(join(outDir, "airplane.glb"), airplane);
console.log(`  airplane.glb: ${airplane.length} bytes`);

const ship = createShip();
writeFileSync(join(outDir, "ship.glb"), ship);
console.log(`  ship.glb: ${ship.length} bytes`);

const satellite = createSatellite();
writeFileSync(join(outDir, "satellite.glb"), satellite);
console.log(`  satellite.glb: ${satellite.length} bytes`);

console.log("Done! Models saved to public/models/");
