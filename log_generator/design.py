"""From the panel's settings to LogSpecs, one per log. No bpy, so it can be tested.

``Design`` holds the settings in fixed units (full-size mm for prototype
sizes, model mm for model sizes). properties.LOGGEN_Settings.design()
fills one in from the panel.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from . import scales, species
from .logmesh import LogSpec, resolution

# Smallest spacing between mesh points, in model mm, for each detail level.
DETAIL_SPACING = {"COARSE": 0.4, "MEDIUM": 0.15, "FINE": 0.08}


@dataclass
class Design:
    """Every setting that shapes the logs, in fixed units."""

    species: str = "DOUGLAS_FIR"
    bark_style: str = "SPECIES"  # or one of species.STYLES
    scale_n: float = 87.1
    size_mode: str = "PROTOTYPE"  # or "MODEL"
    length_real: float = 32 * 304.8  # full-size mm
    diameter_real: float = 36 * 25.4  # full-size mm, large end outside the bark
    length_model: float = 100.0  # model mm
    diameter_model: float = 8.0  # model mm
    top_pct: float = 85.0
    flare_chance: float = 0.0  # 0 to 1
    flare_amount: float = 1.0  # times the species' flare
    ovality: float = 0.04
    bow: float = 1.0  # times the species' typical bow
    knots: float = 1.0  # times the species' limb count
    stub_real: float = 25.0  # full-size mm
    bark_depth: float = 1.0  # times the species' furrow depth
    bark_scale: float = 1.0  # times the species' bark feature size
    damage: float = 0.05  # 0 to 1
    end_tilt: float = 3.0  # degrees
    end_rough: bool = True
    detail: str = "MEDIUM"
    max_triangles: int = 400_000
    carve_rings: bool = False
    carve_depth: float = 0.05  # model mm
    carve_count: int = 12
    hollow: bool = True
    wall: float = 1.0  # model mm
    drain_hole: float = 1.5  # model mm diameter, 0 for none
    arrangement: str = "LOGS"  # "LOGS" (separate logs), "STACK" or "FLOAT" (half logs)
    count: int = 1
    length_var: float = 0.0  # 0 to 1, plus or minus
    diameter_var: float = 0.0  # 0 to 1, plus or minus

    @property
    def sp(self) -> species.Species:
        """The chosen species."""
        return species.get(self.species)

    def style(self) -> str:
        """The bark style: the species' own unless overridden."""
        return self.sp.style if self.bark_style == "SPECIES" else self.bark_style

    def length(self) -> float:
        """Nominal log length in model mm."""
        return self.length_model if self.size_mode == "MODEL" else self.length_real / self.scale_n

    def diameter(self) -> float:
        """Nominal large-end diameter (outside the bark) in model mm."""
        return self.diameter_model if self.size_mode == "MODEL" else self.diameter_real / self.scale_n

    def log_count(self) -> int:
        """How many logs to make."""
        return max(1, int(self.count))


def spacing(d: Design, length: float, diameter: float) -> tuple[float, float]:
    """(round, along) spacing between mesh points in model mm, fine enough for the bark."""
    sp = d.sp
    floor = DETAIL_SPACING.get(d.detail, 0.15)
    feature = sp.bark_scale_mm * d.bark_scale / d.scale_n  # one bark feature, model mm
    style = d.style()
    if style in ("SMOOTH",):
        feature = max(feature, diameter)  # nothing fine to resolve
    stretch = max(min(sp.bark_stretch, 6.0), 0.25)
    # The bark's finest noise octave is about a quarter of the feature size;
    # sample it at least 3 times per period so it doesn't alias into ledges.
    around = max(feature / 8.0, floor)
    along = max(feature * stretch / 12.0, floor)
    along = min(along, max(length / 8.0, floor), 2.0 * diameter)
    return around, along


def make_spec(d: Design, length: float, diameter: float, flare: float, seed: int,
              top_pct: float | None = None) -> LogSpec:
    """A LogSpec for one log of the design at a given size, flare, seed and taper."""
    sp = d.sp
    around, along = spacing(d, length, diameter)
    top = d.top_pct if top_pct is None else top_pct
    return LogSpec(
        scale_n=d.scale_n, length=length, d_butt=diameter,
        d_top=diameter * max(min(top, 100.0), 10.0) / 100.0,
        flare=flare, flare_lobes=sp.flare_lobes, ovality=d.ovality,
        sweep=sp.sweep * d.bow, style=d.style(),
        bark_scale_real=sp.bark_scale_mm * d.bark_scale, bark_stretch=sp.bark_stretch,
        bark_depth_real=sp.bark_depth_mm * d.bark_depth,
        bark_thickness_real=max(sp.bark_thickness_mm, sp.bark_depth_mm * d.bark_depth * 1.2),
        ridge=sp.ridge, furrow=sp.furrow, inner_bark=sp.inner_bark, sapwood=sp.sapwood,
        heartwood=sp.heartwood, heart_frac=sp.heart_frac, carve_rings=d.carve_rings,
        carve_depth=d.carve_depth, carve_count=max(2, int(d.carve_count)),
        hollow=d.hollow, wall=d.wall,
        ring_mm_real=sp.ring_mm, knots_per_m=sp.knots_per_m * d.knots, knot_real=sp.knot_mm,
        stub_real=d.stub_real, damage=d.damage, end_tilt_deg=d.end_tilt, end_rough=d.end_rough,
        around_spacing=around, along_spacing=along, max_triangles=d.max_triangles, seed=seed,
    )


def log_specs(d: Design, seed: int) -> list[LogSpec]:
    """One LogSpec per log, each varied by its own random draw from ``seed``.

    With more than one log, each gets its own length and diameter within the
    variation limits and a slightly different taper; every log also has its
    own bark, limbs, bow and end cuts (its own seed), and its own roll of the
    dice for a flared butt.
    """
    out = []
    multi = d.log_count() > 1
    for i in range(d.log_count()):
        rng = random.Random(seed * 1_000_003 + i * 7919)
        length, diameter, top = d.length(), d.diameter(), d.top_pct
        if multi:
            length *= 1.0 + rng.uniform(-d.length_var, d.length_var)
            diameter *= 1.0 + rng.uniform(-d.diameter_var, d.diameter_var)
            top = min(100.0, top + rng.uniform(-3.0, 3.0))
        flared = rng.random() < d.flare_chance
        flare = d.sp.flare * d.flare_amount if flared else 0.0
        out.append(make_spec(d, length, diameter, flare, (seed + i * 104729) % (2**31 - 1) or 1,
                             top))
    return out


def errors(d: Design) -> list[str]:
    """Settings that can't make a log, as messages saying how to fix them."""
    errs = []
    if d.length() <= 0:
        errs.append("Enter a log length greater than 0.")
    if d.diameter() <= 0:
        errs.append("Enter a log diameter greater than 0.")
    if d.length() > 0 and d.diameter() > 0 and d.length() < d.diameter() * 0.5:
        errs.append("The log is shorter than half its diameter; check length and diameter.")
    if d.scale_n <= 0:
        errs.append("The scale ratio must be greater than 0.")
    return errs


def summary(d: Design) -> dict:
    """Facts for the panel about the nominal log: sizes, taper, board feet, mesh size."""
    L, D = d.length(), d.diameter()
    top = D * d.top_pct / 100.0
    n = d.scale_n
    real_L, real_D, real_top = L * n, D * n, top * n
    bark_real = d.sp.bark_thickness_mm
    small_in = max(real_top - 2 * bark_real, 0.0) / scales.MM_PER_INCH
    length_ft = real_L / scales.MM_PER_FOOT
    taper_in_per_ft = (real_D - real_top) / scales.MM_PER_INCH / max(length_ft, 1e-9)
    spec = make_spec(d, L, D, d.sp.flare * d.flare_amount if d.flare_chance > 0 else 0.0, 1)
    n_ar, n_al, m = resolution(spec)
    tris = 2 * n_ar * n_al + 2 * n_ar * (2 * m + 2)
    return {
        "length": L, "diameter": D, "top": top,
        "real_length": real_L, "real_diameter": real_D, "real_top": real_top,
        "taper_in_per_ft": taper_in_per_ft,
        "doyle": scales.doyle_board_feet(small_in, length_ft),
        "scribner": scales.scribner_board_feet(small_in, length_ft),
        "triangles": tris, "bark_depth_model": min(d.sp.bark_depth_mm * d.bark_depth,
                                                    0.85 * bark_real * 2) / n,
        "points_round": n_ar, "rings": n_al,
        "carve_pitch": max(D / 2 - bark_real / n, 0.0) / max(d.carve_count, 1),
        **hollow_estimate(d, L, D, top),
        "flare_real": real_D * (1 + d.sp.flare * d.flare_amount) if d.flare_chance > 0 else 0.0,
    }


def mid_radius(spec: LogSpec) -> float:
    """A log's radius at mid-length (model mm), outside the bark, before bark relief."""
    return 0.25 * (spec.d_butt + spec.d_top)


def hollow_estimate(d: Design, length: float, diameter: float, top: float) -> dict:
    """Whether the nominal log can be hollowed, and about how much material that saves.

    Returns ``hollow_ok`` (False when the wood is too thin for the wall)
    and ``hollow_saving`` (0 to 1, the share of the solid log's volume).
    """
    from .logmesh import MIN_CAVITY
    if not d.hollow:
        return {"hollow_ok": False, "hollow_saving": 0.0}
    r = 0.25 * (diameter + top)
    bark = min(d.sp.bark_thickness_mm / d.scale_n, 0.3 * r)
    ri = r - bark - d.wall
    inside = length - 2 * d.wall
    if ri < MIN_CAVITY or inside < 2 * d.wall:
        return {"hollow_ok": False, "hollow_saving": 0.0}
    return {"hollow_ok": True, "hollow_saving": (ri / r) ** 2 * inside / length}
