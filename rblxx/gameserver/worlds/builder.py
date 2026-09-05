"""Declarative level builder shared by the simulation and the renderer.

A level is a flat list of parts.  The same JSON drives client rendering and
server collision, so what you see is exactly what you collide with.

Part keys are terse because whole levels are shipped to the browser:
    p     position  [x, y, z]        (centre of the part, studs)
    s     size      [sx, sy, sz]
    c     colour    "#rrggbb"
    t     texture   studs|smooth|grass|brick|metal|wood|glass|lava|water|
                    concrete|sand|snow|neon|plank|tile|rock|circuit
    k     shape     box|cylinder|sphere|cone|wedge  (default box)
    r     rotation  [rx, ry, rz] degrees (visual only; collision is the AABB)
    o     opacity   0..1 (default 1)
    g     glow      0..1 emissive strength
    n     no-collide flag (1 = pass through)
    d     damage    studs/sec damage volume (lava etc.)
    x     tag       gameplay identifier
"""
from __future__ import annotations

import math
import typing as t

TEXTURES = (
    "studs", "smooth", "grass", "brick", "metal", "wood", "glass", "lava",
    "water", "concrete", "sand", "snow", "neon", "plank", "tile", "rock",
    "circuit",
)


class Level:
    def __init__(self, *, sky: str = "classic", ambient: float = 0.55,
                 sun: tuple = (0.42, 0.86, 0.28), fog: str | None = None,
                 fog_near: float = 260, fog_far: float = 900,
                 gravity_scale: float = 1.0, void_y: float = -120.0):
        self.parts: list[dict] = []
        self.spawns: list[dict] = []
        self.pickups: list[dict] = []
        self.objectives: list[dict] = []
        self.decor: list[dict] = []
        self.navpoints: list[list[float]] = []
        self.sky = sky
        self.ambient = ambient
        self.sun = list(sun)
        self.fog = fog
        self.fog_near = fog_near
        self.fog_far = fog_far
        self.gravity_scale = gravity_scale
        self.void_y = void_y
        self.bounds = [-512, -512, 512, 512]

    # -- primitives --------------------------------------------------------
    def add(self, pos, size, color, texture="smooth", *, shape="box",
            rot=None, opacity=1.0, glow=0.0, nocollide=False, damage=0.0,
            tag=None) -> dict:
        part: dict = {
            "p": [round(float(v), 3) for v in pos],
            "s": [round(float(v), 3) for v in size],
            "c": color,
            "t": texture,
        }
        if shape != "box":
            part["k"] = shape
        if rot and any(rot):
            part["r"] = [round(float(v), 2) for v in rot]
        if opacity < 1.0:
            part["o"] = round(opacity, 3)
        if glow:
            part["g"] = round(glow, 3)
        if nocollide or shape in ("sphere", "cone") and nocollide:
            part["n"] = 1
        if damage:
            part["d"] = damage
        if tag:
            part["x"] = tag
        self.parts.append(part)
        return part

    # convenience wrappers -------------------------------------------------
    def box(self, x, y, z, sx, sy, sz, color, texture="smooth", **kw):
        return self.add((x, y, z), (sx, sy, sz), color, texture, **kw)

    def baseplate(self, size=512, color="#5aa02c", texture="grass", y=0.0,
                  thickness=8.0):
        return self.box(0, y - thickness / 2, 0, size, thickness, size,
                        color, texture)

    def wall(self, x1, z1, x2, z2, height, thickness, color,
             texture="brick", y=0.0, **kw):
        cx, cz = (x1 + x2) / 2, (z1 + z2) / 2
        dx, dz = abs(x2 - x1), abs(z2 - z1)
        if dx >= dz:
            return self.box(cx, y + height / 2, cz, dx or thickness, height,
                            thickness, color, texture, **kw)
        return self.box(cx, y + height / 2, cz, thickness, height,
                        dz or thickness, color, texture, **kw)

    def room(self, cx, cz, w, d, height, color, texture="concrete", y=0.0,
             thickness=2.0, walls="nsew", door=None):
        """Four walls (optionally with a gap for a door on one side)."""
        hw, hd = w / 2, d / 2
        if "n" in walls:
            self._wall_with_door(cx, cz - hd, w, height, thickness, color,
                                 texture, y, axis="x",
                                 door=door if door == "n" else None)
        if "s" in walls:
            self._wall_with_door(cx, cz + hd, w, height, thickness, color,
                                 texture, y, axis="x",
                                 door=door if door == "s" else None)
        if "w" in walls:
            self._wall_with_door(cx - hw, cz, d, height, thickness, color,
                                 texture, y, axis="z",
                                 door=door if door == "w" else None)
        if "e" in walls:
            self._wall_with_door(cx + hw, cz, d, height, thickness, color,
                                 texture, y, axis="z",
                                 door=door if door == "e" else None)

    def _wall_with_door(self, cx, cz, length, height, thickness, color,
                        texture, y, axis, door, door_w=8.0, door_h=9.0):
        if door is None:
            if axis == "x":
                self.box(cx, y + height / 2, cz, length, height, thickness,
                         color, texture)
            else:
                self.box(cx, y + height / 2, cz, thickness, height, length,
                         color, texture)
            return
        side = (length - door_w) / 2
        if axis == "x":
            self.box(cx - (door_w + side) / 2, y + height / 2, cz, side,
                     height, thickness, color, texture)
            self.box(cx + (door_w + side) / 2, y + height / 2, cz, side,
                     height, thickness, color, texture)
            if height > door_h:
                self.box(cx, y + door_h + (height - door_h) / 2, cz, door_w,
                         height - door_h, thickness, color, texture)
        else:
            self.box(cx, y + height / 2, cz - (door_w + side) / 2, thickness,
                     height, side, color, texture)
            self.box(cx, y + height / 2, cz + (door_w + side) / 2, thickness,
                     height, side, color, texture)
            if height > door_h:
                self.box(cx, y + door_h + (height - door_h) / 2, cz, thickness,
                         height - door_h, door_w, color, texture)

    def stairs(self, x, y, z, *, steps=8, rise=1.6, run=3.0, width=10.0,
               direction="+z", color="#9a9a9a", texture="concrete"):
        """A staircase built from boxes — climbs cleanly with AABB physics."""
        dx, dz = {"+z": (0, 1), "-z": (0, -1), "+x": (1, 0),
                  "-x": (-1, 0)}[direction]
        for i in range(steps):
            h = rise * (i + 1)
            px = x + dx * (run * (i + 0.5))
            pz = z + dz * (run * (i + 0.5))
            if dx:
                self.box(px, y + h / 2, pz, run, h, width, color, texture)
            else:
                self.box(px, y + h / 2, pz, width, h, run, color, texture)
        return (x + dx * run * steps, y + rise * steps, z + dz * run * steps)

    def ramp(self, x, y, z, *, length=24.0, height=12.0, width=10.0,
             direction="+z", color="#9a9a9c", texture="concrete", segs=10,
             thickness=3.0):
        """A slope made from short overlapping steps.  `height` may be
        negative for a descent; each step is a solid block down to the
        lowest point so nothing is left floating."""
        dx, dz = {"+z": (0, 1), "-z": (0, -1), "+x": (1, 0),
                  "-x": (-1, 0)}[direction]
        seg = length / segs
        base = min(y, y + height) - thickness
        for i in range(segs):
            top = y + height * (i + 1) / segs
            hgt = max(0.4, top - base)
            px = x + dx * (seg * (i + 0.5))
            pz = z + dz * (seg * (i + 0.5))
            cy = base + hgt / 2
            if dx:
                self.box(px, cy, pz, seg + 0.1, hgt, width, color, texture)
            else:
                self.box(px, cy, pz, width, hgt, seg + 0.1, color, texture)
        return (x + dx * length, y + height, z + dz * length)

    def tree(self, x, z, y=0.0, *, scale=1.0, trunk="#6b4a2c",
             leaves="#2f7d32", style="round"):
        h = 9.0 * scale
        self.box(x, y + h / 2, z, 1.6 * scale, h, 1.6 * scale, trunk, "wood")
        if style == "round":
            self.add((x, y + h + 3.2 * scale, z),
                     (9.5 * scale, 8.0 * scale, 9.5 * scale), leaves,
                     "smooth", shape="sphere")
        elif style == "pine":
            for i, f in enumerate((1.0, 0.72, 0.44)):
                self.add((x, y + h + 1.5 * scale + i * 3.4 * scale, z),
                         (9.0 * f * scale, 5.0 * scale, 9.0 * f * scale),
                         leaves, "smooth", shape="cone")
        else:  # blocky
            self.box(x, y + h + 2.6 * scale, z, 8.0 * scale, 6.0 * scale,
                     8.0 * scale, leaves, "smooth")

    def light_post(self, x, z, y=0.0, height=14.0, color="#ffe9a8"):
        self.box(x, y + height / 2, z, 0.8, height, 0.8, "#454b52", "metal")
        self.add((x, y + height + 0.6, z), (2.2, 1.2, 2.2), color, "neon",
                 shape="sphere", glow=1.0, nocollide=True)

    # -- gameplay ----------------------------------------------------------
    def spawn(self, x, y, z, team="neutral", yaw=0.0):
        self.spawns.append({"p": [x, y, z], "team": team, "yaw": yaw})

    def pickup(self, kind, x, y, z, *, respawn=20.0, tag=None):
        self.pickups.append({"kind": kind, "p": [x, y, z],
                             "respawn": respawn, "id": tag or
                             f"{kind}_{len(self.pickups)}"})

    def objective(self, kind, x, y, z, **extra):
        obj = {"kind": kind, "p": [x, y, z]}
        obj.update(extra)
        self.objectives.append(obj)
        return obj

    def nav(self, x, y, z):
        """A navigation node.  Edges are derived by line-of-sight at load."""
        self.navpoints.append([float(x), float(y), float(z)])

    def nav_grid(self, x0, z0, x1, z1, y, step=14.0):
        nx = max(1, int((x1 - x0) / step))
        nz = max(1, int((z1 - z0) / step))
        for i in range(nx + 1):
            for j in range(nz + 1):
                self.nav(x0 + i * (x1 - x0) / nx, y, z0 + j * (z1 - z0) / nz)

    def sign(self, x, y, z, text, *, color="#f2c53d", face="+z", size=6.0):
        self.decor.append({"kind": "sign", "p": [x, y, z], "text": text,
                           "color": color, "face": face, "size": size})

    # -- output ------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "parts": self.parts,
            "spawns": self.spawns,
            "pickups": self.pickups,
            "objectives": self.objectives,
            "decor": self.decor,
            "nav": self.navpoints,
            "sky": self.sky,
            "ambient": self.ambient,
            "sun": self.sun,
            "fog": self.fog,
            "fogNear": self.fog_near,
            "fogFar": self.fog_far,
            "gravityScale": self.gravity_scale,
            "voidY": self.void_y,
            "bounds": self.bounds,
        }

    # -- collision extraction ---------------------------------------------
    def colliders(self) -> list[tuple]:
        """(minx,miny,minz,maxx,maxy,maxz, damage, tag) for solid parts."""
        out = []
        for part in self.parts:
            if part.get("n"):
                if not part.get("d"):
                    continue
            px, py, pz = part["p"]
            sx, sy, sz = part["s"]
            if part.get("k") in ("sphere", "cone"):
                sx, sy, sz = sx * 0.82, sy * 0.82, sz * 0.82
            out.append((px - sx / 2, py - sy / 2, pz - sz / 2,
                        px + sx / 2, py + sy / 2, pz + sz / 2,
                        float(part.get("d", 0.0)),
                        part.get("x"), bool(part.get("n"))))
        return out


def lerp_color(a: str, b: str, t_: float) -> str:
    ar, ag, ab = int(a[1:3], 16), int(a[3:5], 16), int(a[5:7], 16)
    br, bg, bb = int(b[1:3], 16), int(b[3:5], 16), int(b[5:7], 16)
    return "#{:02x}{:02x}{:02x}".format(
        int(ar + (br - ar) * t_), int(ag + (bg - ag) * t_),
        int(ab + (bb - ab) * t_))


def ring_points(cx, cz, radius, count, phase=0.0):
    return [(cx + radius * math.cos(phase + i * 2 * math.pi / count),
             cz + radius * math.sin(phase + i * 2 * math.pi / count))
            for i in range(count)]
