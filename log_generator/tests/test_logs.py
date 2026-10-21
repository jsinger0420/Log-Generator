"""Tests for the pure-Python parts: scales, species, noise, bark, log mesh, arrangements.

Run from the folder that contains the log_generator package:

    python -m unittest discover -s log_generator/tests -t .

No Blender needed (numpy only).
"""

import math
import unittest

import numpy as np

from log_generator import arrange, bark, design, logmesh, noise, scales, species


def small_spec(**kw) -> logmesh.LogSpec:
    """A quick HO log: 16 ft, 24 in, coarse mesh."""
    base = dict(scale_n=87.1, length=16 * 304.8 / 87.1, d_butt=24 * 25.4 / 87.1,
                d_top=20 * 25.4 / 87.1, around_spacing=0.3, along_spacing=0.5, seed=7)
    base.update(kw)
    return logmesh.LogSpec(**base)


class TestScales(unittest.TestCase):
    """Unit conversion, scale ratios and log rules."""

    def test_round_trips(self):
        """Converting to mm and back gives the value entered, in both unit systems."""
        for units in ("IMPERIAL", "METRIC"):
            self.assertAlmostEqual(scales.length_from_mm(scales.length_to_mm(32, units), units), 32)
            self.assertAlmostEqual(scales.diameter_from_mm(scales.diameter_to_mm(30, units), units), 30)
        self.assertAlmostEqual(scales.model_from_mm(scales.model_to_mm(2.5, "IN"), "IN"), 2.5)

    def test_common_scales_present(self):
        """The usual model railroad scales are on the menu with the right ratios."""
        for key, n in (("Z", 220), ("N", 160), ("HO", 87.1), ("OO", 76.2), ("S", 64),
                       ("O48", 48), ("G22", 22.5), ("FN3", 20.3)):
            self.assertAlmostEqual(scales.scale_n(key, 0), n)
        self.assertEqual(scales.scale_n(scales.CUSTOM, 100), 100)

    def test_doyle(self):
        """A 20 in by 16 ft log is 256 board feet by the Doyle rule."""
        self.assertAlmostEqual(scales.doyle_board_feet(20, 16), 256)
        self.assertEqual(scales.doyle_board_feet(3, 16), 0)

    def test_feet_inches(self):
        """Full-size mm shown as feet and inches."""
        self.assertEqual(scales.feet_inches(32 * 304.8), "32'")
        self.assertEqual(scales.feet_inches(30 * 25.4), "2' 6\"")


class TestSpecies(unittest.TestCase):
    """The species table is complete and sane."""

    def test_fields(self):
        """Every species has a known bark style, colours in range and sensible sizes."""
        keys = set()
        for sp in species.SPECIES:
            self.assertNotIn(sp.key, keys)
            keys.add(sp.key)
            self.assertIn(sp.style, species.STYLES)
            for c in (sp.ridge, sp.furrow, sp.inner_bark, sp.sapwood, sp.heartwood):
                self.assertTrue(all(0 <= v <= 1 for v in c))
            self.assertGreater(sp.diameter_in, 0)
            self.assertGreater(sp.length_ft, 0)
            self.assertTrue(10 <= sp.top_pct <= 100)
            self.assertLessEqual(sp.bark_depth_mm, sp.bark_thickness_mm)
        self.assertIn("DOUGLAS_FIR", keys)
        self.assertIn("RED_OAK", keys)
        self.assertGreaterEqual(len(keys), 15)


class TestNoise(unittest.TestCase):
    """Noise is deterministic, varied and in range."""

    def test_deterministic_and_seeded(self):
        """The same seed gives the same values; another seed different ones."""
        p = np.random.default_rng(1).uniform(-10, 10, (500, 3))
        a, b = noise.fbm(p, 3, 5), noise.fbm(p, 3, 5)
        self.assertTrue(np.array_equal(a, b))
        self.assertFalse(np.allclose(a, noise.fbm(p, 3, 6)))
        self.assertLess(np.abs(a).max(), 1.5)
        self.assertGreater(a.std(), 0.05)

    def test_worley(self):
        """F2 is never nearer than F1, and cell values are in [0, 1)."""
        p = np.random.default_rng(2).uniform(-5, 5, (500, 3))
        f1, f2, cell = noise.worley(p, 3)
        self.assertTrue((f2 >= f1).all())
        self.assertTrue(((cell >= 0) & (cell < 1)).all())


class TestBark(unittest.TestCase):
    """Every bark style gives heights and tones in [0, 1] with some relief."""

    def test_styles(self):
        """Each style returns values in range, with relief except the smooth barks."""
        th = np.linspace(0, 2 * np.pi, 80, endpoint=False)
        x = np.linspace(0, 2000, 80)
        T, X = np.meshgrid(th, x)
        for style in species.STYLES:
            h, tone = bark.surface(style, T.ravel(), X.ravel(), 300, 50, 3, 1, (5.0, 10.0))
            self.assertTrue(((h >= 0) & (h <= 1)).all(), style)
            self.assertTrue(((tone >= 0) & (tone <= 1)).all(), style)
            self.assertGreater(h.std(), 0.02, style)

    def test_wraps_round(self):
        """Theta = 0 and 2 pi give the same bark: no seam."""
        x = np.linspace(0, 1000, 20)
        a, _ = bark.surface("FURROWED", np.zeros(20), x, 300, 50, 3, 1)
        b, _ = bark.surface("FURROWED", np.full(20, 2 * np.pi), x, 300, 50, 3, 1)
        self.assertTrue(np.allclose(a, b, atol=1e-9))

    def test_octaves_follow_resolution(self):
        """Coarse meshes draw fewer octaves."""
        self.assertGreater(bark.octaves(0.02, 1.0, 4), bark.octaves(0.2, 1.0, 4))
        self.assertEqual(bark.octaves(10.0), 1)


class TestLogMesh(unittest.TestCase):
    """The log mesh is closed, faces outward and has the right size and shape."""

    def test_closed_and_outward(self):
        """No open edges, positive volume close to a tapered cylinder's."""
        spec = small_spec()
        m = logmesh.build(spec)
        self.assertEqual(logmesh.open_edges(m.triangles), 0)
        vol = logmesh.volume(m.vertices, m.triangles)
        r0, r1 = spec.d_butt / 2, spec.d_top / 2
        frustum = math.pi * spec.length / 3 * (r0 * r0 + r0 * r1 + r1 * r1)
        self.assertGreater(vol, 0.7 * frustum)
        self.assertLess(vol, 1.1 * frustum)

    def test_every_species_closed(self):
        """Logs of every species and flared butts are closed."""
        for sp in species.SPECIES:
            d = design.Design(species=sp.key, detail="COARSE", flare_chance=1.0,
                              max_triangles=40_000)
            spec = design.log_specs(d, 3)[0]
            m = logmesh.build(spec)
            self.assertEqual(logmesh.open_edges(m.triangles), 0, sp.key)
            self.assertGreater(logmesh.volume(m.vertices, m.triangles), 0, sp.key)

    def test_length_and_taper(self):
        """The log runs from x=0 to its length; the butt is wider than the top."""
        spec = small_spec(end_tilt_deg=0.0, end_rough=False, sweep=0.0, knots_per_m=0)
        m = logmesh.build(spec)
        v = m.vertices
        self.assertAlmostEqual(v[:, 0].min(), 0.0, places=6)
        self.assertAlmostEqual(v[:, 0].max(), spec.length, places=6)
        r = np.hypot(v[:, 1], v[:, 2])
        butt = r[v[:, 0] < 0.02 * spec.length].max()
        top = r[v[:, 0] > 0.98 * spec.length].max()
        self.assertGreater(butt, top)

    def test_flare_widens_butt(self):
        """A flared butt is wider than the same log without flare."""
        plain = logmesh.build(small_spec(flare=0.0))
        flared = logmesh.build(small_spec(flare=0.4))

        def butt_r(m):
            v = m.vertices
            return np.hypot(v[:, 1], v[:, 2])[v[:, 0] < 0.5].max()
        self.assertGreater(butt_r(flared), 1.2 * butt_r(plain))

    def test_materials_and_attributes(self):
        """Faces are bark or end grain; colours and UVs cover every vertex."""
        m = logmesh.build(small_spec())
        self.assertEqual(set(np.unique(m.material)) - {logmesh.BARK, logmesh.END_GRAIN}, set())
        self.assertIn(logmesh.END_GRAIN, m.material)
        n = len(m.vertices)
        self.assertEqual(m.colours.shape, (n, 4))
        self.assertEqual(m.uv_norm.shape, (n, 2))
        self.assertTrue(((m.colours >= 0) & (m.colours <= 1)).all())

    def test_carved_rings(self):
        """Carved rings stay closed, add end-face detail and dent the end faces inward."""
        plain = logmesh.build(small_spec(end_rough=False, end_tilt_deg=0.0))
        carved = logmesh.build(small_spec(end_rough=False, end_tilt_deg=0.0, carve_rings=True,
                                          carve_count=10, carve_depth=0.05))
        self.assertEqual(logmesh.open_edges(carved.triangles), 0)
        self.assertGreater(len(carved.triangles), len(plain.triangles))
        x = carved.vertices[:, 0]
        self.assertGreaterEqual(x.min(), -1e-9)  # grooves go into the butt, not out
        self.assertTrue(((x > 0.01) & (x < 0.06)).any())

    def test_rings_uv_counts_rings(self):
        """The Rings UV gives about the carved ring count at the bark."""
        spec = small_spec(carve_rings=True, carve_count=10)
        m = logmesh.build(spec)
        years = np.hypot(m.uv_rings[:, 0], m.uv_rings[:, 1])
        self.assertTrue(8.0 < years.max() < 13.0)

    def test_hollow(self):
        """A hollow log is two closed shells, holds the wall everywhere and weighs less."""
        solid = logmesh.build(small_spec())
        hollow = logmesh.build(small_spec(hollow=True, wall=1.0))
        self.assertTrue(hollow.info["hollow"])
        self.assertEqual(logmesh.open_edges(hollow.triangles), 0)
        v_solid = logmesh.volume(solid.vertices, solid.triangles)
        v_hollow = logmesh.volume(hollow.vertices, hollow.triangles)
        self.assertLess(v_hollow, 0.8 * v_solid)
        self.assertGreater(v_hollow, 0.0)
        k = hollow.info["cavity_vertices"]
        inner, outer = hollow.vertices[-k:], hollow.vertices[:-k]
        nearest = np.full(len(inner), np.inf)
        for i in range(0, len(outer), 2000):
            d = np.linalg.norm(inner[:, None, :] - outer[None, i:i + 2000, :], axis=2).min(axis=1)
            nearest = np.minimum(nearest, d)
        self.assertGreaterEqual(nearest.min(), 1.0 - 1e-6)

    def test_hollow_too_thin(self):
        """A log too thin for the wall stays solid and says so."""
        m = logmesh.build(small_spec(d_butt=2.0, d_top=1.8, hollow=True, wall=1.0))
        self.assertFalse(m.info["hollow"])
        self.assertIn("skipped", m.info)

    def test_seed_repeats(self):
        """The same seed builds the same log; another seed a different one."""
        a = logmesh.build(small_spec(seed=3))
        b = logmesh.build(small_spec(seed=3))
        c = logmesh.build(small_spec(seed=4))
        self.assertTrue(np.array_equal(a.vertices, b.vertices))
        self.assertFalse(a.vertices.shape == c.vertices.shape
                         and np.allclose(a.vertices, c.vertices))

    def test_triangle_budget(self):
        """Resolution stays near the triangle limit."""
        spec = small_spec(around_spacing=0.01, along_spacing=0.01, max_triangles=50_000)
        n_ar, n_al, m = logmesh.resolution(spec)
        self.assertLess(2 * n_ar * n_al, 60_000)


class TestDesign(unittest.TestCase):
    """Settings to specs: sizes, variation and errors."""

    def test_prototype_and_model_size(self):
        """A 32 ft log in HO is 112 mm; model size is used as entered."""
        d = design.Design(length_real=32 * 304.8, diameter_real=36 * 25.4, scale_n=87.1)
        self.assertAlmostEqual(d.length(), 32 * 304.8 / 87.1)
        d.size_mode, d.length_model, d.diameter_model = "MODEL", 50.0, 5.0
        self.assertEqual(d.length(), 50.0)
        spec = design.log_specs(d, 1)[0]
        self.assertAlmostEqual(spec.length, 50.0)
        self.assertAlmostEqual(spec.d_top, 5.0 * d.top_pct / 100)

    def test_variation(self):
        """Several logs vary within the limits; a single log is exact."""
        d = design.Design(arrangement="LOGS", count=20, length_var=0.1, diameter_var=0.2)
        specs = design.log_specs(d, 9)
        self.assertEqual(len(specs), 20)
        ls = [s.length for s in specs]
        self.assertLessEqual(max(ls), d.length() * 1.1 + 1e-9)
        self.assertGreaterEqual(min(ls), d.length() * 0.9 - 1e-9)
        self.assertGreater(len(set(round(v, 6) for v in ls)), 10)
        single = design.log_specs(design.Design(length_var=0.5), 9)
        self.assertEqual(len(single), 1)
        self.assertAlmostEqual(single[0].length, design.Design().length())

    def test_flare_chance(self):
        """0% flares no logs, 100% flares them all."""
        for chance, want in ((0.0, 0), (1.0, 30)):
            d = design.Design(arrangement="FLOAT", count=30, flare_chance=chance)
            self.assertEqual(sum(s.flare > 0 for s in design.log_specs(d, 2)), want)

    def test_errors(self):
        """Zero sizes are refused with a message."""
        self.assertTrue(design.errors(design.Design(length_real=0)))
        self.assertFalse(design.errors(design.Design()))

    def test_hollow_estimate(self):
        """Hollowing saves material on a big log, and is refused on a thin one."""
        m = design.summary(design.Design())
        self.assertTrue(m["hollow_ok"])
        self.assertTrue(0.2 < m["hollow_saving"] < 0.9)
        thin = design.summary(design.Design(diameter_real=4 * 25.4))
        self.assertFalse(thin["hollow_ok"])

    def test_summary(self):
        """The summary gives model sizes and a positive board-foot count."""
        m = design.summary(design.Design())
        self.assertAlmostEqual(m["length"], 32 * 304.8 / 87.1)
        self.assertGreater(m["doyle"], 0)
        self.assertGreater(m["triangles"], 0)


class TestArrange(unittest.TestCase):
    """Car loads, rows and floating."""

    def test_stack_fits_and_rests(self):
        """Bottom row within the width; upper logs touch two below; no overlaps."""
        radii = [5.0] * 10
        centres, left = arrange.stack(radii, 31.0, 4)
        self.assertEqual(len(centres), 6)  # 3 + 2 + 1
        self.assertEqual(len(left), 4)
        ys = [c[0] for c in centres.values()]
        self.assertLessEqual(max(ys) + 5, 15.5 + 1e-9)
        pts = list(centres.values())
        for a in range(len(pts)):
            for b in range(a + 1, len(pts)):
                d = math.hypot(pts[a][0] - pts[b][0], pts[a][1] - pts[b][1])
                self.assertGreaterEqual(d, 10.0 - 1e-6)

    def test_stack_overlap(self):
        """With overlap, neighbours sink into each other by about that much."""
        centres, _left = arrange.stack([5.0, 5.0], 40.0, 1, overlap=0.2)
        (y0, _), (y1, _) = centres[0], centres[1]
        self.assertAlmostEqual(abs(y1 - y0), 10.0 - 0.2)

    def test_float_depth(self):
        """Light logs ride high, heavy ones low; half density floats at the centre line."""
        self.assertAlmostEqual(arrange.float_depth(5.0, 0.5), 0.0, places=5)
        self.assertGreater(arrange.float_depth(5.0, 0.4), 0.0)
        self.assertLess(arrange.float_depth(5.0, 0.9), 0.0)
        self.assertGreater(arrange.float_depth(5.0, 2.0), -5.0)  # sinkers still show

    def test_stack_longest_at_bottom(self):
        """The longest logs go in the bottom row."""
        radii = [5.0] * 6
        lengths = [50, 90, 60, 100, 70, 80]
        centres, left = arrange.stack(radii, 31.0, 3, lengths=lengths)
        bottom = sorted(i for i, (_y, z) in centres.items() if abs(z - 5.0) < 1e-9)
        self.assertEqual(bottom, [1, 3, 5])  # 90, 100 and 80 long

    def test_row(self):
        """Logs in a row don't touch and are centred."""
        ys = arrange.row([2.0, 3.0, 4.0], 1.0)
        self.assertAlmostEqual(ys[1] - ys[0], 2.0 + 3.0 + 1.0)
        self.assertAlmostEqual(ys[2] - ys[1], 3.0 + 4.0 + 1.0)
        self.assertAlmostEqual((ys[0] - 2.0 + ys[2] + 4.0) / 2, 0.0)

    def test_above_water(self):
        """Light species float high, heavy ones low."""
        self.assertGreater(arrange.above_water(5, 0.43), arrange.above_water(5, 0.9))
        self.assertAlmostEqual(arrange.above_water(5, 0.5), 0.5, places=5)


if __name__ == "__main__":
    unittest.main()
