"""One saved photograph through the production engine, no precomputed outputs."""
import hashlib,json,time
from pathlib import Path
import numpy as np
from usb_full_engine import FullEngine
from board_dma import Arena
from board_geometry import section
ROOT=Path(__file__).resolve().parent
def main():
    with np.load(ROOT/'hardware_case.npz') as z:frame=z['frame_bgr'].copy()
    engine=FullEngine();last=[0]
    def progress(stage,details):
        if stage!='completion' or time.monotonic()-last[0]>2:
            print(stage,json.dumps(details),flush=True);last[0]=time.monotonic()
    arrays,metadata=engine.compute(frame,progress)
    valid=arrays['valid'];completed_valid=(arrays['completed_geometry_flags']&1)!=0
    y,x=np.indices(valid.shape)
    errors={}
    for prefix,qkey in (('raw','disparity_q4'),('completed','completed_disparity_q4')):
        mask=valid if prefix=='raw' else completed_valid
        v=np.stack((x,y,arrays[qkey]/16,np.ones(valid.shape)),axis=-1)@arrays['Q'].T
        ideal=v[:,:,:3]/np.where(v[:,:,3:4]!=0,v[:,:,3:4],1)
        error=float(np.max(abs(arrays[prefix+'_xyz_q12'][mask]/4096-ideal[mask])));assert error<.00025
        errors[prefix]=error
    records=np.concatenate((arrays['completed_xyz_q12'],arrays['completed_geometry_flags'][:,:,None]),axis=2).astype(np.int32)
    a=Arena(True);sections=[]
    try:
        for axis,center,width,include in ((0,0,10,False),(1,0,10,True),(2,700,40,False),(2,700,40,True)):
            s=section(a,records,axis,center,width,include)
            sections.append({'axis':axis,'center_mm':center,'thickness_mm':width,'include_inferred':include,'count':len(s['indices']),'seconds':s['board_seconds']})
    finally:a.close()
    report={'passed':True,'geometry_max_error_mm':errors,'sections':sections,'metadata':metadata}
    np.savez_compressed(ROOT/'full_pipeline_result.npz',metadata_json=np.frombuffer(json.dumps(metadata).encode(),np.uint8),**arrays)
    (ROOT/'full_pipeline_verified.json').write_text(json.dumps(report,indent=2));print('FULL_PIPELINE_PASS',json.dumps(report),flush=True)
if __name__=='__main__':main()
