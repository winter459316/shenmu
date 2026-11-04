"""Finite, offline comparison. No camera or board access."""
import os
os.environ['TORCHDYNAMO_DISABLE']='1'  # Windows eager execution, identical operators.
from pathlib import Path
import sys,json,time,hashlib,argparse
import numpy as np
import torch
import torch.nn.functional as F
import cv2,yaml
R=Path(__file__).resolve().parent
os.environ['HF_HOME']=str(R/'cache/huggingface')
os.environ['TORCH_HOME']=str(R/'cache/torch')
p=argparse.ArgumentParser();p.add_argument('model',choices=['light','fast']);args=p.parse_args()
torch.set_num_threads(4);torch.manual_seed(0)
torch.backends.cudnn.benchmark=False
torch.backends.cuda.matmul.allow_tf32=False
torch.backends.cudnn.allow_tf32=False
a=np.load(R/'input/board_result.npz')
for k in ['left','right']:cv2.imwrite(str(R/f'input/{k}.png'),a[f'rectified_{k}'])
imgs=[torch.from_numpy(a['rectified_'+k][...,::-1].copy()).permute(2,0,1)[None].float() for k in ['left','right']]
start=time.perf_counter()
if args.model=='light':
    sys.path.insert(0,str(R/'OpenStereo'))
    sys.path.insert(0,str(R/'light_deps'))
    # Import the official inference modules without importing every training model.
    import types
    package=types.ModuleType('stereo.modeling')
    package.__path__=[str(R/'OpenStereo/stereo/modeling')]
    sys.modules['stereo.modeling']=package
    import timm
    # Entire stereo state is loaded strictly below; skip redundant ImageNet download.
    orig=timm.create_model
    def create(*a,**kw):kw['pretrained']=False;return orig(*a,**kw)
    timm.create_model=create
    from stereo.modeling.models.lightstereo.lightstereo import LightStereo
    class Config(dict):
        __getattr__=dict.__getitem__
    cfg=Config(yaml.safe_load((R/'OpenStereo/cfgs/lightstereo/lightstereo_s_sceneflow.yaml').read_text())['MODEL'])
    model=LightStereo(cfg)
    checkpoint=R/'weights/LightStereo-S-SceneFlow.ckpt'
    state=torch.load(checkpoint,map_location='cpu',weights_only=True)
    print('checkpoint keys',list(state)[:10],flush=True)
    if 'model_state' in state:state=state['model_state']
    elif 'state_dict' in state:state=state['state_dict']
    model.load_state_dict(state,strict=True)
    model=model.cuda().eval()
    def prepare():
        mean=torch.tensor([.485,.456,.406],device='cuda')[None,:,None,None]
        std=torch.tensor([.229,.224,.225],device='cuda')[None,:,None,None]
        return [F.pad((im.cuda()/255-mean)/std,(0,0,24,0),mode='replicate') for im in imgs]
    def forward(x):return model({'left':x[0],'right':x[1]})['disp_pred'][...,24:,:]
    precision='FP32';max_disp=192;iterations=None;pad=[0,0,24,0]
else:
    sys.path.insert(0,str(R/'Fast-FoundationStereo'))
    import core.foundation_stereo
    from core.utils.utils import InputPadder
    checkpoint=R/'weights/model_best_bp2_serialize.pth'
    model=torch.load(checkpoint,map_location='cpu',weights_only=False)
    model.args.valid_iters=8;model.args.max_disp=192
    model=model.cuda().eval()
    padder=InputPadder(imgs[0].shape,divis_by=32,force_square=False)
    def prepare():return padder.pad(*[im.cuda() for im in imgs])
    def forward(x):
        with torch.amp.autocast('cuda',dtype=torch.float16):
            d=model.forward(*x,iters=8,test_mode=True,optimize_build_volume='pytorch1')
        return padder.unpad(d.float())
    precision='FP16 autocast';max_disp=192;iterations=8;pad=padder._pad
torch.cuda.synchronize();load_seconds=time.perf_counter()-start
out=R/'results'/args.model;out.mkdir(parents=True,exist_ok=True)
with torch.inference_mode():
    x=prepare();torch.cuda.synchronize()
    t=time.perf_counter();d=forward(x);torch.cuda.synchronize();cold=time.perf_counter()-t
    pred=d.float().cpu().numpy().reshape(360,320)
    assert np.isfinite(pred).all()
    np.save(out/'disparity.npy',pred)
    # Two warmups, five bounded samples. CUDA synchronize excludes async timing error.
    for _ in range(2):forward(x)
    torch.cuda.synchronize();torch.cuda.reset_peak_memory_stats()
    timings=[];end_to_end=[]
    for _ in range(5):
        torch.cuda.synchronize();t=time.perf_counter();forward(x);torch.cuda.synchronize();timings.append(time.perf_counter()-t)
    for _ in range(3):
        torch.cuda.synchronize();t=time.perf_counter();y=forward(prepare()).float().cpu().numpy();torch.cuda.synchronize();end_to_end.append(time.perf_counter()-t)
    final=y.reshape(360,320);np.save(out/'disparity.npy',final)
report={'model':args.model,'checkpoint_sha256':hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
 'gpu':torch.cuda.get_device_name(),'torch':torch.__version__,'cuda':torch.version.cuda,'precision':precision,
 'max_disparity':max_disp,'iterations':iterations,'input_wh':[320,360],'padding_lrtb':pad,
 'model_load_seconds':load_seconds,'first_forward_seconds':cold,'warm_forward_seconds':timings,
 'transfer_preprocess_forward_download_seconds':end_to_end,'median_forward_seconds':float(np.median(timings)),
 'median_pipeline_seconds':float(np.median(end_to_end)),'peak_allocated_bytes':torch.cuda.max_memory_allocated(),
 'prediction_range': [float(final.min()),float(final.max())],
 'cold_warm_max_difference':float(np.max(np.abs(pred-final))),
 'execution':'Windows PyTorch CUDA eager; no TensorRT, no torch.compile, no board execution',
 'postprocessing':'none; no hole filling or plane correction',
 'parameters':sum(p.numel() for p in model.parameters())}
(out/'timing.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report,indent=2),flush=True)
