"""Resident mixed-precision model; each PL block releases its DMA mapping and lock."""
from pathlib import Path
import ctypes,hashlib,json,os,re,resource,sys,time
R=Path(__file__).resolve().parent
from pl3_execute_v5_quad import configuration,execute,H as PL3_ROOT
os.environ.update(OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='4',FAST_PL_ENABLE='1')
resource.setrlimit(resource.RLIMIT_AS,(1250*1024**2,1250*1024**2))
sys.path.insert(0,str(R.parent/'fast_board/deps'));sys.path.insert(0,str(R.parent/'usb320_hdmifps'))
import numpy as np,onnxruntime as ort
from board_dma import reservation
ort.disable_telemetry_events()
class Runtime:
 def __init__(self):
  self.transport_enabled=json.loads((R/'transport_config.json').read_text())['enabled']
  os.environ['FAST_PL_PARALLEL_COPY']='1' if self.transport_enabled else '0'
  self.layout_enabled=json.loads((R/'layout_config.json').read_text())['enabled']
  self.inference_optimized=json.loads((R/'inference_config.json').read_text())['enabled']
  self.pending=None
  self.speed_enabled=json.loads((R/'speed_config.json').read_text())['enabled']
  self.model_name='fast_speed.onnx' if self.speed_enabled else 'fast_sample.onnx' if self.inference_optimized else ('fast_layout.onnx' if self.layout_enabled else 'fast_pl.onnx')
  assert self.speed_enabled and self.transport_enabled and self.inference_optimized
  self.pl3_manifest=configuration()
  self.model_name=str(PL3_ROOT/'fast_pl3_hook_full_20261028.onnx')
  self.model_sha=hashlib.sha256((R/self.model_name).read_bytes()).hexdigest()
  self.lib_sha=hashlib.sha256((R/'libfast_pl.so').read_bytes()).hexdigest()
  so=ort.SessionOptions();so.intra_op_num_threads=4;so.inter_op_num_threads=1
  so.enable_cpu_mem_arena=False;so.enable_mem_pattern=False;so.graph_optimization_level=ort.GraphOptimizationLevel.ORT_ENABLE_EXTENDED
  so.register_custom_ops_library(str(R/'libfast_pl.so'))
  so.register_custom_ops_library(str(R/'libfast_sample.so'))
  if self.speed_enabled:so.register_custom_ops_library(str(R/'libfast_layout.so'))
  so.register_custom_ops_library(str(PL3_ROOT/'libfastpl3_hook_20261028.so'))
  start=time.monotonic();self.session=ort.InferenceSession(str(R/self.model_name),so,providers=['CPUExecutionProvider']);self.initial_load=time.monotonic()-start
  self.lib=ctypes.CDLL(str(R/'libfast_pl.so'));self.completed=0
  from geometry_preview import prime
  prime()
  # Load image libraries once, outside the per-photo wait. Calibration/maps
  # are still hash-checked and PL-vs-CPU parity is still tested on every photo.
  import cv2
  from usb_full_engine import FullEngine
  from preview_rectify import PreviewRectifier
  from fast_capture_board import rectify
  self.rectify_function=rectify
  from fallback_runtime import install
  self.fallback_callback,self.fallback_sessions=install(self.lib,R)
 def rectify(self,job):
  assert re.fullmatch('[0-9a-f]{32}',job)
  F=R/'jobs'/job
  state=json.loads((F/'status.json').read_text())
  assert state['busy'] and state['stage']=='rectification'
  assert json.loads((R/'configuration_state.json').read_text())['new']
  proof=json.loads((R/'hardware_verified.json').read_text())
  loaded=json.loads((R/'loaded.json').read_text())
  assert loaded['state']=='operating' and loaded['sha256']==proof['sha256']
  assert json.loads((R.parent/'usb320_hdmifps/loaded.json').read_text())['state']=='suspended'
  result=self.rectify_function(F)
  result['resident_worker']=True
  return result
 def run(self,job):
  assert re.fullmatch('[0-9a-f]{32}',job)
  F=R/'jobs'/job;reservation()
  assert self.pending is None,'An unfinished coordinate stage needs inspection'
  assert not (R/'dma.fault').exists() and not (R.parent/'fast_pl/dma.fault').exists()
  proof=json.loads((R/'hardware_verified.json').read_text())
  assert self.model_sha==self.pl3_manifest['files']['fast_pl3_hook_full_20261028.onnx'] and self.lib_sha==proof['sources']['libfast_pl.so'],'Restart the model worker after updating its artifacts'
  assert json.loads((R/'configuration_state.json').read_text())['new'] is True
  loaded=json.loads((R/'loaded.json').read_text());assert loaded['state']=='operating' and loaded['sha256']==proof['sha256']
  assert json.loads((R.parent/'usb320_hdmifps/loaded.json').read_text())['state']=='suspended'
  prepare_started=time.monotonic()
  with np.load(str(F/'rectified.npz'),allow_pickle=False) as z:a={n:z[n] for n in z.files}
  mean=np.array([.485,.456,.406],np.float32)[None,:,None,None];std=np.array([.229,.224,.225],np.float32)[None,:,None,None]
  feed={}
  for side in ('left','right'):
      image=np.pad(a['rectified_'+side][...,::-1].transpose(2,0,1)[None].astype(np.float32),((0,0),(0,0),(12,12),(0,0)),mode='edge')
      feed[side+'_image']=np.ascontiguousarray((image/255-mean)/std)
  preparation_seconds=time.monotonic()-prepare_started
  print('FAST_PS_PL_INFERENCE',job,flush=True)
  self.lib.mixed_reset_stats()
  d,elapsed,pl3_detail=execute(self,job,feed)
  assert d.shape==(360,320) and np.isfinite(d).all()
  v=(ctypes.c_double*4)();self.lib.fast_pl_stats(v);assert int(v[3])==2,list(v)
  cv=(ctypes.c_double*4)();self.lib.fast_conv_stats(cv)
  mv=(ctypes.c_double*4)();self.lib.mixed_stats(mv)
  assert 0<=int(cv[3])<=5 and int(cv[3])==int(mv[3]),(list(cv),list(mv))
  assert 0<=int(mv[2])<=2
  if not int(mv[2]):assert int(cv[3])==5 and mv[0]==0 and mv[1]==0
  report=dict(job_id=job,backend='Fast-FoundationStereo: A53 + PL INT16/INT48 convolution blocks plus two FP32 ConvTranspose3D nodes; three further Conv3D nodes PL3 exact FP32; other network operations A53 FP32',rectification='PL fixed-point calibrated maps; exact preview parity checked',geometry='PL FGP1 FP64 Q projection, FP32 XYZ mm',input_wh=[320,360],iterations=2,max_disparity=192,threads=4,arithmetic='INT16 x INT16 / INT48 accumulation in two PL blocks; FP32 elsewhere',load_seconds=0.0,model_resident=True,model_initial_load_seconds=self.initial_load,worker_completed_before=self.completed,forward_seconds=elapsed,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,pl=dict(copyin_seconds=v[0],device_seconds=v[1],copyout_seconds=v[2],calls=int(v[3])),conv_pl=dict(copyin_seconds=cv[0],device_seconds=cv[1],copyout_seconds=cv[2],calls=int(cv[3])),hole_filling=False)
  report.update(pl3=pl3_detail, pl3_nodes=[827,830,831], automatic_pl2_pl3=True)
  report.update(input_preparation_seconds=preparation_seconds,geometry_pending=True,transpose_accelerated=self.speed_enabled)
  report.update(inference_optimized=self.inference_optimized,sampling_backend="A53 four-way exact FP32 Sample1D" if self.inference_optimized else "ORT GridSample",transport_optimized=self.transport_enabled,layout_optimized=self.layout_enabled,layout_model_sha256=self.model_sha,layout_operation='FP32 bit-preserving matrix transpose; shared by both iterations',mixed_blocks=2, mixed_pl=dict(initial_clipped=int(mv[0]), intermediate_clipped=int(mv[1]), fp32_fallback_blocks=int(mv[2]), integer_stage_calls=int(mv[3])))
  report.update(hardware_profile='fast_infer2_v1',hardware_sha256=proof['sha256'],removed_blocks=proof['removed_blocks'])
  self.pending=(job,a,d,report)
  (F/'inference.json').write_text(json.dumps(report,indent=2))
  return report
 def finish_geometry(self,job):
  assert self.pending is not None and self.pending[0]==job
  _,a,d,report=self.pending;F=R/'jobs'/job
  try:
   from geometry_preview import project
   xyz,valid,depth,detail=project(d,a['Q'],a['domain'])
  finally:self.pending=None
  report.update(geometry_pending=False,geometry_seconds=detail['total_seconds'],geometry_pl=detail,valid_pixels=int(valid.sum()))
  a.update(disparity=d,xyz_mm=xyz,depth_mm=depth,valid=valid)
  # Preserve every array byte; avoid single-core DEFLATE after neural inference.
  report['result_encoding']='NPZ ZIP_STORED; lossless array bytes'
  a['metadata_json']=np.frombuffer(json.dumps(report).encode(),np.uint8)
  archive_start=time.monotonic();np.savez(str(F/'result.npz'),**a)
  report['archive_seconds']=time.monotonic()-archive_start
  (F/'inference.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
  self.completed+=1
  return report
