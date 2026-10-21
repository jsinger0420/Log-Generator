"""Bark relief and colour patterns, one function per bark style. No bpy.

Bark is sampled on a cylinder in full-size millimetres: a point at angle
``theta`` round the log and ``x`` along it becomes

    (R cos theta / s, R sin theta / s, x / (s * stretch))

where R is the log's nominal radius, s the size of one bark feature and
``stretch`` how much longer features are along the log than around it.
Sampling in 3D means the pattern wraps round the log without a seam, and
working in full-size millimetres means a species' bark looks the same at
every scale.

The mesh can only show detail a few times coarser than its point
spacing; finer noise would alias into random ledges. So each pattern is
told the mesh resolution (``res``: point spacing in bark-space units) and
leaves out noise octaves and fine details the mesh can't show, and sharp
edges are softened to at least a couple of points wide. If even one
feature is too small for the mesh (very small scales, coarse detail), the
feature size is enlarged until it can be shown.

Each style returns ``height`` in [0, 1] (1 is the outer bark surface, 0 the
bottom of the deepest furrow) and ``tone`` in [0, 1], a slow variation used
to vary the colour.
"""

from __future__ import annotations

import math

import numpy as np

from . import noise
from .noise import smoothstep

# Finest noise period drawn, in mesh points: below about 3 points a period aliases.
MIN_PERIOD_POINTS = 3.0
# Largest mesh spacing, in feature sizes, before the features are enlarged.
MAX_RES = 0.15


def _points(theta, x, radius, scale, stretch):
    """Bark-space sample points (N, 3) for angles, positions along the log and a radius."""
    r = radius / scale
    return np.column_stack((r * np.cos(theta), r * np.sin(theta), x / (scale * stretch)))


def octaves(res: float, base: float = 1.0, most: int = 4) -> int:
    """How many fBm octaves starting at frequency ``base`` the mesh can show (at least 1)."""
    finest = 1.0 / (MIN_PERIOD_POINTS * max(res, 1e-6))  # highest frequency allowed
    if finest <= base:
        return 1
    return int(max(1, min(most, 1 + math.floor(math.log2(finest / base)))))


def shown(res: float, freq: float) -> float:
    """0 to 1: how much of a detail at frequency ``freq`` to keep at this resolution."""
    period_points = 1.0 / (freq * max(res, 1e-6))
    return float(np.clip((period_points - MIN_PERIOD_POINTS) / MIN_PERIOD_POINTS, 0.0, 1.0))


def _edge(width: float, res: float) -> float:
    """An edge width (bark-space units) no sharper than about two mesh points."""
    return max(width, 2.0 * res)


def _furrowed(p, seed, res):
    """Ridges along the log split by narrow, deep furrows that wander and merge."""
    warp = noise.fbm(p * 0.45, 2, seed + 7)[:, None] * np.array([0.7, 0.7, 0.25])
    n = noise.fbm(p + warp, octaves(res, 1.0, 3), seed) * 2.2
    h = smoothstep(0.0, _edge(0.42, res * 2.2), np.abs(n))
    # Cross-cracks break the ridges into blocks now and then.
    k = shown(res, 3.5)
    if k > 0:
        q = p * np.array([1.4, 1.4, 3.5])
        crack = smoothstep(0.82, 0.95, np.abs(noise.gradient(q, seed + 3)) * 1.8)
        h = h * (1.0 - 0.5 * k * crack)
    k = shown(res, 5.0)
    if k > 0:
        h += noise.fbm(p * 5.0, 2, seed + 11) * 0.06 * k
    return h


def _plated(p, seed, res):
    """Flat plates, each at its own height, separated by deep dark crevices."""
    warp = noise.fbm(p * 0.6, 2, seed + 5)[:, None] * 0.35
    f1, f2, cell = noise.worley(p + warp, seed)
    h = smoothstep(0.0, _edge(0.16, res), f2 - f1) * (0.72 + 0.28 * cell)
    k = shown(res, 6.0)
    if k > 0:
        h += noise.fbm(p * 6.0, 2, seed + 9) * 0.05 * h * k  # flaky plate surface
    return h, cell


def _fibrous(p, seed, res):
    """Long, soft, stringy strips with fine fibres between them."""
    warp = noise.fbm(p * 0.5, 2, seed + 7)[:, None] * np.array([0.5, 0.5, 0.2])
    n = noise.fbm(p + warp, octaves(res, 1.0, 3), seed) * 2.0
    coarse = smoothstep(-0.05, _edge(0.5, res * 2.0), np.abs(n))
    k = shown(res, 3.0)
    if k <= 0:
        return coarse
    fine = smoothstep(0.0, 0.35, np.abs(noise.fbm(p * np.array([3.0, 3.0, 1.2]), 2, seed + 13)) * 2.0)
    return (1.0 - 0.3 * k) * coarse + 0.3 * k * fine


def _scaly(p, seed, res):
    """Small flaky scales, each lifted a little at its lower edge."""
    f1, f2, cell = noise.worley(p, seed)
    h = smoothstep(0.0, _edge(0.12, res), f2 - f1) * (0.6 + 0.4 * cell)
    h += 0.12 * smoothstep(0.1, 0.6, f1) * h
    return h, cell


def _interlaced(p, seed, res):
    """Narrow ridges joining into a diamond network, with furrows in the diamonds."""
    warp = noise.fbm(p * 0.5, 2, seed + 5)[:, None] * 0.25
    f1, f2, cell = noise.worley(p + warp, seed)
    ridge = 1.0 - smoothstep(0.0, _edge(0.2, res), f2 - f1)
    h = 0.2 + 0.8 * ridge
    k = shown(res, 4.0)
    if k > 0:
        h += noise.fbm(p * 4.0, 2, seed + 9) * 0.05 * k
    return h, cell


def _shaggy(p, seed, res):
    """Long strips of bark, each lifting away from the trunk by its own amount."""
    f1, f2, cell = noise.worley(p, seed, jitter=0.95)
    strip = smoothstep(0.0, _edge(0.09, res), f2 - f1)
    # Strips lift more toward one end, as the curled ends of shagbark do.
    lift = 0.45 + 0.55 * cell * (0.6 + 0.4 * smoothstep(-0.5, 0.5, noise.gradient(p * 0.7, seed + 3)))
    return 0.25 + 0.75 * strip * lift, cell


def _smooth(p, seed, res):
    """Thin, nearly smooth bark with soft undulation."""
    return 0.85 + 0.15 * noise.fbm(p * 0.7, octaves(res, 0.7, 3), seed)


def _birch(p, seed, res):
    """Smooth bark with short dark horizontal lenticels."""
    base = 0.9 + 0.1 * noise.fbm(p * 0.5, 2, seed)
    lent = smoothstep(0.30, 0.30 + _edge(0.12, res), noise.fbm(p, octaves(res, 1.0, 3), seed + 21))
    return base - 0.7 * lent


def surface(style: str, theta: np.ndarray, x: np.ndarray, radius: float, scale: float,
            stretch: float, seed: int, spacing: tuple[float, float] = (0.0, 0.0)):
    """Bark height and colour tone at each point.

    ``theta`` in radians round the log, ``x`` full-size mm along it,
    ``radius`` the log's nominal full-size radius in mm, ``scale`` the bark
    feature size in full-size mm, ``spacing`` the mesh's (round, along)
    point spacing in full-size mm (0 = draw every detail). Returns
    (height, tone), each in [0, 1].
    """
    scale = max(scale, 1e-3)
    stretch = max(stretch, 0.05)
    res = max(spacing[0] / scale, spacing[1] / (scale * stretch))
    if res > MAX_RES:  # the mesh can't show features this small: enlarge them
        scale *= res / MAX_RES
        res = MAX_RES
    p = _points(theta, x, radius, scale, stretch)
    cell = None
    if style == "PLATED":
        h, cell = _plated(p, seed, res)
    elif style == "SCALY":
        h, cell = _scaly(p, seed, res)
    elif style == "INTERLACED":
        h, cell = _interlaced(p, seed, res)
    elif style == "SHAGGY":
        h, cell = _shaggy(p, seed, res)
    elif style == "FIBROUS":
        h = _fibrous(p, seed, res)
    elif style == "SMOOTH":
        h = _smooth(p, seed, res)
    elif style == "BIRCH":
        h = _birch(p, seed, res)
    else:
        h = _furrowed(p, seed, res)
    tone = 0.5 + 0.5 * noise.fbm(p * np.array([0.25, 0.25, 0.6]), 2, seed + 101)
    if cell is not None:
        tone = 0.6 * tone + 0.4 * cell
    return np.clip(h, 0.0, 1.0), np.clip(tone, 0.0, 1.0)


def colour(height: np.ndarray, tone: np.ndarray, ridge, furrow) -> np.ndarray:
    """sRGB bark colour (N, 3): furrow colour deep down, ridge colour on top, varied by tone."""
    ridge = np.asarray(ridge, dtype=np.float64)
    furrow = np.asarray(furrow, dtype=np.float64)
    t = smoothstep(0.12, 0.85, height)[:, None]
    c = furrow * (1.0 - t) + ridge * t
    c *= (0.82 + 0.36 * tone)[:, None]
    return np.clip(c, 0.0, 1.0)
