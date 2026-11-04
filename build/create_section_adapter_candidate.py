"""Generate an isolated section interface candidate; no deployment or network IO."""
import argparse
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE_SHA256 = 'de75767e2447c25a110300746a831404957c9f744c36574411ce119b0def94ed'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def create_candidate(output, baseline=None):
    baseline = Path(baseline or ROOT / 'src/host/app/section_mesh.py')
    if digest(baseline) != BASELINE_SHA256:
        raise ValueError('Section baseline differs from reviewed source')
    source = baseline.read_text(encoding='utf8')
    tree = ast.parse(source)
    functions = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    # Keep the complete shell implementation byte-for-byte, replacing only the
    # two public plane functions with the separately reviewable implementation.
    start = functions['plane'].lineno - 1
    if set(functions) != {'shell', 'plane', 'render_geometry'}:
        raise ValueError('Unexpected section integration layout')
    candidate = ''.join(source.splitlines(keepends=True)[:start])
    candidate += 'from section_projection import plane, render_geometry\n'
    helper = ROOT / 'src/host/app/adaptation/section_projection.py'
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    targets = [output / name for name in ('section_mesh.py', helper.name, 'candidate_manifest.json')]
    if any(path.exists() for path in targets):
        raise FileExistsError('Use a new candidate directory')
    targets[0].write_text(candidate, encoding='utf8')
    targets[1].write_bytes(helper.read_bytes())
    targets[2].write_text(json.dumps(dict(
        status='offline_candidate_not_promoted', baseline_sha256=BASELINE_SHA256,
        candidate_sha256=digest(targets[0]), helper_sha256=digest(targets[1]),
        changed_scope=['UI plane mapping', 'SEC1 FP32 packet', 'browser projection geometry',
                       'reject malformed parameters', 'preserve caller normal array'],
        unchanged_scope=['measured coordinates', 'shell topology and extrusion', 'SEC1 hardware',
                         'session transport', 'startup and stable runtime']), indent=2), encoding='utf8')
    return targets[0]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(create_candidate(args.output))
