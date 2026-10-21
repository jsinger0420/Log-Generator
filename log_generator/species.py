"""Built-in tree species: bark look, wood colours and typical log sizes. No bpy.

Sizes are full-size (prototype): diameters in inches, lengths in feet,
bark sizes and ring widths in millimetres. Colours are sRGB, 0 to 1.

Bark styles (see bark.py for how each is drawn):

- FURROWED: ridges running along the log split by deep, narrow furrows
  (Douglas fir, oaks, white pine, hemlock).
- PLATED: flat plates separated by dark crevices (ponderosa and southern
  pines, sugar maple).
- FIBROUS: long, soft, stringy strips (redwood, cedar, cypress).
- SCALY: small flaky scales (spruce, cherry, white oak).
- INTERLACED: narrow ridges forming a diamond network (ash, poplar).
- SHAGGY: long strips that lift away from the trunk (shagbark hickory).
- SMOOTH: thin, nearly smooth bark (beech).
- BIRCH: smooth bark with dark horizontal lenticels (paper birch).

Typical sizes are for mainstream logging of the steam era (1880s to
1950s): long logs in the West, 12 to 16 ft multiples in the East. They
fill the size fields only when you press "Use Typical Size".
"""

from __future__ import annotations

from dataclasses import dataclass

STYLES = ("FURROWED", "PLATED", "FIBROUS", "SCALY", "INTERLACED", "SHAGGY", "SMOOTH", "BIRCH")

STYLE_LABELS = {
    "FURROWED": ("Furrowed", "Ridges along the log split by deep narrow furrows"),
    "PLATED": ("Plated", "Flat plates separated by dark crevices"),
    "FIBROUS": ("Fibrous", "Long, soft, stringy strips"),
    "SCALY": ("Scaly", "Small flaky scales"),
    "INTERLACED": ("Interlaced", "Narrow ridges forming a diamond network"),
    "SHAGGY": ("Shaggy", "Long strips lifting away from the trunk"),
    "SMOOTH": ("Smooth", "Thin, nearly smooth bark"),
    "BIRCH": ("Birch", "Smooth bark with dark horizontal lenticels"),
}

RGB = tuple[float, float, float]


@dataclass(frozen=True)
class Species:
    """One tree species: how its bark, wood and logs look."""

    key: str
    name: str
    kind: str  # "SOFTWOOD" or "HARDWOOD"
    description: str
    # typical log (prototype)
    diameter_in: float  # large-end diameter outside the bark
    length_ft: float
    top_pct: float  # small-end diameter as a percentage of the large end
    # bark
    style: str
    bark_scale_mm: float  # size of one bark feature (ridge spacing, plate size)
    bark_stretch: float  # how much longer features are along the log than around it
    bark_depth_mm: float  # furrow depth
    bark_thickness_mm: float  # bark thickness at the cut end
    ridge: RGB  # colour of the bark's outer surface
    furrow: RGB  # colour deep in the furrows
    inner_bark: RGB  # colour of the inner bark seen at the cut end
    # wood
    sapwood: RGB
    heartwood: RGB
    heart_frac: float  # heartwood share of the wood radius
    ring_mm: float  # growth ring width
    # shape
    flare: float  # extra diameter at the butt of a flared log, as a fraction
    flare_lobes: int  # root buttresses round a flared butt
    knots_per_m: float  # cut limbs per metre of log
    knot_mm: float  # typical cut limb diameter
    sweep: float  # typical bow, as a fraction of the length
    specific_gravity: float  # green log, for how deep it floats (1.0 or more sinks)


def _s(**kw) -> Species:
    """A Species from keyword arguments (keeps the table below readable)."""
    return Species(**kw)


SPECIES: tuple[Species, ...] = (
    # ---- softwoods ----
    _s(key="DOUGLAS_FIR", name="Douglas Fir", kind="SOFTWOOD",
       description="Pacific Northwest giant; thick, deeply furrowed dark bark",
       diameter_in=36, length_ft=32, top_pct=85,
       style="FURROWED", bark_scale_mm=70, bark_stretch=7.0, bark_depth_mm=40, bark_thickness_mm=90,
       ridge=(0.36, 0.27, 0.22), furrow=(0.11, 0.07, 0.05), inner_bark=(0.55, 0.26, 0.16),
       sapwood=(0.86, 0.73, 0.55), heartwood=(0.80, 0.48, 0.30), heart_frac=0.8, ring_mm=3.0,
       flare=0.25, flare_lobes=5, knots_per_m=0.8, knot_mm=50, sweep=0.006,
       specific_gravity=0.61),
    _s(key="PONDEROSA", name="Ponderosa Pine", kind="SOFTWOOD",
       description="Western pine with big orange-cinnamon plates and black crevices",
       diameter_in=30, length_ft=32, top_pct=85,
       style="PLATED", bark_scale_mm=150, bark_stretch=1.7, bark_depth_mm=35, bark_thickness_mm=60,
       ridge=(0.66, 0.40, 0.23), furrow=(0.10, 0.07, 0.06), inner_bark=(0.62, 0.32, 0.18),
       sapwood=(0.93, 0.85, 0.67), heartwood=(0.82, 0.63, 0.42), heart_frac=0.5, ring_mm=3.0,
       flare=0.2, flare_lobes=5, knots_per_m=1.2, knot_mm=45, sweep=0.006,
       specific_gravity=0.73),
    _s(key="WHITE_PINE", name="Eastern White Pine", kind="SOFTWOOD",
       description="Northeast and Great Lakes pine; dark grey ridged bark, knotty",
       diameter_in=24, length_ft=16, top_pct=82,
       style="FURROWED", bark_scale_mm=50, bark_stretch=4.5, bark_depth_mm=20, bark_thickness_mm=30,
       ridge=(0.34, 0.31, 0.28), furrow=(0.12, 0.10, 0.09), inner_bark=(0.55, 0.32, 0.20),
       sapwood=(0.93, 0.86, 0.70), heartwood=(0.86, 0.70, 0.48), heart_frac=0.6, ring_mm=4.0,
       flare=0.15, flare_lobes=5, knots_per_m=2.0, knot_mm=40, sweep=0.008,
       specific_gravity=0.58),
    _s(key="YELLOW_PINE", name="Southern Yellow Pine", kind="SOFTWOOD",
       description="Longleaf and loblolly pine of the South; reddish scaly plates",
       diameter_in=18, length_ft=24, top_pct=85,
       style="PLATED", bark_scale_mm=80, bark_stretch=1.8, bark_depth_mm=20, bark_thickness_mm=30,
       ridge=(0.46, 0.31, 0.23), furrow=(0.12, 0.09, 0.07), inner_bark=(0.60, 0.30, 0.18),
       sapwood=(0.92, 0.82, 0.60), heartwood=(0.83, 0.56, 0.32), heart_frac=0.5, ring_mm=3.0,
       flare=0.12, flare_lobes=4, knots_per_m=0.8, knot_mm=35, sweep=0.006,
       specific_gravity=0.88),
    _s(key="REDWOOD", name="Coast Redwood", kind="SOFTWOOD",
       description="California giant; thick, soft, fibrous red-brown bark",
       diameter_in=60, length_ft=20, top_pct=90,
       style="FIBROUS", bark_scale_mm=40, bark_stretch=10.0, bark_depth_mm=50, bark_thickness_mm=150,
       ridge=(0.53, 0.31, 0.22), furrow=(0.22, 0.12, 0.09), inner_bark=(0.62, 0.30, 0.18),
       sapwood=(0.92, 0.82, 0.70), heartwood=(0.64, 0.26, 0.16), heart_frac=0.85, ring_mm=4.0,
       flare=0.35, flare_lobes=6, knots_per_m=0.3, knot_mm=60, sweep=0.004,
       specific_gravity=0.97),
    _s(key="CEDAR", name="Western Red Cedar", kind="SOFTWOOD",
       description="Stringy grey-red bark, strongly flared and tapered butt",
       diameter_in=36, length_ft=24, top_pct=80,
       style="FIBROUS", bark_scale_mm=30, bark_stretch=12.0, bark_depth_mm=15, bark_thickness_mm=20,
       ridge=(0.56, 0.43, 0.36), furrow=(0.30, 0.18, 0.14), inner_bark=(0.62, 0.34, 0.22),
       sapwood=(0.90, 0.82, 0.68), heartwood=(0.68, 0.39, 0.24), heart_frac=0.85, ring_mm=3.0,
       flare=0.4, flare_lobes=7, knots_per_m=0.6, knot_mm=45, sweep=0.008,
       specific_gravity=0.45),
    _s(key="SPRUCE", name="Sitka Spruce", kind="SOFTWOOD",
       description="Coastal spruce with thin, flaky grey-brown scales",
       diameter_in=36, length_ft=32, top_pct=85,
       style="SCALY", bark_scale_mm=25, bark_stretch=1.4, bark_depth_mm=8, bark_thickness_mm=12,
       ridge=(0.46, 0.37, 0.30), furrow=(0.20, 0.15, 0.12), inner_bark=(0.58, 0.36, 0.24),
       sapwood=(0.93, 0.87, 0.73), heartwood=(0.86, 0.71, 0.55), heart_frac=0.6, ring_mm=3.0,
       flare=0.25, flare_lobes=5, knots_per_m=0.8, knot_mm=35, sweep=0.005,
       specific_gravity=0.50),
    _s(key="HEMLOCK", name="Western Hemlock", kind="SOFTWOOD",
       description="Red-brown bark with shallow furrows",
       diameter_in=30, length_ft=32, top_pct=85,
       style="FURROWED", bark_scale_mm=35, bark_stretch=4.5, bark_depth_mm=12, bark_thickness_mm=20,
       ridge=(0.43, 0.32, 0.26), furrow=(0.18, 0.12, 0.10), inner_bark=(0.58, 0.28, 0.18),
       sapwood=(0.90, 0.80, 0.65), heartwood=(0.84, 0.69, 0.50), heart_frac=0.6, ring_mm=3.0,
       flare=0.2, flare_lobes=5, knots_per_m=1.0, knot_mm=35, sweep=0.006,
       specific_gravity=0.66),
    _s(key="CYPRESS", name="Bald Cypress", kind="SOFTWOOD",
       description="Southern swamp tree; fibrous bark and a heavily buttressed, tapered butt",
       diameter_in=30, length_ft=20, top_pct=75,
       style="FIBROUS", bark_scale_mm=35, bark_stretch=8.0, bark_depth_mm=12, bark_thickness_mm=15,
       ridge=(0.56, 0.46, 0.39), furrow=(0.30, 0.22, 0.18), inner_bark=(0.60, 0.36, 0.24),
       sapwood=(0.90, 0.80, 0.62), heartwood=(0.71, 0.51, 0.33), heart_frac=0.7, ring_mm=3.0,
       flare=0.6, flare_lobes=6, knots_per_m=0.4, knot_mm=45, sweep=0.008,
       specific_gravity=0.85),
    # ---- hardwoods ----
    _s(key="RED_OAK", name="Red Oak", kind="HARDWOOD",
       description="Dark ridges with shiny flat-topped strips; green logs barely float",
       diameter_in=24, length_ft=16, top_pct=85,
       style="FURROWED", bark_scale_mm=40, bark_stretch=6.0, bark_depth_mm=18, bark_thickness_mm=25,
       ridge=(0.39, 0.36, 0.33), furrow=(0.12, 0.10, 0.09), inner_bark=(0.62, 0.38, 0.26),
       sapwood=(0.88, 0.76, 0.58), heartwood=(0.73, 0.51, 0.39), heart_frac=0.75, ring_mm=4.0,
       flare=0.15, flare_lobes=5, knots_per_m=0.8, knot_mm=50, sweep=0.01,
       specific_gravity=1.0),
    _s(key="WHITE_OAK", name="White Oak", kind="HARDWOOD",
       description="Light grey, scaly-plated bark; green logs barely float",
       diameter_in=24, length_ft=16, top_pct=85,
       style="SCALY", bark_scale_mm=60, bark_stretch=2.0, bark_depth_mm=15, bark_thickness_mm=22,
       ridge=(0.56, 0.53, 0.49), furrow=(0.22, 0.20, 0.18), inner_bark=(0.66, 0.48, 0.32),
       sapwood=(0.90, 0.80, 0.62), heartwood=(0.71, 0.56, 0.38), heart_frac=0.75, ring_mm=3.0,
       flare=0.15, flare_lobes=5, knots_per_m=0.8, knot_mm=50, sweep=0.01,
       specific_gravity=1.0),
    _s(key="MAPLE", name="Sugar Maple", kind="HARDWOOD",
       description="Hard maple: long grey plates curling at the edges, pale wood",
       diameter_in=20, length_ft=16, top_pct=85,
       style="PLATED", bark_scale_mm=60, bark_stretch=3.5, bark_depth_mm=12, bark_thickness_mm=15,
       ridge=(0.46, 0.41, 0.36), furrow=(0.18, 0.15, 0.13), inner_bark=(0.70, 0.52, 0.36),
       sapwood=(0.94, 0.88, 0.76), heartwood=(0.71, 0.56, 0.41), heart_frac=0.35, ring_mm=3.0,
       flare=0.15, flare_lobes=5, knots_per_m=1.2, knot_mm=40, sweep=0.01,
       specific_gravity=1.0),
    _s(key="ASH", name="White Ash", kind="HARDWOOD",
       description="Grey bark with a tight diamond pattern of ridges",
       diameter_in=20, length_ft=16, top_pct=85,
       style="INTERLACED", bark_scale_mm=35, bark_stretch=2.5, bark_depth_mm=12, bark_thickness_mm=15,
       ridge=(0.53, 0.51, 0.47), furrow=(0.20, 0.19, 0.17), inner_bark=(0.68, 0.52, 0.36),
       sapwood=(0.94, 0.88, 0.75), heartwood=(0.76, 0.63, 0.46), heart_frac=0.5, ring_mm=4.0,
       flare=0.12, flare_lobes=5, knots_per_m=0.8, knot_mm=40, sweep=0.008,
       specific_gravity=0.80),
    _s(key="POPLAR", name="Yellow Poplar", kind="HARDWOOD",
       description="Tulip tree: tall, straight, grey bark with shallow interlacing ridges",
       diameter_in=30, length_ft=16, top_pct=88,
       style="INTERLACED", bark_scale_mm=40, bark_stretch=3.0, bark_depth_mm=8, bark_thickness_mm=12,
       ridge=(0.56, 0.54, 0.49), furrow=(0.25, 0.24, 0.22), inner_bark=(0.70, 0.60, 0.42),
       sapwood=(0.94, 0.90, 0.78), heartwood=(0.67, 0.66, 0.46), heart_frac=0.7, ring_mm=5.0,
       flare=0.15, flare_lobes=5, knots_per_m=0.5, knot_mm=40, sweep=0.004,
       specific_gravity=0.80),
    _s(key="CHERRY", name="Black Cherry", kind="HARDWOOD",
       description="Dark, flaky 'burnt potato chip' bark, reddish heartwood",
       diameter_in=18, length_ft=12, top_pct=85,
       style="SCALY", bark_scale_mm=25, bark_stretch=1.2, bark_depth_mm=8, bark_thickness_mm=10,
       ridge=(0.21, 0.14, 0.12), furrow=(0.08, 0.05, 0.05), inner_bark=(0.55, 0.30, 0.20),
       sapwood=(0.90, 0.80, 0.65), heartwood=(0.66, 0.33, 0.21), heart_frac=0.7, ring_mm=3.0,
       flare=0.1, flare_lobes=4, knots_per_m=1.0, knot_mm=35, sweep=0.012,
       specific_gravity=0.85),
    _s(key="CHESTNUT", name="American Chestnut", kind="HARDWOOD",
       description="Before the blight, a staple of Appalachian logging; ridged grey bark",
       diameter_in=30, length_ft=16, top_pct=85,
       style="FURROWED", bark_scale_mm=50, bark_stretch=5.5, bark_depth_mm=18, bark_thickness_mm=25,
       ridge=(0.41, 0.36, 0.31), furrow=(0.14, 0.11, 0.09), inner_bark=(0.62, 0.40, 0.26),
       sapwood=(0.90, 0.82, 0.65), heartwood=(0.69, 0.51, 0.33), heart_frac=0.9, ring_mm=4.0,
       flare=0.2, flare_lobes=5, knots_per_m=0.6, knot_mm=45, sweep=0.008,
       specific_gravity=0.90),
    _s(key="HICKORY", name="Shagbark Hickory", kind="HARDWOOD",
       description="Long grey strips of bark peeling away from the trunk",
       diameter_in=18, length_ft=12, top_pct=88,
       style="SHAGGY", bark_scale_mm=50, bark_stretch=8.0, bark_depth_mm=25, bark_thickness_mm=25,
       ridge=(0.46, 0.43, 0.39), furrow=(0.15, 0.13, 0.12), inner_bark=(0.68, 0.52, 0.36),
       sapwood=(0.93, 0.88, 0.78), heartwood=(0.67, 0.51, 0.37), heart_frac=0.4, ring_mm=3.0,
       flare=0.1, flare_lobes=4, knots_per_m=0.6, knot_mm=40, sweep=0.008,
       specific_gravity=1.0),
    _s(key="BEECH", name="American Beech", kind="HARDWOOD",
       description="Smooth, light grey bark",
       diameter_in=20, length_ft=12, top_pct=88,
       style="SMOOTH", bark_scale_mm=30, bark_stretch=1.0, bark_depth_mm=1.5, bark_thickness_mm=8,
       ridge=(0.63, 0.63, 0.61), furrow=(0.42, 0.42, 0.40), inner_bark=(0.72, 0.58, 0.42),
       sapwood=(0.91, 0.81, 0.67), heartwood=(0.81, 0.66, 0.51), heart_frac=0.3, ring_mm=3.0,
       flare=0.1, flare_lobes=4, knots_per_m=0.5, knot_mm=40, sweep=0.008,
       specific_gravity=0.95),
    _s(key="BIRCH", name="Paper Birch", kind="HARDWOOD",
       description="White bark with dark horizontal lenticels",
       diameter_in=14, length_ft=12, top_pct=85,
       style="BIRCH", bark_scale_mm=30, bark_stretch=0.25, bark_depth_mm=1.5, bark_thickness_mm=6,
       ridge=(0.88, 0.86, 0.82), furrow=(0.12, 0.11, 0.10), inner_bark=(0.72, 0.48, 0.32),
       sapwood=(0.93, 0.88, 0.78), heartwood=(0.85, 0.75, 0.60), heart_frac=0.2, ring_mm=3.0,
       flare=0.08, flare_lobes=4, knots_per_m=1.2, knot_mm=30, sweep=0.01,
       specific_gravity=0.90),
    _s(key="WALNUT", name="Black Walnut", kind="HARDWOOD",
       description="Dark, deeply ridged bark and chocolate-brown heartwood",
       diameter_in=20, length_ft=10, top_pct=85,
       style="FURROWED", bark_scale_mm=40, bark_stretch=4.5, bark_depth_mm=15, bark_thickness_mm=20,
       ridge=(0.23, 0.19, 0.16), furrow=(0.08, 0.06, 0.05), inner_bark=(0.45, 0.28, 0.18),
       sapwood=(0.85, 0.75, 0.60), heartwood=(0.33, 0.21, 0.15), heart_frac=0.7, ring_mm=4.0,
       flare=0.15, flare_lobes=5, knots_per_m=0.5, knot_mm=45, sweep=0.01,
       specific_gravity=1.0),
)

BY_KEY = {s.key: s for s in SPECIES}


def get(key: str) -> Species:
    """A species by key; Douglas fir for an unknown key."""
    return BY_KEY.get(key, SPECIES[0])
