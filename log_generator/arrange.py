"""Placing several logs: side by side in a row, or a stacked load for a log car. No bpy.

All sizes are model millimetres. Logs lie along X.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class Placement:
    """Where one log goes: centre of its axis, turn about Z and roll about its own axis."""

    x: float
    y: float
    z: float
    yaw: float = 0.0  # radians
    roll: float = 0.0  # radians
    flip: bool = False  # butt toward -X instead of +X


def _rest_on_two(c1, c2, r):
    """Centre of a circle of radius ``r`` resting on circles c1 and c2 (y, z, radius), or None."""
    (y1, z1, r1), (y2, z2, r2) = c1, c2
    d1, d2 = r1 + r, r2 + r
    dy, dz = y2 - y1, z2 - z1
    dist = math.hypot(dy, dz)
    if dist < 1e-9 or dist > d1 + d2 or dist < abs(d1 - d2):
        return None
    a = (d1 * d1 - d2 * d2 + dist * dist) / (2 * dist)
    h = math.sqrt(max(d1 * d1 - a * a, 0.0))
    my, mz = y1 + a * dy / dist, z1 + a * dz / dist
    # Two solutions; take the upper one.
    s1 = (my - h * dz / dist, mz + h * dy / dist)
    s2 = (my + h * dz / dist, mz - h * dy / dist)
    return s1 if s1[1] >= s2[1] else s2


def _rest_on_one(c, y, r):
    """Height of a circle of radius ``r`` at ``y`` resting on circle c (y, z, radius)."""
    yc, zc, rc = c
    d = rc + r
    dy = y - yc
    if abs(dy) >= d:
        return r
    return zc + math.sqrt(d * d - dy * dy)


def stack(radii: list[float], width: float, max_rows: int, overlap: float = 0.0,
          lengths: list[float] | None = None):
    """A pyramid load: logs side by side across ``width``, each row resting in the row below.

    ``radii`` are the logs' mid-length radii. The longest logs (``lengths``)
    go to the bottom, as loaders built a load; without lengths, the biggest.
    ``overlap`` lets neighbours sink into each other by that much (for a
    load joined into one printable piece). Returns (centres, leftover)
    where ``centres`` maps each placed log's index to its (y, z), z = 0
    being the deck, and ``leftover`` lists indices that didn't fit.
    """
    if lengths is not None:
        order = sorted(range(len(radii)), key=lambda i: (-lengths[i], -radii[i]))
    else:
        order = sorted(range(len(radii)), key=lambda i: -radii[i])
    eff = [max(radii[i] - overlap / 2.0, 1e-6) for i in range(len(radii))]
    centres: dict[int, tuple[float, float]] = {}
    row: list[tuple[float, float, float]] = []
    used = 0
    # Bottom row: as many as fit across the width.
    y = 0.0
    bottom = []
    while used < len(order):
        i = order[used]
        if bottom and y + 2 * eff[i] > width + 1e-9:
            break
        bottom.append(i)
        y += 2 * eff[i]
        used += 1
    if not bottom and order:
        bottom, used = [order[0]], 1
    shift = -sum(2 * eff[i] for i in bottom) / 2.0
    y = shift
    for i in bottom:
        cy = y + eff[i]
        centres[i] = (cy, radii[i])
        row.append((cy, radii[i], eff[i]))
        y += 2 * eff[i]
    rows = 1
    while used < len(order) and rows < max_rows and len(row) >= 2:
        new_row = []
        for k in range(len(row) - 1):
            if used >= len(order):
                break
            i = order[used]
            r = eff[i]
            c1 = (row[k][0], row[k][1], row[k][2])
            c2 = (row[k + 1][0], row[k + 1][1], row[k + 1][2])
            pos = _rest_on_two(c1, c2, r)
            if pos is None:
                ym = 0.5 * (c1[0] + c2[0])
                pos = (ym, max(_rest_on_one(c1, ym, r), _rest_on_one(c2, ym, r)))
            centres[i] = pos
            new_row.append((pos[0], pos[1], r))
            used += 1
        row = new_row
        rows += 1
    leftover = order[used:]
    return centres, leftover


def capacity(width: float, radius: float, max_rows: int) -> int:
    """How many logs of one radius a stack of ``width`` and ``max_rows`` holds."""
    n = max(1, int(width // (2 * radius))) if radius > 0 else 0
    return sum(max(n - k, 0) for k in range(max(max_rows, 1)))


def float_depth(radius: float, specific_gravity: float) -> float:
    """Height of a floating log's axis above the water (negative: below).

    The submerged share of the cross-section matches the green log's
    specific gravity. Logs of 1.0 or more would sink; they are shown just
    awash, with a sliver above the water, as waterlogged "sinkers" are
    before they go down.
    """
    f = min(max(specific_gravity, 0.05), 0.97)
    target = f * math.pi * radius * radius
    lo, hi = 0.0, 2 * radius  # depth of the bottom below the water
    for _ in range(60):
        h = 0.5 * (lo + hi)
        area = radius * radius * math.acos((radius - h) / radius) - (radius - h) * math.sqrt(
            max(2 * radius * h - h * h, 0.0))
        if area < target:
            lo = h
        else:
            hi = h
    return radius - 0.5 * (lo + hi)


def row(radii: list[float], gap: float) -> list[float]:
    """Y positions for logs laid side by side, ``gap`` apart, centred on 0."""
    ys, y = [], 0.0
    for r in radii:
        ys.append(y + r)
        y += 2 * r + gap
    shift = (y - gap) / 2.0 if radii else 0.0
    return [v - shift for v in ys]


def above_water(radius: float, specific_gravity: float) -> float:
    """Share of a floating log's diameter above the water (0 to 1), from its green weight."""
    return (radius + float_depth(radius, specific_gravity)) / (2.0 * radius)
