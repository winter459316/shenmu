"""Read-only local binding and live endpoint checks. Never starts a service."""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import urllib.request

P = Path(__file__).resolve().parents[1]
R = P / 'candidates/usb_fast_infer2'
S = P / 'candidates/usb_320_hdmifps'
E = P / 'experiments/geometry_fast_20261024'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def local_checks():
    proof = json.loads((R / 'hardware_verified.json').read_text(encoding='utf8'))
    expected = dict(proof['sources'])
    expected['fast_pl.bit.bin'] = proof['sha256']
    checks = {str((R / n).relative_to(P)): (R / n).is_file() and sha(R / n) == h
              for n, h in expected.items()}
    promotion = json.loads((E / 'promotion_verified.json').read_text(encoding='utf8'))
    for n, h in promotion['after'].items():
        checks[n] = (P / n).is_file() and sha(P / n) == h
    filters = json.loads((S / 'filters_verified.json').read_text(encoding='utf8'))
    checks['preview_bit_binding'] = sha(S / 'usb320.bit.bin') == filters['sha256']
    checks['filters_qualified'] = bool(filters['qualified'] and filters['timing_passed']
                                     and filters['combinational_loops'] == 0)
    preview = json.loads((S / 'preview_verified.json').read_text(encoding='utf8'))
    checks['preview_processing_qualified'] = bool(preview['qualified'] and preview['timing_passed'] and preview['combinational_loops'] == 0 and preview['sha256'] == sha(S / 'usb320.bit.bin'))
    section=json.loads((R/'section_payload/section_config.json').read_text())
    checks['section_bit_binding']=sha(R/'section_payload/section_preview.bit.bin')==section['sha256']
    checks['section_qualified']=bool(section['qualified'] and section['timing_passed'] and section['cdc_review_passed'])
    geometry=json.loads((R/'geometry_config.json').read_text())
    checks['geometry_bit_binding']=geometry['qualified'] and geometry['sha256']==sha(S/'usb320.bit.bin')
    checks['geometry_control_binding']=geometry['control']==0xA10C0000 and geometry['memory_base']==0x67000000
    return dict(passed=all(checks.values()), checks=checks)


def live_checks():
    op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    endpoints = {
        'pc': 'http://127.0.0.1:8849/api/status',
        'model': 'http://192.168.137.2:8850/health',
        'camera': 'http://192.168.137.2:8788/status',
        'hdmi': 'http://192.168.137.2:8788/hdmi/status',
        'section': 'http://192.168.137.2:8852/status',
    }
    result = {}
    for name, url in endpoints.items():
        try:
            with op.open(url, timeout=3) as response:
                data = json.load(response)
            # Keep a compact public status; no environment, tokens or private snapshots.
            keys = ('busy', 'stage', 'error', 'job_id', 'ready', 'version', 'mode',
                    'age_seconds', 'preview_error', 'jpeg_error', 'fps', 'frames', 'enabled', 'filter_backend','active','switching','backend')
            result[name] = dict(reachable=True, url=url,
                                status={k: data[k] for k in keys if k in data})
            if name == 'model':
                result[name]['worker_state'] = data.get('model_worker', {}).get('state')
        except Exception as exc:
            result[name] = dict(reachable=False, url=url, error=str(exc))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--output', type=Path, help='Optional local JSON evidence file')
    args = parser.parse_args()
    result = dict(checked_at=datetime.datetime.now().astimezone().isoformat(),
                  local=local_checks(), changes_to_board=False)
    if not args.offline:
        result['live'] = live_checks()
    text = json.dumps(result, indent=2, ensure_ascii=False)
    print(text)
    if args.output:
        args.output.write_text(text + '\n', encoding='utf8')
    if not result['local']['passed']:
        raise SystemExit('Binding changed: inspect differences before deployment.')


if __name__ == '__main__':
    main()
