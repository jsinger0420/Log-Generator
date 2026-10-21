"""Seeded 3D noise in numpy: gradient (Perlin-style) noise, fBm and Worley cells.

No bpy, so it can be tested. Every function takes an (N, 3) array of
points and returns values for each point. Bark is sampled on a cylinder in
3D (see bark.py), so the patterns wrap round the log without a seam.
"""

from __future__ import annotations

import numpy as np

_MASK = np.uint64(0xFFFFFFFF)

# The 12 edge directions of a cube: Perlin's gradient set.
_GRAD = np.array([
    [1, 1, 0], [-1, 1, 0], [1, -1, 0], [-1, -1, 0],
    [1, 0, 1], [-1, 0, 1], [1, 0, -1], [-1, 0, -1],
    [0, 1, 1], [0, -1, 1], [0, 1, -1], [0, -1, -1],
], dtype=np.float64)


def hash3(ix: np.ndarray, iy: np.ndarray, iz: np.ndarray, seed: int) -> np.ndarray:
    """A well-mixed 32-bit hash of integer lattice coordinates and a seed (uint64 array)."""
    with np.errstate(over="ignore"):
        h = (ix.astype(np.int64).astype(np.uint64) * np.uint64(0x9E3779B1)
             ^ iy.astype(np.int64).astype(np.uint64) * np.uint64(0x85EBCA77)
             ^ iz.astype(np.int64).astype(np.uint64) * np.uint64(0xC2B2AE3D)
             ^ np.uint64((int(seed) * 0x27D4EB2F) & 0xFFFFFFFF))
        h &= _MASK
        h ^= h >> np.uint64(16)
        h = (h * np.uint64(0x7FEB352D)) & _MASK
        h ^= h >> np.uint64(15)
        h = (h * np.uint64(0x846CA68B)) & _MASK
        h ^= h >> np.uint64(16)
    return h


def unit(h: np.ndarray) -> np.ndarray:
    """A hash as a float in [0, 1)."""
    return (h & _MASK).astype(np.float64) / 4294967296.0


def _fade(t: np.ndarray) -> np.ndarray:
    """Perlin's quintic fade curve 6t^5 - 15t^4 + 10t^3."""
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)


def gradient(p: np.ndarray, seed: int = 0) -> np.ndarray:
    """Gradient noise at points ``p`` (N, 3); values roughly in [-1, 1], 0 on lattice points."""
    p = np.asarray(p, dtype=np.float64)
    i = np.floor(p)
    f = p - i
    i = i.astype(np.int64)
    u = _fade(f)
    out = np.zeros(len(p))
    # Accumulate the 8 corners with trilinear weights.
    for dx in (0, 1):
        wx = u[:, 0] if dx else 1.0 - u[:, 0]
        for dy in (0, 1):
            wy = u[:, 1] if dy else 1.0 - u[:, 1]
            for dz in (0, 1):
                wz = u[:, 2] if dz else 1.0 - u[:, 2]
                h = hash3(i[:, 0] + dx, i[:, 1] + dy, i[:, 2] + dz, seed)
                g = _GRAD[(h % np.uint64(12)).astype(np.int64)]
                d = f - np.array([dx, dy, dz], dtype=np.float64)
                out += wx * wy * wz * np.einsum("ij,ij->i", g, d)
    return out


def fbm(p: np.ndarray, octaves: int = 4, seed: int = 0, lacunarity: float = 2.0,
        gain: float = 0.5) -> np.ndarray:
    """Fractal sum of gradient noise, normalised to roughly [-1, 1]."""
    p = np.asarray(p, dtype=np.float64)
    total = np.zeros(len(p))
    amp, freq, norm = 1.0, 1.0, 0.0
    for k in range(max(1, octaves)):
        total += amp * gradient(p * freq, seed + 1013 * k)
        norm += amp
        amp *= gain
        freq *= lacunarity
    return total / norm


def worley(p: np.ndarray, seed: int = 0, jitter: float = 0.9):
    """Worley (cellular) noise: one random feature point per unit cell.

    Returns (F1, F2, cell) where F1 and F2 are the distances to the
    nearest and second-nearest feature points and ``cell`` is a random
    value in [0, 1) belonging to the nearest point's cell, so each cell
    (bark plate, scale or strip) can be given its own height or colour.
    """
    p = np.asarray(p, dtype=np.float64)
    base = np.floor(p).astype(np.int64)
    n = len(p)
    f1 = np.full(n, np.inf)
    f2 = np.full(n, np.inf)
    cell = np.zeros(n)
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                cx, cy, cz = base[:, 0] + dx, base[:, 1] + dy, base[:, 2] + dz
                h = hash3(cx, cy, cz, seed)
                fx = cx + 0.5 + jitter * (unit(h) - 0.5)
                fy = cy + 0.5 + jitter * (unit(hash3(cx, cy, cz, seed + 17)) - 0.5)
                fz = cz + 0.5 + jitter * (unit(hash3(cx, cy, cz, seed + 31)) - 0.5)
                d = np.sqrt((p[:, 0] - fx) ** 2 + (p[:, 1] - fy) ** 2 + (p[:, 2] - fz) ** 2)
                closer = d < f1
                f2 = np.where(closer, f1, np.minimum(f2, d))
                cell = np.where(closer, unit(hash3(cx, cy, cz, seed + 53)), cell)
                f1 = np.where(closer, d, f1)
    return f1, f2, cell


def smoothstep(e0: float, e1: float, x: np.ndarray) -> np.ndarray:
    """0 below ``e0``, 1 above ``e1``, a smooth S-curve between."""
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)
