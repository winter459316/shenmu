"""Offline SEC1 parameter equivalence; never opens a board, socket or camera."""
import ast
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


old = load('section_reference', ROOT / 'src/host/app/section_mesh.py')
new = load('section_projection', ROOT / 'src/host/app/adaptation/section_projection.py')
builder = load('section_builder', ROOT / 'build/create_section_adapter_candidate.py')
BOUNDS = {'bounds_mm': [[-35., -10., 145.], [45., 65., 275.]]}


def compare(metadata, normal, position, flip=False):
    expected, expected_info = old.plane(metadata, list(normal), position, flip)
    actual, actual_info = new.plane(metadata, list(normal), position, flip)
    if expected.dtype != actual.dtype or expected.tobytes() != actual.tobytes():
        raise AssertionError('SEC1 packet differs')
    if expected_info != actual_info:
        raise AssertionError('Browser geometry differs')
    return actual, actual_info


class SectionTests(unittest.TestCase):
    def test_axis_oblique_and_extreme_positions(self):
        for normal in ([1, 0, 0], [0, 1, 0], [0, 0, 1], [-1, 0, 0], [1, 1, 1], [.7, -.9, .2]):
            for pos in (0, .1, 25, 50, 99.9, 100):
                for flip in (False, True):
                    with self.subTest(normal=normal, position=pos, flip=flip):
                        compare(BOUNDS, normal, pos, flip)

    def test_seeded_views_byte_exact(self):
        rng = np.random.default_rng(31415)
        for _ in range(200):
            lo = rng.uniform(-1000, 1000, 3)
            hi = lo + rng.uniform(.01, 1000, 3)
            normal = rng.normal(size=3)
            normal *= 2 / np.linalg.norm(normal)
            compare({'bounds_mm': [lo.tolist(), hi.tolist()]}, normal, rng.uniform(0, 100))

    def test_zero_extent_and_minimum_viewport(self):
        for bounds in ([[0, 0, 10], [0, 0, 10]], [[0, 0, 10], [.1, .1, 10.1]]):
            compare({'bounds_mm': bounds}, [0, 0, 1], 50)

    def test_normal_is_owned_and_repeatable(self):
        normal = np.array([1., 2., 3.])
        before = normal.tobytes()
        normal.setflags(write=False)
        first, _ = new.plane(BOUNDS, normal, 32)
        second, _ = new.plane(BOUNDS, normal, 32)
        self.assertEqual(normal.tobytes(), before)
        self.assertEqual(first.tobytes(), second.tobytes())

    def test_display_follows_returned_packet_and_units(self):
        packet, _ = new.plane(BOUNDS, [1, 2, 3], 40)
        packet[3] += np.float32(2)  # Simulate the actual returned plane offset.
        info = new.render_geometry(packet.tolist(), 40, True)
        self.assertEqual(info, old.render_geometry(packet, 40, True))
        corners_mm = np.array(info['corners_m']) * 1000
        # FP32 U/V rounding permits a small normal component. Bound that error
        # by coordinate scale, rather than incorrectly requiring exact FP64
        # orthogonality from an intentionally FP32 hardware packet.
        bound = 8 * np.finfo(np.float32).eps * np.max(abs(corners_mm))
        self.assertLess(np.max(abs(corners_mm @ packet[:3].astype(float) + packet[3])), bound)
        self.assertEqual(info['plane_m'][3], float(packet[3] * np.float32(.001)))
        self.assertTrue(np.all(packet[13:] == 0))

    def test_reject_invalid_ui_and_packet(self):
        for normal in ([0, 0, 0], [1, 2], [np.nan, 0, 1], [.1, .1, .1]):
            with self.assertRaises(ValueError): new.plane(BOUNDS, normal, 50)
        for pos in (-1, 101, np.inf, np.nan):
            with self.assertRaises(ValueError): new.plane(BOUNDS, [1, 0, 0], pos)
        for bounds in ([[1, 0, 0], [0, 1, 1]], [[np.nan]*3]*2, [[1, 2, 3]]):
            with self.assertRaises(ValueError): new.plane({'bounds_mm': bounds}, [1, 0, 0], 50)
        packet, _ = new.plane(BOUNDS, [1, 0, 0], 50)
        for bad in (packet[:15], np.zeros(16), np.full(16, np.nan)):
            with self.assertRaises(ValueError): new.render_geometry(bad, 50, False)

    def test_candidate_keeps_real_shell_and_routes_plane(self):
        baseline = ROOT / 'src/host/app/section_mesh.py'
        before = hashlib.sha256(baseline.read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory() as folder:
            path = builder.create_candidate(folder)
            trees = [ast.parse(p.read_text(encoding='utf8')) for p in (baseline, path)]
            shells = [next(n for n in t.body if isinstance(n, ast.FunctionDef) and n.name == 'shell') for t in trees]
            self.assertEqual(ast.dump(shells[0]), ast.dump(shells[1]))
            self.assertIn('from section_projection import plane, render_geometry', path.read_text(encoding='utf8'))
            with patch.dict(sys.modules, section_projection=new):
                integrated = load('integrated_section', path)
            expected, expected_info = old.plane(BOUNDS, [1, 2, 3], 40)
            actual, actual_info = integrated.plane(BOUNDS, [1, 2, 3], 40)
            self.assertEqual(actual.tobytes(), expected.tobytes())
            self.assertEqual(actual_info, expected_info)
            with self.assertRaises(FileExistsError): builder.create_candidate(folder)
        self.assertEqual(hashlib.sha256(baseline.read_bytes()).hexdigest(), before)


def saved_geometry_comparison(paths, report):
    results = []
    with tempfile.TemporaryDirectory() as folder:
        candidate = builder.create_candidate(folder)
        with patch.dict(sys.modules, section_projection=new):
            integrated = load('saved_integrated_section', candidate)
    for path in map(Path, paths):
        # The unmodified shell provides the exact metadata consumed by the UI.
        # No geometry or image is regenerated to make the comparison pass.
        triangles, baseline_extra, metadata = old.shell(path.parent, 10)
        candidate_triangles, candidate_extra, candidate_meta = integrated.shell(path.parent, 10)
        if (triangles.tobytes() != candidate_triangles.tobytes()
                or baseline_extra.tobytes() != candidate_extra.tobytes() or metadata != candidate_meta):
            raise AssertionError('Candidate shell differs')
        for normal in ([1, 0, 0], [0, 1, 0], [0, 0, 1], [1, -2, 3]):
            for position in (0, 25, 50, 75, 100):
                compare(metadata, normal, position)
        results.append(dict(geometry_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                            shell_triangles=len(triangles), plane_cases=20,
                            packet_byte_exact=True, browser_geometry_exact=True, shell_byte_exact=True))
    evidence = dict(passed=True, scope='Saved shell metadata and plane interface only; no SEC1 execution',
                    captures=results, baseline_sha256=builder.BASELINE_SHA256)
    Path(report).write_text(json.dumps(evidence, indent=2), encoding='utf8')
    return evidence


if __name__ == '__main__':
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--geometry', type=Path, action='append')
    parser.add_argument('--report', type=Path)
    args, remaining = parser.parse_known_args()
    if args.geometry or args.report:
        if not args.geometry or not args.report:
            parser.error('--geometry and --report must be supplied together')
        print(json.dumps(saved_geometry_comparison(args.geometry, args.report), indent=2))
    else:
        unittest.main(argv=[sys.argv[0], *remaining])
