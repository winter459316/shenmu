"""Finite saved-photo/map and key-cycle regression checks; no shutter."""
import hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
deps=ROOT.parents[1]/'experiments/usb_camera_20261016/deps'
if deps.exists():sys.path.insert(0,str(deps))
from preview_rectify import PreviewRectifier,MODES,np,cv2

def run(photo):
    rect=PreviewRectifier()
    with np.load(str(photo),allow_pickle=False) as z:
        raw=z['frame_bgr']; expected=np.concatenate([z['rectified_left'],z['rectified_right']],axis=1)
    before=raw.tobytes();got=rect.rectified_grid(raw)
    assert raw.tobytes()==before,'Preview mutated photo input'
    assert got.tobytes()==expected.tobytes(),'Preview differs from saved PL rectification'
    # Exercise key behavior directly without importing Linux I/O on Windows.
    import ast
    tree=ast.parse((ROOT/'physical_keys.py').read_text())
    nodes=[n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Actions']
    import time
    scope={'time':time,'MODES':MODES,'KEYS':{103:'ps_key1',108:'ps_key2',105:'pl_key1',106:'pl_key2'}}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'key_actions','exec'),scope)
    state={'mode':'color','source':'preview'};calls=[]
    def request(path,body=None):
        calls.append((path,body))
        if path=='/hdmi/status':return {'enabled':True,'source':state['source']}
        if path=='/status':return {'mode':state['mode']}
        if path=='/preview/mode':state['mode']=body['mode'];return {}
        if path=='/hdmi/preview':state['source']='preview';return {}
        raise AssertionError('Unexpected request '+path)
    action=scope['Actions'](request,True);cycle=[]
    for unused in MODES:
        action.event(1,105,1);cycle.append(state['mode'])
        action.event(1,105,2);action.event(1,105,1)
        assert state['mode']==cycle[-1]
        action.event(1,105,0)
    assert cycle==list(MODES[1:]+MODES[:1])
    state['source']='3d_cast';action.event(1,105,1)
    assert state=={'mode':'color','source':'preview'}
    assert not any(path=='/stereo/capture' for path,_ in calls)
    return {'passed':True,'saved_PL_pixels_byte_exact':True,'input_preserved':True,'key_cycle':cycle,'return_from_3d':True,'no_shutter':True,'photo_sha256':hashlib.sha256(Path(photo).read_bytes()).hexdigest()}

if __name__=='__main__':
    result=run(sys.argv[1]);print(json.dumps(result));(ROOT/'rectified_preview_verified.json').write_text(json.dumps(result,indent=2))
