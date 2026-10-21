"""Model railroad scales and unit conversion. No bpy, so it can be tested.

Prototype (full-size) sizes are entered in feet and inches or metres and
centimetres and kept as full-size millimetres internally. Model sizes are
millimetres: full-size millimetres divided by the scale's N (as in 1:N).
"""

from __future__ import annotations

MM_PER_INCH = 25.4
MM_PER_FOOT = 304.8

# key: (menu label, N in 1:N, tooltip)
SCALES: dict[str, tuple[str, float, str]] = {
    "T": ("T 1:450", 450.0, "T scale, 3 mm gauge"),
    "Z": ("Z 1:220", 220.0, "Z scale, 6.5 mm gauge"),
    "N": ("N / Nn3 1:160", 160.0, "N scale (US and Europe); also Nn3"),
    "N150": ("N (Japan) 1:150", 150.0, "Japanese N scale"),
    "N148": ("N (UK) 1:148", 148.0, "British N scale"),
    "TT": ("TT 1:120", 120.0, "TT scale"),
    "HO": ("HO / HOn3 / HOn30 1:87.1", 87.1, "HO scale, including HOn3 and HOn30 narrow gauge"),
    "OO": ("OO 1:76.2", 76.2, "British OO (4 mm to the foot)"),
    "S": ("S / Sn3 1:64", 64.0, "S scale, including Sn3 narrow gauge"),
    "O48": ("O / On3 / On30 1:48", 48.0, "US O scale (1/4 inch to the foot), On3 and On30"),
    "O45": ("O (Europe) 1:45", 45.0, "Continental European O scale"),
    "O43": ("O (UK) 1:43.5", 43.5, "British O (7 mm to the foot)"),
    "G32": ("Gauge 1 1:32", 32.0, "Gauge 1 standard gauge"),
    "G29": ("G 1:29", 29.0, "1:29 standard gauge on 45 mm track"),
    "G24": ("1:24 (1/2 in scale)", 24.0, "Half-inch scale"),
    "G22": ("G / LGB 1:22.5", 22.5, "G scale metre gauge (LGB)"),
    "FN3": ("Fn3 1:20.3", 20.3, "Fn3, 3 ft gauge on 45 mm track; popular for logging lines"),
    "G16": ("7/8 in 1:13.7", 13.7, "7/8 inch scale (2 ft gauge on 45 mm track)"),
    "G12": ("1 in 1:12", 12.0, "One-inch scale live steam"),
    "G8": ("1.5 in 1:8", 8.0, "1-1/2 inch scale live steam"),
}
CUSTOM = "CUSTOM"


def scale_n(key: str, custom: float) -> float:
    """N in 1:N for a scale key (the custom ratio for CUSTOM)."""
    if key == CUSTOM:
        return float(custom)
    return SCALES[key][1]


def scale_label(key: str, custom: float) -> str:
    """Short text used in file names, e.g. 'HO' or '1-100'."""
    if key == CUSTOM:
        return f"1-{custom:g}"
    return key


# ---- prototype units: lengths in feet or metres, diameters in inches or cm ----

def length_to_mm(value: float, units: str) -> float:
    """A prototype length in feet ("IMPERIAL") or metres ("METRIC") as full-size mm."""
    return value * (MM_PER_FOOT if units == "IMPERIAL" else 1000.0)


def length_from_mm(mm: float, units: str) -> float:
    """Full-size mm as feet ("IMPERIAL") or metres ("METRIC")."""
    return mm / (MM_PER_FOOT if units == "IMPERIAL" else 1000.0)


def diameter_to_mm(value: float, units: str) -> float:
    """A prototype diameter in inches ("IMPERIAL") or centimetres ("METRIC") as full-size mm."""
    return value * (MM_PER_INCH if units == "IMPERIAL" else 10.0)


def diameter_from_mm(mm: float, units: str) -> float:
    """Full-size mm as inches ("IMPERIAL") or centimetres ("METRIC")."""
    return mm / (MM_PER_INCH if units == "IMPERIAL" else 10.0)


def model_to_mm(value: float, units: str) -> float:
    """A model size in inches ("IN") or millimetres ("MM") as model mm."""
    return value * MM_PER_INCH if units == "IN" else value


def model_from_mm(mm: float, units: str) -> float:
    """Model mm as inches ("IN") or millimetres ("MM")."""
    return mm / MM_PER_INCH if units == "IN" else mm


def feet_inches(mm: float) -> str:
    """Full-size mm as feet and inches, e.g. 32' 6\"; under a foot just inches."""
    inches = round(mm / MM_PER_INCH * 2) / 2
    if inches >= 12:
        feet, rest = divmod(inches, 12)
        return f"{int(feet)}' {rest:g}\"" if rest else f"{int(feet)}'"
    return f"{inches:g}\""


def doyle_board_feet(small_end_in: float, length_ft: float) -> float:
    """Board feet in a log by the Doyle log rule: (D - 4)^2 / 16 x L.

    D is the small-end diameter inside the bark in inches, L the length in
    feet. Logs 4 in or smaller come out at zero.
    """
    if small_end_in <= 4.0:
        return 0.0
    return (small_end_in - 4.0) ** 2 / 16.0 * length_ft


def scribner_board_feet(small_end_in: float, length_ft: float) -> float:
    """Board feet by the Scribner Decimal C approximation: (0.79 D^2 - 2 D - 4) x L / 16."""
    return max(0.0, (0.79 * small_end_in ** 2 - 2.0 * small_end_in - 4.0) * length_ft / 16.0)
