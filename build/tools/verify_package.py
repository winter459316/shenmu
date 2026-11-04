"""Offline source/asset completeness checks; no vendor tools or board access."""
from pathlib import Path
import argparse
import hashlib
import json
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[2]
NS={'s':'http://www.spiritconsortium.org/XMLSchema/SPIRIT/1685-2009'}


def main():
    hardware=ROOT/'src/pl'
    references=0
    for component in hardware.rglob('component.xml'):
        for name in ET.parse(component).findall('.//s:file/s:name',NS):
            target=(component.parent/name.text).resolve()
            assert target.is_relative_to(hardware.resolve()),'External IP file: '+name.text
            assert target.is_file(),'Missing IP file: '+str(target)
            references+=1
    provenance=json.loads((hardware/'legacy_source_provenance.json').read_text(encoding='utf8'))
    for item in provenance:
        assert hashlib.sha256((hardware/item['packaged']).read_bytes()).hexdigest()==item['sha256'],item['packaged']
    for mode in ('pl1','pl2','pl3'):
        spec=json.loads((hardware/mode/'sources.json').read_text(encoding='utf8'))
        assert spec['part']=='xczu4ev-sfvc784-2-i'
        assert (hardware/mode/'bd/system.bd').is_file()
        for item in spec['files']:assert (hardware/mode/item['path']).is_file()
    source_map=json.loads((ROOT/'board/config/source_map.json').read_text(encoding='utf8'))
    for item in source_map:
        assert hashlib.sha256((ROOT/item['source']).read_bytes()).hexdigest()==item['sha256'],item['source']
    required=('numpy-2.2.6-cp312-cp312-win_amd64.whl','opencv_python_headless-5.0.0.93-cp37-abi3-win_amd64.whl')
    for name in required:assert (ROOT.parent/'private_runtime/wheels'/name).is_file(),name
    evidence=dict(passed=True,scope='Offline file completeness, not Vivado 2026.1 validation',
                  hardware_profiles=3,ip_file_references=references,hardware_files_verified=len(provenance),
                  mapped_runtime_sources_verified=len(source_map),hardware_build_deferred=False)
    (ROOT/'sim/results').mkdir(exist_ok=True)
    (ROOT/'sim/results/package_completeness.json').write_text(json.dumps(evidence,indent=2),encoding='utf8')
    print(json.dumps(evidence,indent=2))


if __name__=='__main__':main()
