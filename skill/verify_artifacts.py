"""Read-only portable checks for hashes and exact numeric-array regressions."""
from pathlib import Path
import argparse
import hashlib
import json
import sys


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def verify_manifest(root, manifest):
    root = Path(root).resolve()
    data = json.loads(Path(manifest).read_text(encoding='utf-8'))
    rows = []
    for entry in data['files']:
        p = (root / entry['path']).resolve()
        if not p.is_relative_to(root):
            raise ValueError('Manifest path escapes the supplied root')
        actual = sha256(p) if p.is_file() else None
        rows.append({'path': entry['path'], 'passed': actual == entry['sha256']})
    return {'passed': bool(rows) and all(r['passed'] for r in rows), 'files': rows}


def compare(reference, candidate, keys_file=None):
    import numpy as np
    with np.load(reference, allow_pickle=False) as ref, np.load(candidate, allow_pickle=False) as got:
        keys = json.loads(Path(keys_file).read_text(encoding='utf-8')) if keys_file else sorted(set(ref.files) | set(got.files))
        if not isinstance(keys, list) or not keys or not all(isinstance(k, str) for k in keys) or len(keys) != len(set(keys)):
            raise ValueError('Keys must be a nonempty unique list of strings')
        rows = {}
        for key in keys:
            if key not in ref.files or key not in got.files:
                rows[key] = {'passed': False, 'reason': 'missing array'}
                continue
            a, b = ref[key], got[key]
            ok = a.dtype == b.dtype and a.shape == b.shape and a.tobytes(order='C') == b.tobytes(order='C')
            rows[key] = {'passed': bool(ok), 'dtype_reference': str(a.dtype), 'dtype_candidate': str(b.dtype),
                         'shape_reference': list(a.shape), 'shape_candidate': list(b.shape)}
    return {'passed': all(r['passed'] for r in rows.values()), 'arrays': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    a = sub.add_parser('manifest')
    a.add_argument('--root', required=True)
    a.add_argument('--file', required=True)
    b = sub.add_parser('compare')
    b.add_argument('reference')
    b.add_argument('candidate')
    b.add_argument('--keys-file')
    args = parser.parse_args()
    try:
        result = verify_manifest(args.root, args.file) if args.command == 'manifest' else compare(args.reference, args.candidate, args.keys_file)
    except Exception as exc:
        result = {'passed': False, 'error': str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
