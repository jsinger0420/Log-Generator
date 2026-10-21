"""One log as numpy arrays: shape, bark, cut limbs and sawn ends. No bpy.

The log lies along +X from x = 0 (the butt, or large end) to x = length,
its axis on the X axis. Sizes in a ``LogSpec`` are model millimetres
unless the name ends in ``_real`` (full-size millimetres).

How the surface is made:

1. A grid of rings along the log, each with the same number of points round
   it. The outside of the bark tapers from the butt to the top diameter,
   swells into a flared, lobed root collar at a flared butt, and is a
   little oval and lumpy.
2. Bark relief (bark.py) cuts furrows inward from that outer surface. The
   furrows never go deeper than the bark is thick.
3. Patches of missing bark (handling damage) drop to the wood.
4. Cut limbs: each is a raised collar of bark round a flat, sawn-off stub
   face that shows end grain.
5. A gentle bow along the length.
6. Each end is closed by a sawn face (a disc of rings out to the bark,
   tilted a little as real cuts are). The outer band of the face is bark,
   the rest end grain round a slightly off-centre pith.

The mesh is closed (watertight), so it exports for 3D printing as it is.

Faces carry a material index (``BARK`` or ``END_GRAIN``); vertices carry a
linear RGBA colour (the bark colour, used by the bark material) and two UV
maps for the end grain material: ``uv_norm`` is the offset from the pith
(or a limb's centre) as a fraction of the wood radius, ``uv_rings`` the
same offset in growth rings.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from . import bark, noise
from .noise import smoothstep

BARK, END_GRAIN = 0, 1
MAX_RINGS = 22  # most growth rings drawn from pith to bark


@dataclass
class LogSpec:
    """Everything needed to build one log."""

    scale_n: float = 87.1
    length: float = 100.0  # model mm
    d_butt: float = 8.0  # model mm, outside the bark, before any flare
    d_top: float = 7.0  # model mm, outside the bark
    flare: float = 0.0  # extra diameter at the butt, as a fraction (0 = no flare)
    flare_lobes: int = 5
    ovality: float = 0.04  # fraction
    lumpiness: float = 0.02  # fraction
    sweep: float = 0.006  # bow, as a fraction of the length
    style: str = "FURROWED"
    bark_scale_real: float = 50.0
    bark_stretch: float = 3.0
    bark_depth_real: float = 20.0
    bark_thickness_real: float = 30.0
    ridge: tuple = (0.4, 0.3, 0.25)
    furrow: tuple = (0.1, 0.08, 0.06)
    inner_bark: tuple = (0.55, 0.3, 0.2)
    sapwood: tuple = (0.9, 0.8, 0.6)
    ring_mm_real: float = 3.0
    knots_per_m: float = 1.0
    knot_real: float = 45.0  # limb diameter, full size mm
    stub_real: float = 25.0  # longest limb stub left, full size mm
    damage: float = 0.05  # fraction of the bark knocked off
    end_tilt_deg: float = 3.0  # largest tilt of a sawn end from square
    end_rough: bool = True
    around_spacing: float = 0.15  # model mm between points round the log
    along_spacing: float = 0.3  # model mm between rings
    max_triangles: int = 400_000
    seed: int = 1

    def real(self, model_mm: float) -> float:
        """A model size in full-size mm."""
        return model_mm * self.scale_n

    def model(self, real_mm: float) -> float:
        """A full-size size in model mm."""
        return real_mm / self.scale_n


@dataclass
class LogMesh:
    """A built log: arrays ready for Blender, and facts about it."""

    vertices: np.ndarray  # (N, 3) float
    triangles: np.ndarray  # (M, 3) int
    material: np.ndarray  # (M,) int, BARK or END_GRAIN
    colours: np.ndarray  # (N, 4) linear RGBA
    uv_norm: np.ndarray  # (N, 2)
    uv_rings: np.ndarray  # (N, 2)
    info: dict = field(default_factory=dict)


def srgb_to_linear(c: np.ndarray) -> np.ndarray:
    """sRGB colour values to linear, as Blender stores colours."""
    c = np.asarray(c, dtype=np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def flare_length(spec: LogSpec) -> float:
    """How far up the log a flared butt reaches (model mm): about one and a half diameters."""
    return 1.5 * spec.d_butt


def resolution(spec: LogSpec) -> tuple[int, int, int]:
    """(points round, rings along, rings on each end face), within the triangle budget."""
    r_max = 0.5 * spec.d_butt * (1.0 + spec.flare)
    around = max(spec.around_spacing, 1e-3)
    along = max(spec.along_spacing, 1e-3)
    n_ar = int(np.clip(math.ceil(2 * math.pi * r_max / around), 24, 1440))
    n_al = int(np.clip(math.ceil(spec.length / along), 8, 8000))
    if spec.flare > 0:  # enough rings to shape the flare
        n_al = max(n_al, int(math.ceil(spec.length / (flare_length(spec) / 12))))
    m = int(np.clip(round(0.5 * spec.d_butt / (1.5 * around)), 2, 40))

    def tris(a, b, c):
        return 2 * a * b + 2 * a * (2 * c + 2)

    total = tris(n_ar, n_al, m)
    if total > spec.max_triangles:
        f = math.sqrt(spec.max_triangles / total)
        n_ar = max(24, int(n_ar * f))
        n_al = max(8, int(n_al * f))
        m = max(2, int(m * f))
    return n_ar, n_al, m


def _wrap(a: np.ndarray) -> np.ndarray:
    """Angles wrapped into [-pi, pi)."""
    return (a + np.pi) % (2 * np.pi) - np.pi


def _lobes(theta: np.ndarray, k: int, phase: float, rng) -> np.ndarray:
    """Root buttress lobes round a flared butt: peaks of 1, valleys near 0, a little uneven."""
    amp = 1.0 + 0.35 * np.sin(theta * 1.0 + rng.uniform(0, 2 * np.pi))  # uneven buttresses
    c = 0.5 + 0.5 * np.cos(k * (theta - phase))
    return (c ** 1.5) * amp


@dataclass
class _Knot:
    """One cut limb: where it is and how big (model mm and radians)."""

    x: float
    theta: float
    radius: float  # stub face radius round the log
    stub: float  # how far the stub stands proud of the collar
    elong: float  # the face is longer along the log than across


def _knots(spec: LogSpec, rng) -> list[_Knot]:
    """Random cut limbs, fewer on a flared butt, none close to the ends."""
    length_m = spec.real(spec.length) / 1000.0
    count = rng.poisson(max(0.0, spec.knots_per_m) * length_m)
    out = []
    for _ in range(count):
        dia = spec.model(spec.knot_real) * rng.uniform(0.6, 1.4)
        r = 0.5 * dia
        margin = 3.0 * r
        if spec.length <= 2 * margin:
            continue
        x = rng.uniform(margin, spec.length - margin)
        if spec.flare > 0 and x < flare_length(spec) and rng.random() < 0.8:
            continue  # limbs are rare low on the trunk
        out.append(_Knot(x=x, theta=rng.uniform(-np.pi, np.pi), radius=r,
                         stub=spec.model(spec.stub_real) * rng.random() ** 1.5,
                         elong=rng.uniform(1.1, 1.6)))
    return out


def _end_plane(rng, max_deg: float) -> tuple[float, float]:
    """Slopes (dx/dy, dx/dz) of a sawn end tilted up to ``max_deg`` from square."""
    tilt = math.radians(max(0.0, max_deg)) * math.sqrt(rng.random())
    direction = rng.uniform(0, 2 * np.pi)
    s = math.tan(tilt)
    return s * math.cos(direction), s * math.sin(direction)


def build(spec: LogSpec) -> LogMesh:
    """Build one log from ``spec``."""
    rng = np.random.default_rng(spec.seed)
    seed = int(spec.seed) & 0x7FFFFFFF
    n_ar, n_al, m_cap = resolution(spec)
    L = spec.length
    r_butt, r_top = 0.5 * spec.d_butt, 0.5 * spec.d_top
    r_nominal_real = spec.real(0.5 * (r_butt + r_top))

    theta = np.arange(n_ar) * (2 * np.pi / n_ar)
    t = np.linspace(0.0, 1.0, n_al + 1)
    x = t * L
    T, X = np.meshgrid(theta, x)  # (n_al + 1, n_ar)

    # ---- the outside of the bark ----
    R = r_butt + (r_top - r_butt) * (X / L)
    if spec.flare > 0:
        fl = flare_length(spec)
        lobe = _lobes(T, max(3, int(spec.flare_lobes)), rng.uniform(0, 2 * np.pi), rng)
        fall = np.exp(-X / (0.35 * fl))
        R = R * (1.0 + spec.flare * fall * (0.7 + 0.6 * lobe))
    ov_phase = rng.uniform(0, np.pi)
    R = R * (1.0 + spec.ovality * np.cos(2 * (T - ov_phase)))
    pts_low = np.column_stack((np.cos(T).ravel(), np.sin(T).ravel(),
                               (X / max(spec.d_butt, 1e-6)).ravel() * 0.6))
    R = R * (1.0 + spec.lumpiness * noise.fbm(pts_low, 2, seed + 401).reshape(R.shape))

    # ---- bark relief ----
    thick = np.minimum(spec.model(spec.bark_thickness_real), 0.3 * R)
    depth = np.minimum(spec.model(spec.bark_depth_real), 0.85 * thick)
    h, tone = bark.surface(spec.style, T.ravel(), spec.real(X).ravel(), r_nominal_real,
                           spec.bark_scale_real, spec.bark_stretch, seed,
                           spacing=(spec.real(2 * np.pi * 0.5 * (r_butt + r_top) / n_ar),
                                    spec.real(L / n_al)))
    h, tone = h.reshape(R.shape), tone.reshape(R.shape)
    r = R - depth * (1.0 - h)
    wood = R - thick
    rgb = bark.colour(h.ravel(), tone.ravel(), spec.ridge, spec.furrow).reshape(R.shape + (3,))

    # ---- missing bark ----
    if spec.damage > 0:
        pts = np.column_stack((np.cos(T).ravel(), np.sin(T).ravel(),
                               (X / max(spec.d_butt, 1e-6)).ravel() * 0.5)) * 1.6
        v = noise.fbm(pts, 3, seed + 211).reshape(R.shape)
        thr = np.quantile(v, 1.0 - min(spec.damage, 0.95))
        bare = v > thr
        r = np.where(bare, wood + 0.12 * thick, r)
        streak = noise.fbm(np.column_stack((np.cos(T).ravel() * 6, np.sin(T).ravel() * 6,
                                            (X / max(spec.d_butt, 1e-6)).ravel() * 0.4)),
                           2, seed + 223).reshape(R.shape)
        # Bare wood on a log weathers and gets dirty quickly: duller than fresh sapwood.
        wood_rgb = (np.asarray(spec.sapwood) * 0.55 + np.array([0.42, 0.37, 0.30]) * 0.45) * 0.85
        wood_rgb = wood_rgb[None, None, :] * (0.9 + 0.2 * streak)[..., None]
        rgb = np.where(bare[..., None], np.clip(wood_rgb, 0, 1), rgb)

    # ---- cut limbs ----
    knots = _knots(spec, rng)
    knot_id = np.full(R.shape, -1, dtype=np.int64)
    uvn = np.zeros(R.shape + (2,))
    uvr = np.zeros(R.shape + (2,))
    ring_model = max(spec.model(spec.ring_mm_real), 0.5 * spec.d_butt / MAX_RINGS) * 0.5
    for k, kn in enumerate(knots):
        i0 = max(0, int((kn.x - 3 * kn.radius * kn.elong) / L * n_al) - 1)
        i1 = min(n_al + 1, int((kn.x + 3 * kn.radius * kn.elong) / L * n_al) + 2)
        if i1 <= i0:
            continue
        Ts, Xs, Rs = T[i0:i1], X[i0:i1], R[i0:i1]
        rk_c = float(np.interp(kn.x, x, R[:, int(round(kn.theta % (2 * np.pi) / (2 * np.pi) * n_ar)) % n_ar]))
        dth = _wrap(Ts - kn.theta)
        a = rk_c * dth
        b = (Xs - kn.x) / kn.elong
        d = np.sqrt(a * a + b * b)
        collar_h = rk_c + 0.3 * kn.radius
        plateau = (collar_h + kn.stub) / np.maximum(np.cos(dth), 0.2)
        wc = smoothstep(2.4 * kn.radius, 1.0 * kn.radius, d)
        r_sl = r[i0:i1]
        collar = r_sl + wc * np.maximum(collar_h - r_sl, 0.0)
        inside = d < kn.radius
        r[i0:i1] = np.where(inside, plateau, np.maximum(r_sl, collar))
        knot_id[i0:i1] = np.where(inside, k, knot_id[i0:i1])
        uvn[i0:i1] = np.where(inside[..., None], np.stack((a, b * kn.elong), -1) / kn.radius,
                              uvn[i0:i1])
        uvr[i0:i1] = np.where(inside[..., None], np.stack((a, b * kn.elong), -1) / ring_model,
                              uvr[i0:i1])
        _ = Rs  # the collar follows the local bark surface

    # Keep the bark surface outside the wood everywhere so the end faces stay valid.
    r = np.maximum(r, wood + 0.04 * thick)

    # ---- bow ----
    sweep_dir = rng.uniform(0, 2 * np.pi)
    bow = spec.sweep * L * np.sin(np.pi * x / L)  # per ring
    cy, cz = bow * math.cos(sweep_dir), bow * math.sin(sweep_dir)

    # ---- sawn ends ----
    a0, b0 = _end_plane(rng, spec.end_tilt_deg)
    a1, b1 = _end_plane(rng, spec.end_tilt_deg)
    Y = cy[:, None] + r * np.cos(T)
    Z = cz[:, None] + r * np.sin(T)
    x0 = a0 * Y[0] + b0 * Z[0]
    x1 = L + a1 * Y[-1] + b1 * Z[-1]
    Xs = (1.0 - t)[:, None] * x0[None, :] + t[:, None] * x1[None, :]
    side = np.stack((Xs, Y, Z), axis=-1).reshape(-1, 3)

    verts = [side]
    cols = [rgb.reshape(-1, 3)]
    uvn_l = [uvn.reshape(-1, 2)]
    uvr_l = [uvr.reshape(-1, 2)]
    tris, mats = [], []

    # side faces
    i = np.arange(n_al)[:, None]
    j = np.arange(n_ar)[None, :]
    v00 = i * n_ar + j
    v01 = i * n_ar + (j + 1) % n_ar
    v10 = (i + 1) * n_ar + j
    v11 = (i + 1) * n_ar + (j + 1) % n_ar
    side_tris = np.concatenate((np.stack((v00, v01, v11), -1).reshape(-1, 3),
                                np.stack((v00, v11, v10), -1).reshape(-1, 3)))
    kid = knot_id.reshape(-1)
    in_knot = (kid[side_tris] >= 0).all(axis=1) & (kid[side_tris[:, 0]] == kid[side_tris[:, 1]]) \
        & (kid[side_tris[:, 1]] == kid[side_tris[:, 2]])
    tris.append(side_tris)
    mats.append(np.where(in_knot, END_GRAIN, BARK))

    # Real growth rings are far too fine to see on a model log (an HO log has
    # 100 or more across a few millimetres), so they are drawn no finer than
    # MAX_RINGS across the radius, as a modeller would paint them.
    ring_model_wood = max(spec.model(spec.ring_mm_real), 0.5 * spec.d_butt / MAX_RINGS)
    rough_amp = min(spec.model(4.0), 0.3 * L / n_al) if spec.end_rough else 0.0
    pith_dir = rng.uniform(0, 2 * np.pi)
    pith_off = rng.uniform(0.0, 0.12)
    n_side = len(side)
    offset = n_side
    end_info = []
    for end in (0, 1):
        row = 0 if end == 0 else n_al
        a_, b_ = (a0, b0) if end == 0 else (a1, b1)
        base_x = 0.0 if end == 0 else L
        ccy, ccz = float(cy[row]), float(cz[row])
        w_r = wood[row]
        outer_idx = row * n_ar + np.arange(n_ar)
        wy = ccy + w_r * np.cos(theta)
        wz = ccz + w_r * np.sin(theta)
        rw_mean = float(w_r.mean())
        po = pith_off * rw_mean * (1.0 + rng.uniform(-0.3, 0.3))
        py = ccy + po * math.cos(pith_dir + rng.uniform(-0.3, 0.3))
        pz = ccz + po * math.sin(pith_dir + rng.uniform(-0.3, 0.3))
        rings_y = [wy]
        rings_z = [wz]
        for k in range(1, m_cap + 1):
            f = 1.0 - k / (m_cap + 1)
            rings_y.append(py + (wy - py) * f)
            rings_z.append(pz + (wz - pz) * f)
        ry = np.concatenate(rings_y + [np.array([py])])
        rz = np.concatenate(rings_z + [np.array([pz])])
        rx = base_x + a_ * ry + b_ * rz
        if rough_amp > 0:
            q = np.column_stack((ry, rz, np.full_like(ry, float(end) * 7.3))) / max(rw_mean * 0.35, 1e-6)
            rx = rx + rough_amp * noise.fbm(q, 2, seed + 601 + end)
        cap_verts = np.column_stack((rx, ry, rz))
        n_cap = len(cap_verts)
        ring_idx = [outer_idx] + [offset + k * n_ar + np.arange(n_ar) for k in range(m_cap + 1)]
        centre = offset + n_cap - 1
        verts.append(cap_verts)
        c = np.empty((n_cap, 3))
        # The bark seen in the cut: outer bark colour at the surface shading to
        # the reddish inner bark where it meets the wood.
        c[:n_ar] = 0.6 * np.asarray(spec.inner_bark) + 0.4 * np.asarray(spec.furrow)
        c[n_ar:] = np.asarray(spec.sapwood)
        cols.append(c)
        dy, dz = ry - py, rz - pz
        norm_y, norm_z = dy / max(rw_mean, 1e-9), dz / max(rw_mean, 1e-9)
        uvn_l.append(np.column_stack((norm_y, norm_z)))
        uvr_l.append(np.column_stack((dy, dz)) / max(ring_model_wood, 1e-9))

        cap_t, cap_m = [], []
        jj = np.arange(n_ar)
        jn = (jj + 1) % n_ar
        for k in range(len(ring_idx) - 1):
            A, B = ring_idx[k], ring_idx[k + 1]
            band = np.concatenate((np.stack((A[jj], A[jn], B[jn]), -1),
                                   np.stack((A[jj], B[jn], B[jj]), -1)))
            cap_t.append(band)
            cap_m.append(np.full(len(band), BARK if k == 0 else END_GRAIN))
        B = ring_idx[-1]
        fan = np.stack((B[jj], B[jn], np.full(n_ar, centre)), -1)
        cap_t.append(fan)
        cap_m.append(np.full(len(fan), END_GRAIN))
        cap_t = np.concatenate(cap_t)
        cap_m = np.concatenate(cap_m)
        # Wind the face so its normal points out of the log (-X at the butt, +X at the top).
        all_v = np.concatenate(verts)
        p0, p1, p2 = all_v[cap_t[:, 0]], all_v[cap_t[:, 1]], all_v[cap_t[:, 2]]
        nx = np.cross(p1 - p0, p2 - p0)[:, 0].sum()
        if (nx > 0) == (end == 0):
            cap_t = cap_t[:, [0, 2, 1]]
        tris.append(cap_t)
        mats.append(cap_m)
        offset += n_cap
        end_info.append({"wood_radius": rw_mean, "pith": (py, pz)})

    V = np.concatenate(verts)
    F = np.concatenate(tris).astype(np.int64)
    M = np.concatenate(mats).astype(np.int64)
    C = srgb_to_linear(np.concatenate(cols))
    C = np.column_stack((C, np.ones(len(C))))

    info = {
        "points_round": n_ar, "rings": n_al, "face_rings": m_cap,
        "triangles": len(F), "knots": len(knots),
        "mid_radius": float(np.interp(0.5 * L, x, R.mean(axis=1))),
        "butt_radius_max": float(R[0].max()),
        "top_radius": float(R[-1].mean()),
        "bark_thickness": float(thick.mean()), "bark_depth": float(depth.mean()),
        "ends": end_info,
    }
    return LogMesh(V, F, M, C, np.concatenate(uvn_l), np.concatenate(uvr_l), info)


def volume(verts: np.ndarray, tris: np.ndarray) -> float:
    """Volume enclosed by a closed, outward-facing triangle mesh (divergence theorem)."""
    p0, p1, p2 = verts[tris[:, 0]], verts[tris[:, 1]], verts[tris[:, 2]]
    return float(np.einsum("ij,ij->i", p0, np.cross(p1, p2)).sum() / 6.0)


def open_edges(tris: np.ndarray) -> int:
    """Edges used by other than exactly two triangles (0 for a closed mesh)."""
    e = np.concatenate((tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]))
    e.sort(axis=1)
    _, counts = np.unique(e, axis=0, return_counts=True)
    return int((counts != 2).sum())
