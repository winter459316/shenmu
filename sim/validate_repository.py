"""Read-only public source-tree checks; no vendor tools or board required."""
from pathlib import Path
import ast,hashlib,json,re,sys

ROOT=Path(__file__).resolve().parents[1]
def validate(root=ROOT):
    root=Path(root)
    required=('src','sim','build','board','data','skill','report')
    for name in required:assert (root/name).is_dir(),name
    files=[p for p in root.rglob('*') if p.is_file() and not any(x in p.relative_to(root).parts for x in ('.runtime','.git','__pycache__'))]
    for p in files:
        for part in p.relative_to(root).parts:
            assert part=='README.md' or re.fullmatch(r'[a-z0-9_.-]+',part),str(p)
        if p.suffix=='.py':ast.parse(p.read_text(encoding='utf-8-sig'),filename=str(p))
        assert not any(x in p.name.lower() for x in ('token.txt','password.txt','private_key')),str(p)
        assert p.stat().st_size<50*1024**2,str(p)
    mapping=json.loads((root/'board/config/source_map.json').read_text(encoding='utf8'))
    for item in mapping:
        data=(root/item['source']).read_bytes()
        assert hashlib.sha256(data).hexdigest()==item['sha256'],item['source']
    assert len({x['runtime'] for x in mapping})==len(mapping)
    print(json.dumps({'passed':True,'public_files':len(files),'mapped_runtime_sources':len(mapping)},indent=2))
if __name__=='__main__':validate()
