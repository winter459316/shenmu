"""Finite same-photo exactness/performance checks; no shutter or PL writes."""
import os
os.environ.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',USB_SURFACE_NATIVE='1')
import hashlib,json,time,multiprocessing,sys
from pathlib import Path
import numpy as np
from board_surface import prepare
from surface_cleanup import triangle_stretch
from surface_holes import repair_surface
from board_completion import CompletionCancelled
ROOT=Path(__file__).resolve().parent
def exact(actual,expected,name):
    assert actual.dtype==expected.dtype and actual.shape==expected.shape,name+' layout'
    assert actual.tobytes()==expected.tobytes(),name+' values'
def inputs(filename):
    with np.load(ROOT/filename,allow_pickle=False) as z:a={k:z[k] for k in z.files}
    return a
def main():
    report={'passed':False,'shutter_triggered':False,'tests':{}}
    held=inputs('held_restore.npz');a={k:v for k,v in held.items() if k!='metadata_json' and not k.startswith('display_')}
    expected={k[8:]:v for k,v in held.items() if k.startswith('display_')}
    if sys.argv[1]=='mesh':
        samples=[]
        for layer in ('optimized','detail','repaired'):
            xyz=expected[layer+'_xyz_mm'];faces=expected[layer+'_faces']
            os.environ['USB_MESH_NATIVE']='0';t=time.monotonic();ref=triangle_stretch(xyz,faces);old=time.monotonic()-t
            os.environ['USB_MESH_NATIVE']='1';t=time.monotonic();new=triangle_stretch(xyz,faces);seconds=time.monotonic()-t
            exact(new,ref,layer)
            samples.append({'layer':layer,'faces':len(faces),'reference_seconds':old,'native_seconds':seconds})
        report['tests']['mesh']=samples
    else:
        os.environ.update(USB_MESH_NATIVE='0',USB_HOLES_PARALLEL='0')
        if sys.argv[1]=='full':
            print('BEGIN_BASELINE_SAME_PHOTO',flush=True)
            baseline,old=prepare(a,lambda stage,details:print('baseline',stage,flush=True))
            for k,v in expected.items():exact(baseline[k],v,'reference '+k)
        else:
            prior=json.loads((ROOT/'photo_speed_full_verified.json').read_text())['tests']['surface']
            assert prior['input_sha256']==hashlib.sha256((ROOT/'held_restore.npz').read_bytes()).hexdigest()
            old={'seconds':prior['reference_seconds'],'stage_seconds':prior['reference_stages']}
        os.environ.update(USB_MESH_NATIVE='1',USB_HOLES_PARALLEL='1')
        print('BEGIN_ACCELERATED_SAME_PHOTO',flush=True)
        accelerated,new=prepare(a,lambda stage,details:print('accelerated',stage,flush=True))
        for k,v in expected.items():exact(accelerated[k],v,'accelerated '+k)
        assert set(accelerated)==set(expected)
        report['tests']['surface']={'reference_seconds':old['seconds'],'accelerated_seconds':new['seconds'],
            'reference_stages':old['stage_seconds'],'accelerated_stages':new['stage_seconds'],
            'exact_arrays':list(expected),'input_sha256':hashlib.sha256((ROOT/'held_restore.npz').read_bytes()).hexdigest()}
        # Independent saved scene, exercises different rejection/consensus decisions.
        other=inputs('full_pipeline_result.npz');saved=inputs('surface_native_result.npz')
        g={'Q_grid':other['Q'],'provenance':other['completion_origin'],
            'measured_valid':(other['completion_origin']==0)&((other['completed_geometry_flags']&1)!=0),
            'completed_q4':other['completed_disparity_q4'],'preview_valid':saved['preview_valid'],'max_disparity_px':127}
        d={'valid':saved['detail_valid'],'xyz_mm':saved['detail_xyz_mm'],'disparity_px':saved['detail_disparity_px'],'grid_faces':saved['detail_faces']}
        print('BEGIN_SECOND_SCENE_HOLES',flush=True);t=time.monotonic();out=repair_surface(g,d)
        mapping={'xyz_mm':'repaired_xyz_mm','valid':'repaired_valid','disparity_px':'repaired_disparity_px',
            'provenance':'repaired_origin','restored_inferred':'restored_inferred','grid_faces':'repaired_faces'}
        for k,v in mapping.items():exact(out[k],saved[v],'second scene '+k)
        report['tests']['second_scene']={'seconds':time.monotonic()-t,'exact_arrays':list(mapping)}
        children={p.pid for p in multiprocessing.active_children()};t=time.monotonic()
        try:repair_surface(g,d,cancel=lambda:time.monotonic()-t>.75)
        except CompletionCancelled:pass
        else:raise AssertionError('Cancellation did not propagate')
        assert {p.pid for p in multiprocessing.active_children()}==children
        report['tests']['cancel']={'seconds':time.monotonic()-t,'no_workers_left':True}
    report['passed']=True
    name='photo_speed_'+sys.argv[1]+'_verified.json'
    (ROOT/name).write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2),flush=True)
if __name__=='__main__':main()
