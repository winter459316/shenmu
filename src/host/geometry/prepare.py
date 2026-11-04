from pathlib import Path
import hashlib,json,shutil,numpy as np
R=Path(__file__).resolve().parent
project=R.parents[1]
stable=project/'candidates/usb_320_lowlatency'
job=json.loads((stable/'live_latest.json').read_text())['job_id']
src=stable/'live_captures'/job
out=R/'input';out.mkdir(exist_ok=True)
for name in ['board_result.npz','report.json','received.json']:
    shutil.copy2(src/name,out/name)
shutil.copy2(stable/'stereo_parameters.json',out/'stereo_parameters.json')
shutil.copy2(stable/'pointcloud_viewer.html',R/'viewer_template.html')
shutil.copy2(stable/'viewer_export.py',R/'viewer_export.py')
shutil.copy2(stable/'mesh_limits.py',R/'mesh_limits.py')
manifest={}
for folder in ['usb_320_lowlatency','usb_320_hdmifps']:
    for p in (project/'candidates'/folder).iterdir():
        if p.is_file() and p.suffix in ['.py','.html','.so','.bin','.hpp']:
            manifest[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
manifest[str(src/'board_result.npz')]=hashlib.sha256((src/'board_result.npz').read_bytes()).hexdigest()
(R/'preserved_sha256.json').write_text(json.dumps(manifest,indent=2))
a=np.load(out/'board_result.npz');m=json.loads(a['metadata_json'].tobytes())
info={'job_id':job,'source':str(src),'input_size_wh':[320,360],'Q':a['Q'].tolist(),'metadata':m,
      'input_sha256':{k:hashlib.sha256(a[k].tobytes()).hexdigest() for k in ['rectified_left','rectified_right']}}
(out/'input_manifest.json').write_text(json.dumps(info,indent=2))
print('Preserved',len(manifest),'files; selected',job)
print('metadata timing', {k:v for k,v in m.items() if 'second' in k or 'tim' in k})
