// Procedural primitive meshes. Everything is unit-sized around the origin so
// an instance matrix's scale gives the part its real dimensions in studs.

function mesh(positions, normals, indices) {
  return {
    positions: new Float32Array(positions),
    normals: new Float32Array(normals),
    indices: indices.length > 65535
      ? new Uint32Array(indices) : new Uint16Array(indices),
    count: indices.length,
  };
}

export function boxMesh() {
  const p = [], n = [], idx = [];
  const faces = [
    [[0, 0, 1], [[-.5, -.5, .5], [.5, -.5, .5], [.5, .5, .5], [-.5, .5, .5]]],
    [[0, 0, -1], [[.5, -.5, -.5], [-.5, -.5, -.5], [-.5, .5, -.5], [.5, .5, -.5]]],
    [[1, 0, 0], [[.5, -.5, .5], [.5, -.5, -.5], [.5, .5, -.5], [.5, .5, .5]]],
    [[-1, 0, 0], [[-.5, -.5, -.5], [-.5, -.5, .5], [-.5, .5, .5], [-.5, .5, -.5]]],
    [[0, 1, 0], [[-.5, .5, .5], [.5, .5, .5], [.5, .5, -.5], [-.5, .5, -.5]]],
    [[0, -1, 0], [[-.5, -.5, -.5], [.5, -.5, -.5], [.5, -.5, .5], [-.5, -.5, .5]]],
  ];
  for (const [normal, verts] of faces) {
    const base = p.length / 3;
    for (const v of verts) { p.push(...v); n.push(...normal); }
    idx.push(base, base + 1, base + 2, base, base + 2, base + 3);
  }
  return mesh(p, n, idx);
}

export function cylinderMesh(segments = 18) {
  const p = [], n = [], idx = [];
  // side
  for (let i = 0; i <= segments; i++) {
    const a = (i / segments) * Math.PI * 2;
    const cx = Math.cos(a) * 0.5, cz = Math.sin(a) * 0.5;
    const nx = Math.cos(a), nz = Math.sin(a);
    p.push(cx, -0.5, cz, cx, 0.5, cz);
    n.push(nx, 0, nz, nx, 0, nz);
  }
  for (let i = 0; i < segments; i++) {
    const b = i * 2;
    idx.push(b, b + 2, b + 3, b, b + 3, b + 1);
  }
  // caps
  for (const [y, ny] of [[0.5, 1], [-0.5, -1]]) {
    const centre = p.length / 3;
    p.push(0, y, 0); n.push(0, ny, 0);
    for (let i = 0; i <= segments; i++) {
      const a = (i / segments) * Math.PI * 2;
      p.push(Math.cos(a) * 0.5, y, Math.sin(a) * 0.5);
      n.push(0, ny, 0);
    }
    for (let i = 0; i < segments; i++) {
      if (ny > 0) idx.push(centre, centre + 1 + i, centre + 2 + i);
      else idx.push(centre, centre + 2 + i, centre + 1 + i);
    }
  }
  return mesh(p, n, idx);
}

export function sphereMesh(rings = 12, segments = 18) {
  const p = [], n = [], idx = [];
  for (let y = 0; y <= rings; y++) {
    const phi = (y / rings) * Math.PI;
    for (let x = 0; x <= segments; x++) {
      const theta = (x / segments) * Math.PI * 2;
      const nx = Math.sin(phi) * Math.cos(theta);
      const ny = Math.cos(phi);
      const nz = Math.sin(phi) * Math.sin(theta);
      p.push(nx * 0.5, ny * 0.5, nz * 0.5);
      n.push(nx, ny, nz);
    }
  }
  const rowLen = segments + 1;
  for (let y = 0; y < rings; y++) {
    for (let x = 0; x < segments; x++) {
      const a = y * rowLen + x, b = a + rowLen;
      idx.push(a, b, a + 1, a + 1, b, b + 1);
    }
  }
  return mesh(p, n, idx);
}

export function coneMesh(segments = 18) {
  const p = [], n = [], idx = [];
  for (let i = 0; i < segments; i++) {
    const a0 = (i / segments) * Math.PI * 2;
    const a1 = ((i + 1) / segments) * Math.PI * 2;
    const am = (a0 + a1) / 2;
    const ny = 0.45;
    const nx = Math.cos(am), nz = Math.sin(am);
    const base = p.length / 3;
    p.push(Math.cos(a0) * 0.5, -0.5, Math.sin(a0) * 0.5);
    p.push(Math.cos(a1) * 0.5, -0.5, Math.sin(a1) * 0.5);
    p.push(0, 0.5, 0);
    for (let k = 0; k < 3; k++) n.push(nx, ny, nz);
    idx.push(base, base + 1, base + 2);
  }
  const centre = p.length / 3;
  p.push(0, -0.5, 0); n.push(0, -1, 0);
  for (let i = 0; i <= segments; i++) {
    const a = (i / segments) * Math.PI * 2;
    p.push(Math.cos(a) * 0.5, -0.5, Math.sin(a) * 0.5);
    n.push(0, -1, 0);
  }
  for (let i = 0; i < segments; i++) idx.push(centre, centre + 2 + i, centre + 1 + i);
  return mesh(p, n, idx);
}

export function wedgeMesh() {
  // A right-triangular prism: full height at -z, zero height at +z.
  const p = [], n = [], idx = [];
  const push = (verts, normal) => {
    const base = p.length / 3;
    for (const v of verts) { p.push(...v); n.push(...normal); }
    if (verts.length === 3) idx.push(base, base + 1, base + 2);
    else idx.push(base, base + 1, base + 2, base, base + 2, base + 3);
  };
  const sl = Math.SQRT1_2;
  push([[-.5, -.5, .5], [.5, -.5, .5], [.5, -.5, -.5], [-.5, -.5, -.5]], [0, -1, 0]);
  push([[-.5, -.5, -.5], [.5, -.5, -.5], [.5, .5, -.5], [-.5, .5, -.5]], [0, 0, -1]);
  push([[.5, -.5, .5], [-.5, -.5, .5], [-.5, .5, -.5], [.5, .5, -.5]], [0, sl, sl]);
  push([[.5, -.5, -.5], [.5, -.5, .5], [.5, .5, -.5]], [1, 0, 0]);
  push([[-.5, -.5, .5], [-.5, -.5, -.5], [-.5, .5, -.5]], [-1, 0, 0]);
  return mesh(p, n, idx);
}

export function torusMesh(rings = 16, sides = 10, tube = 0.16) {
  const p = [], n = [], idx = [];
  for (let i = 0; i <= rings; i++) {
    const u = (i / rings) * Math.PI * 2;
    for (let j = 0; j <= sides; j++) {
      const v = (j / sides) * Math.PI * 2;
      const cx = Math.cos(u), cz = Math.sin(u);
      const r = 0.5 - tube + Math.cos(v) * tube;
      p.push(cx * r, Math.sin(v) * tube, cz * r);
      n.push(cx * Math.cos(v), Math.sin(v), cz * Math.cos(v));
    }
  }
  const rowLen = sides + 1;
  for (let i = 0; i < rings; i++) {
    for (let j = 0; j < sides; j++) {
      const a = i * rowLen + j, b = a + rowLen;
      idx.push(a, b, a + 1, a + 1, b, b + 1);
    }
  }
  return mesh(p, n, idx);
}

export function quadMesh() {
  return mesh(
    [-.5, -.5, 0, .5, -.5, 0, .5, .5, 0, -.5, .5, 0],
    [0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1],
    [0, 1, 2, 0, 2, 3]);
}

export const SHAPES = {
  box: boxMesh,
  cylinder: cylinderMesh,
  sphere: sphereMesh,
  cone: coneMesh,
  wedge: wedgeMesh,
  torus: torusMesh,
  quad: quadMesh,
};

const cache = {};
export function getMesh(name) {
  if (!cache[name]) {
    const fn = SHAPES[name] || SHAPES.box;
    cache[name] = fn();
  }
  return cache[name];
}
