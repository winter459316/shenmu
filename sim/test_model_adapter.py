"""Finite offline equivalence tests; no camera, ONNX session or board is opened."""
from pathlib import Path
import ast
import contextlib
import copy
import ctypes
import hashlib
import importlib.util
import io
import json
import re
import tempfile
import time
import types
import unittest
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


adapter = load("shenmu_stereo_contract", ROOT / "src/ps/inference/adaptation/stereo_contract.py")
builder = load("shenmu_candidate_builder", ROOT / "build/create_model_adapter_candidate.py")
baseline = ROOT / "src/ps/inference/v5/infer_runtime_pl3_v5_quad.py"


def baseline_preparation():
    """Compile the actual old preparation statements, not a hand-written copy."""
    tree = ast.parse(baseline.read_text(encoding="utf8"))
    runtime = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Runtime")
    run = next(n for n in runtime.body if isinstance(n, ast.FunctionDef) and n.name == "run")
    begin = next(i for i, n in enumerate(run.body)
                 if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "mean" for t in n.targets))
    end = next(i for i, n in enumerate(run.body)
               if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "preparation_seconds" for t in n.targets))
    function = ast.FunctionDef(name="prepare", args=ast.arguments(posonlyargs=[], args=[ast.arg(arg="a")],
                              kwonlyargs=[], kw_defaults=[], defaults=[]),
                              body=run.body[begin:end] + [ast.Return(value=ast.Name(id="feed", ctx=ast.Load()))],
                              decorator_list=[])
    module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    namespace = {"np": np}
    exec(compile(module, str(baseline), "exec"), namespace)
    return namespace["prepare"]


old_prepare = baseline_preparation()


class InputTests(unittest.TestCase):
    def compare(self, left, right):
        arrays = {"rectified_left": left, "rectified_right": right}
        before = [v.tobytes() for v in arrays.values()]
        expected, actual = old_prepare(arrays), adapter.prepare_inputs(arrays)
        for key in expected:
            self.assertEqual(expected[key].dtype, actual[key].dtype)
            self.assertEqual(expected[key].shape, actual[key].shape)
            self.assertEqual(expected[key].tobytes(), actual[key].tobytes(), key)
            self.assertTrue(actual[key].flags.c_contiguous)
            self.assertTrue(actual[key].flags.owndata)
            self.assertFalse(np.shares_memory(actual[key], left))
        self.assertEqual(before, [v.tobytes() for v in arrays.values()])
        self.assertFalse(np.shares_memory(actual["left_image"], actual["right_image"]))

    def test_all_byte_values_and_edge_padding(self):
        a = (np.arange(360 * 320 * 3, dtype=np.uint32) % 256).astype(np.uint8).reshape(360, 320, 3)
        a[0] = (0, 127, 255)
        a[-1] = (255, 128, 0)
        self.compare(a, a[::-1])

    def test_seeded_distinct_and_noncontiguous_frames(self):
        rng = np.random.default_rng(20261103)
        for i in range(12):
            with self.subTest(case=i):
                a = rng.integers(0, 256, (360, 640, 3), np.uint8)
                b = rng.integers(0, 256, (360, 640, 3), np.uint8)
                self.compare(a[:, ::2], b[:, 1::2])

    def test_invalid_input_rejected_instead_of_resized(self):
        good = np.zeros((360, 320, 3), np.uint8)
        for bad in [good.astype(np.float32), good[:-1], good[:, :-1], good[..., 0], good[..., :2]]:
            with self.subTest(shape=bad.shape, dtype=bad.dtype):
                with self.assertRaises(ValueError):
                    adapter.prepare_inputs({"rectified_left": good, "rectified_right": bad})

    def test_zero_padding_profile(self):
        spec = adapter.StereoContract(width=32, height=32)
        frame = np.zeros((32, 32, 3), np.uint8)
        feed = adapter.prepare_inputs({"rectified_left": frame, "rectified_right": frame}, spec)
        self.assertEqual(feed["left_image"].shape, (1, 3, 32, 32))
        self.assertTrue(np.isfinite(feed["left_image"]).all())

    def test_geometry_checks_preserve_array_identity(self):
        d = np.ones((360, 320), np.float32)
        q = np.eye(4, dtype=np.float64)
        domain = np.ones(d.shape, np.bool_)
        result = adapter.validate_geometry(d, q, domain)
        self.assertTrue(all(a is b for a, b in zip(result, (d, q, domain))))
        for bad in [d.astype(np.float64), d[:-1], np.full(d.shape, np.nan, np.float32)]:
            with self.assertRaises(ValueError): adapter.validate_prediction(bad)
        with self.assertRaises(ValueError):adapter.validate_geometry(d, q[:3], domain)
        with self.assertRaises(ValueError):adapter.validate_geometry(d, q, domain[:-1])

    def test_candidate_integrates_real_runtime_without_requalifying_baseline(self):
        digest = hashlib.sha256(baseline.read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory() as folder:
            generated = builder.create_candidate(folder)
            tree = ast.parse(generated.read_text(encoding="utf8"))
            runtime = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Runtime")
            run = next(n for n in runtime.body if isinstance(n, ast.FunctionDef) and n.name == "run")
            feed = next(n for n in run.body if isinstance(n, ast.Assign)
                        and any(isinstance(t, ast.Name) and t.id == "feed" for t in n.targets))
            self.assertIsInstance(feed.value, ast.Call)
            self.assertEqual(feed.value.func.id, "prepare_inputs")
            self.assertIn("validate_geometry(d", generated.read_text(encoding="utf8"))
            manifest = json.loads((Path(folder) / "candidate_manifest.json").read_text(encoding="utf8"))
            self.assertEqual(manifest["status"], "offline_candidate_not_promoted")
            self.assertEqual(manifest["baseline_sha256"], digest)
            with self.assertRaises(FileExistsError):builder.create_candidate(folder)
        self.assertEqual(hashlib.sha256(baseline.read_bytes()).hexdigest(), digest)

    def test_actual_runtime_run_matches_baseline_with_hardware_stubbed(self):
        """Exercise the real run method; the PL execute function is explicitly a stub."""
        outputs = []
        with tempfile.TemporaryDirectory() as folder:
            generated = builder.create_candidate(Path(folder) / "candidate")
            image = np.arange(360 * 320 * 3, dtype=np.uint32).astype(np.uint8).reshape(360, 320, 3)
            for number, source in enumerate((baseline, generated)):
                runtime_root = Path(folder) / str(number) / "fast"
                job = "a" * 32
                job_root = runtime_root / "jobs" / job
                job_root.mkdir(parents=True)
                np.savez(job_root / "rectified.npz", rectified_left=image, rectified_right=image[::-1],
                         Q=np.eye(4), domain=np.ones((360, 320), bool))
                fixtures = {
                    runtime_root / "hardware_verified.json": {"sha256": "bit", "sources": {"libfast_pl.so": "lib"}, "removed_blocks": []},
                    runtime_root / "configuration_state.json": {"new": True},
                    runtime_root / "loaded.json": {"state": "operating", "sha256": "bit"},
                    runtime_root.parent / "usb320_hdmifps/loaded.json": {"state": "suspended"},
                }
                for target, value in fixtures.items():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(json.dumps(value), encoding="utf8")
                feeds = []

                def execute_stub(owner, request, feed):
                    feeds.append(feed)
                    return np.ones((360, 320), np.float32), 0.2, {"test_stub": True}

                def stats(out, count):
                    for i, value in enumerate((0.0, 0.0, 0.0, float(count))): out[i] = value

                owner = types.SimpleNamespace(
                    pending=None, model_sha="model", lib_sha="lib", initial_load=0.1, completed=0,
                    speed_enabled=True, inference_optimized=True, transport_enabled=True, layout_enabled=True,
                    pl3_manifest={"files": {"fast_pl3_hook_full_20261028.onnx": "model"}},
                    lib=types.SimpleNamespace(mixed_reset_stats=lambda: None,
                                             fast_pl_stats=lambda out: stats(out, 2),
                                             fast_conv_stats=lambda out: stats(out, 5),
                                             mixed_stats=lambda out: stats(out, 5)))
                parsed = ast.parse(source.read_text(encoding="utf8"))
                cls = next(n for n in parsed.body if isinstance(n, ast.ClassDef) and n.name == "Runtime")
                method = copy.deepcopy(next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "run"))
                namespace = dict(R=runtime_root, re=re, json=json, np=np, time=time, ctypes=ctypes,
                                 reservation=lambda: None, execute=execute_stub,
                                 resource=types.SimpleNamespace(RUSAGE_SELF=0,
                                     getrusage=lambda _: types.SimpleNamespace(ru_maxrss=100)),
                                 prepare_inputs=adapter.prepare_inputs, validate_prediction=adapter.validate_prediction)
                exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), str(source), "exec"), namespace)
                with contextlib.redirect_stdout(io.StringIO()):
                    report = namespace["run"](owner, job)
                self.assertTrue(report["geometry_pending"])
                self.assertEqual(owner.pending[0], job)
                self.assertEqual(len(feeds), 1)
                del report["input_preparation_seconds"]  # Deliberately measured, not deterministic.
                outputs.append((feeds[0], owner.pending[2], report))
            self.assertEqual(outputs[0][2], outputs[1][2])
            for key in outputs[0][0]:
                self.assertEqual(outputs[0][0][key].tobytes(), outputs[1][0][key].tobytes())
            self.assertEqual(outputs[0][1].tobytes(), outputs[1][1].tobytes())


def saved_capture_comparison(captures, report):
    outcomes = []
    for capture in captures:
        capture = Path(capture)
        with np.load(capture, allow_pickle=False) as archive:
            arrays = {k: archive[k] for k in ("rectified_left", "rectified_right")}
            q, domain = archive["Q"], archive["domain"]
            d = archive["disparity"]
        expected, actual = old_prepare(arrays), adapter.prepare_inputs(arrays)
        assert all(expected[k].tobytes() == actual[k].tobytes() for k in expected), str(capture)
        adapter.validate_geometry(d, q, domain)
        outcomes.append({"capture_sha256": hashlib.sha256(capture.read_bytes()).hexdigest(),
                         "feed_shape": list(actual["left_image"].shape),
                         "byte_exact": True, "geometry_contract_passed": True})
    result = {"passed": True, "captures": outcomes,
              "scope": "Input tensors and saved geometry contracts only; no new network/board execution",
              "baseline_sha256": hashlib.sha256(baseline.read_bytes()).hexdigest()}
    Path(report).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf8")
    return result


if __name__ == "__main__":
    unittest.main()
