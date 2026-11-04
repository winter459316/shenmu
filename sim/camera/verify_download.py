"""PC recheck of actual returned PL buffers; separate from the board assertions."""
from evaluate_reference import HERE,np
import hashlib,json
case=np.load(HERE/'hardware_case.npz');actual=np.load(HERE/'board_evidence/hardware_result.npz')
for key in ('rect0','rect1','q','score','margin','rq','rscore','rmargin','valid'):
    assert np.array_equal(actual[key],case[key]),key
y,x=np.indices(actual['q'].shape);q=actual['Q'];disp=actual['q'].astype(float)/16
ideal=np.stack((x,y,disp,np.ones(disp.shape)),axis=-1)@q.T
xyz=ideal[:,:,:3]/np.where(ideal[:,:,3:4]!=0,ideal[:,:,3:4],1)
valid=actual['valid'].astype(bool);error=np.max(abs(actual['xyz_q12'][valid]/4096-xyz[valid]),axis=0)
assert np.max(error)<.00025
selection=valid&(abs(actual['xyz_q12'][:,:,2].astype(np.int64)-1000*4096)<=20*4096)
assert np.array_equal((actual['flags']&2)!=0,selection)
result={'passed':True,'returned_file_sha256':hashlib.sha256((HERE/'board_evidence/hardware_result.npz').read_bytes()).hexdigest(),
        'all_six_matching_arrays_exact':True,'both_rgb_images_exact':True,'xyz_max_error_mm_per_axis':error.tolist(),
        'section_exact':True,'valid_pixels':int(valid.sum()),'valid_fraction':float(valid.mean()),
        'limit':'One saved scene, fixed-photo kernel test. Live runtime, completion and interactive rendering still pending.'}
(HERE/'board_evidence/pc_verified.json').write_text(json.dumps(result,indent=2),'utf8');print(json.dumps(result,indent=2))
