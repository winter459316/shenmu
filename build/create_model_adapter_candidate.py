"""Build a reviewable candidate from the qualified source; never deploy it."""
from pathlib import Path
import argparse
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
BASELINE_SHA256 = "5cb1f3453ac90af7748f57bec7dfbff05340fbff287b84ced19ed4445747460d"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def create_candidate(output, baseline=None):
    baseline = Path(baseline or ROOT / "src/ps/inference/v5/infer_runtime_pl3_v5_quad.py")
    if digest(baseline) != BASELINE_SHA256:
        raise ValueError("Baseline differs from reviewed v5 source; review integration first")
    helper = ROOT / "src/ps/inference/adaptation/stereo_contract.py"
    source = baseline.read_text(encoding="utf8")
    start = source.index("  mean=np.array(")
    end = source.index("  preparation_seconds=", start)
    original_preparation = source[start:end]
    source = source[:start] + "  feed=prepare_inputs(a)\n" + source[end:]
    source = source.replace("import numpy as np,onnxruntime as ort\n",
                            "import numpy as np,onnxruntime as ort\n"
                            "from stereo_contract import prepare_inputs,validate_prediction,validate_geometry\n", 1)
    source = source.replace("  assert d.shape==(360,320) and np.isfinite(d).all()",
                            "  validate_prediction(d)", 1)
    source = source.replace("   xyz,valid,depth,detail=project(d,a['Q'],a['domain'])",
                            "   validate_geometry(d,a['Q'],a['domain'])\n"
                            "   xyz,valid,depth,detail=project(d,a['Q'],a['domain'])", 1)
    assert source.count("feed=prepare_inputs(a)") == 1
    assert source.count("validate_geometry(d,a['Q'],a['domain'])") == 1
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    targets = (output / "candidate_runtime.py", output / helper.name, output / "candidate_manifest.json")
    if any(p.exists() for p in targets):
        raise FileExistsError("Candidate files already exist; choose a new output directory")
    targets[0].write_text(source, encoding="utf8")
    targets[1].write_bytes(helper.read_bytes())
    manifest = {
        "status": "offline_candidate_not_promoted",
        "baseline_sha256": BASELINE_SHA256,
        "candidate_sha256": digest(targets[0]),
        "helper_sha256": digest(targets[1]),
        "changed_scope": ["input tensor construction", "prediction and geometry handoff validation"],
        "unchanged_scope": ["network graph and weights", "ONNX execution", "PL2/PL3 scheduling",
                            "DMA", "PL projection arithmetic", "result archive fields"],
        "baseline_preparation": original_preparation,
        "deployment": "No startup entry, qualification manifest or live runtime was modified",
    }
    targets[2].write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf8")
    return targets[0]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--baseline", type=Path)
    args = parser.parse_args()
    print(create_candidate(args.output, args.baseline))
