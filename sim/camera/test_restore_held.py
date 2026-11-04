"""Restore the actual held package without constructing a hardware runtime."""
import hashlib,json,platform,sys,tempfile,threading,types
from pathlib import Path
ROOT=Path(__file__).resolve().parent
if platform.system()=='Windows':sys.path.insert(0,str(ROOT.parents[1]/'experiments/usb_camera_20261016/deps'))
import numpy as np
import restore_held

def main():
    source=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'held_restore.npz'
    data=source.read_bytes();digest=hashlib.sha256(data).hexdigest()
    assert digest=='3026c9f32eef9d0d083e0565616ed7798a972643fd4fc964401b21be16ff0095'
    with np.load(source,allow_pickle=False) as z:
        metadata=json.loads(z['metadata_json'].tobytes())
        records=np.concatenate((z['completed_xyz_q12'],z['completed_geometry_flags'][:,:,None]),axis=2).astype(np.int32)
    with tempfile.TemporaryDirectory(prefix='usb_restore_test_') as temporary:
        restore_held.ROOT=Path(temporary)
        (restore_held.ROOT/'held_restore.npz').write_bytes(data)
        record={'job_id':metadata['job_id'],'sha256':digest,'bytes':len(data)}
        (restore_held.ROOT/'held_restore.json').write_text(json.dumps(record))
        runtime=types.SimpleNamespace(lock=threading.Lock(),busy=False,section_busy=False,job_id=None)
        restore_held.restore(runtime)
        assert runtime.package==data and runtime.result_id==metadata['job_id']
        assert runtime.held.dtype==records.dtype and runtime.held.shape==records.shape and runtime.held.tobytes()==records.tobytes()
        assert runtime.metadata['bitstream_sha256']==metadata['bitstream_sha256']
        assert runtime.stage=='ready' and runtime.metadata['restored']
        record['total_seconds']=50.628194221
        (restore_held.ROOT/'held_restore.json').write_text(json.dumps(record))
        resumed=types.SimpleNamespace(lock=threading.Lock(),busy=False,section_busy=False,job_id=None)
        restore_held.restore(resumed)
        assert resumed.metadata['total_seconds']==record['total_seconds'] and resumed.package==data
        record['sha256']='0'*64
        (restore_held.ROOT/'held_restore.json').write_text(json.dumps(record))
        try:restore_held.restore(runtime)
        except AssertionError:pass
        else:raise AssertionError('Bad digest accepted')
    print(json.dumps({'passed':True,'package_sha256':digest,'all_held_records_byte_exact':True,
                      'original_hardware_metadata_preserved':True,'bad_hash_rejected':True,'runtime_timing_restored':True,
                      'physical_hardware_used':False,'architecture':platform.machine()}))
if __name__=='__main__':main()
