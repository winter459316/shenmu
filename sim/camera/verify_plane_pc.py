"""One-time acceptance only; never called by the live photo observer."""
import hashlib,json,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[1]/'experiments/usb_camera_20261016/deps'))
import numpy as np
from receive_result import receive
from render_saved import export_result
from plane_guard import improve
def run():
    tests=[]
    for stem in ('reference','baseline'):
        data=(ROOT/'board_evidence'/(stem+'_replay.npz')).read_bytes()
        status=json.loads((ROOT/'board_evidence'/(stem+'_replay_status.json')).read_text())
        a,m,b,r=receive(data,status,status['job_id'],lambda stage:None)
        q,changed,_,_=improve(a['rectified_left'],a['completed_disparity_q4'],a['completion_origin'],a['domain'])
        assert np.array_equal(q,a['dense3d_q4'])
        assert np.all(a['dense_origin'][changed]==5)
        s=export_result(a,m,b,m['surface_preparation'],ROOT/'replay_views'/stem)
        assert s['plane_correction']['version']=='edge-supported-dominant-plane-v1'
        tests.append({'case':stem,'pc_board_q4_exact':True,'integrity_passed':r['integrity_passed'],
            'points':115200,'faces':len(a['dense3d_faces']),'corrected_marked_inferred':True})
    manifest=json.loads((ROOT/'PRESERVED_SOURCE_SHA256.json').read_text())
    assert all(hashlib.sha256((ROOT.parent/name).read_bytes()).hexdigest()==digest for name,digest in manifest.items())
    baseline=ROOT/'board_evidence/baseline_photo.npz'
    held=json.loads((ROOT/'board_evidence/baseline_public.json').read_text())['held']
    assert hashlib.sha256(baseline.read_bytes()).hexdigest()==held['sha256']
    # Preserve the exact current photo plus the stable source archives before switching.
    archive=ROOT/'previous_stable_20261017.zip'
    files=[(ROOT.parent/'usb_320_sharedpreview/shared_preview_20261017.zip','shared_preview_20261017.zip'),
           (baseline,'held_photo.npz'),(ROOT/'board_evidence/baseline_public.json','held_photo.json'),
           (ROOT/'PRESERVED_SOURCE_SHA256.json','PRESERVED_SOURCE_SHA256.json')]
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        for p,name in files:z.write(p,name)
        for p in (ROOT.parent/'usb_320_display').iterdir():
            if p.is_file() and p.suffix in ('.py','.html','.npz') :z.write(p,'pc_display/'+p.name)
    with zipfile.ZipFile(archive) as z:assert z.testzip() is None
    report={'passed':True,'cases':tests,'stable_hashes_verified':len(manifest),'previous_stable_archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}
    (ROOT/'plane_pc_verified.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
if __name__=='__main__':run()
