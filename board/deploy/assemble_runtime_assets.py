"""Reassemble published runtime assets using their ordered SHA256 inventory."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import tempfile


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def assemble(parts_directory, output):
    parts_directory = Path(parts_directory).resolve()
    output = Path(output).resolve()
    spec = json.loads((parts_directory / 'asset_parts.json').read_text(encoding='utf-8'))
    rows = spec['parts']
    if not rows or len({row['file'] for row in rows}) != len(rows):
        raise ValueError('Part inventory must be nonempty and unique')
    if output.exists():
        if output.stat().st_size == spec['bytes'] and digest(output) == spec['sha256']:
            return output
        raise FileExistsError('Existing asset cache differs; preserve it and select a new output path')
    for row in rows:
        if not re.fullmatch(r'runtime_assets\.part[0-9]{3}', row['file']):
            raise ValueError('Invalid part filename')
        part = parts_directory / row['file']
        if not part.is_file():
            raise FileNotFoundError('Missing asset part: ' + row['file'])
        if part.stat().st_size != row['bytes'] or digest(part) != row['sha256']:
            raise ValueError('Asset part verification failed: ' + row['file'])
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix='assets_', suffix='.partial', dir=output.parent, delete=False) as f:
        partial = Path(f.name)
        for row in rows:
            with (parts_directory / row['file']).open('rb') as source:
                for block in iter(lambda: source.read(1024 * 1024), b''):
                    f.write(block)
    if partial.stat().st_size != spec['bytes'] or digest(partial) != spec['sha256']:
        raise ValueError('Reassembled archive failed verification; partial file retained: ' + str(partial))
    if output.exists():
        raise FileExistsError('Output appeared during assembly; partial file retained: ' + str(partial))
    os.rename(partial, output)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parts-directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print('Runtime assets ready:', assemble(args.parts_directory, args.output))


if __name__ == '__main__':
    main()
