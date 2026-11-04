"""FP32 disparity -> qualified FP64 projection in the preview/section PL image."""
from pathlib import Path
import ctypes,fcntl,hashlib,json,time
import numpy as np
from board_dma import reservation
R=Path(__file__).resolve().parent;S=R.parent/'usb320_hdmifps'
_verified_image=None

def prime():
 global _verified_image
 cfg=json.loads((R/'geometry_config.json').read_text());p=S/'usb320.bit.bin';s=p.stat()
 signature=(cfg['sha256'],s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)
 if signature!=_verified_image:
  assert hashlib.sha256(p.read_bytes()).hexdigest()==cfg['sha256']
  _verified_image=signature
 return cfg

def project(disparity,q,domain):
 started=time.monotonic();reservation()
 assert disparity.dtype==np.float32 and disparity.shape==(360,320)
 assert q.dtype==np.float64 and q.shape==(4,4) and np.isfinite(q).all()
 assert domain.dtype==bool and domain.shape==disparity.shape
 assert all(v==0 for i,v in enumerate(q.ravel()) if i not in (0,3,5,7,11,14,15))
 assert q[2,3]>0 and q[3,2]!=0
 cfg=prime()
 assert cfg['qualified'] and cfg['control']==0xA10C0000 and cfg['memory_base']==0x67000000
 assert not json.loads((R/'configuration_state.json').read_text())['new'],'Fast image still active'
 assert json.loads((S/'loaded.json').read_text())['sha256']==cfg['sha256']
 assert Path('/sys/class/fpga_manager/fpga0/state').read_text().strip()=='operating'
 assert not any((root/n).exists() for root,n in ((R,'dma.fault'),(S,'dma.fault'),(R,'geometry.dma.fault')))
 packed=np.empty((360,320,2),dtype='<u4');packed[...,0]=disparity.view('<u4');packed[...,1]=domain
 q=np.ascontiguousarray(q,dtype='<f8');words=np.empty((360,320,4),dtype='<u4');timing=np.zeros(3,np.float64)
 packing=time.monotonic()-started
 lib=ctypes.CDLL(str(R/'geometry_dma.so'))
 lib.geometry_run.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p]
 for n in ('geometry_open','geometry_identity','geometry_idle','geometry_close'):getattr(lib,n).restype=ctypes.c_int
 lib.geometry_run.restype=ctypes.c_int
 with (R/'geometry.lock').open('a+') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  assert lib.geometry_open()==0,'Cannot map geometry reservation'
  try:
   identity=lib.geometry_identity()
   if identity==-110:
    (R/'geometry.dma.fault').write_text('Geometry identity timeout: keep frozen')
    (R/'dma.fault').write_text('Geometry identity timeout')
   assert identity==0x46475031,'Geometry identity mismatch'
   count=lib.geometry_run(q.ctypes.data,packed.ctypes.data,words.ctypes.data,timing.ctypes.data)
   if count==-110:
    (R/'geometry.dma.fault').write_text('Geometry DMA timeout: keep frozen; inspect idle before reconfiguration')
    (R/'dma.fault').write_text('Geometry DMA timeout')
   assert count>=0,'PL geometry command failed: '+str(count)
  finally:
   assert lib.geometry_close()==0,'Geometry DMA did not drain; keep mappings and fault state'
 xyz=np.empty((360,320,3),dtype='<f4');depth=np.empty((360,320),dtype='<f4');valid=np.empty((360,320),dtype=bool)
 domain=np.ascontiguousarray(domain)
 lib.geometry_extract.argtypes=[ctypes.c_void_p]*5;lib.geometry_extract.restype=ctypes.c_int
 assert lib.geometry_extract(words.ctypes.data,xyz.ctypes.data,valid.ctypes.data,depth.ctypes.data,domain.ctypes.data)==count,'PL output validation failed'
 report=dict(backend='PL FGP1 in preview/section image',input='unchanged FP32 disparity',intermediate='FP64',output='FP32 XYZ millimetres',valid_points=count,points=disparity.size,packing_seconds=packing,copyin_seconds=float(timing[0]),device_seconds=float(timing[1]),copyout_seconds=float(timing[2]),total_seconds=time.monotonic()-started,calls=1)
 return xyz,valid,depth,report
