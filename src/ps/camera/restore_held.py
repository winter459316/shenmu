"""Restore one checksummed held result after a controlled service update.

Does not compute, capture, load PL, or replace its original hardware metadata.
The manifest and exact package are prepared from the running service first.
"""
import hashlib,json,re,math
from pathlib import Path
import numpy as np
from hardware_catalog import result_variant
ROOT=Path(__file__).resolve().parent

def restore(runtime):
    record=json.loads((ROOT/'held_restore.json').read_text())
    assert {'job_id','sha256','bytes'}<=set(record)<={'job_id','sha256','bytes','total_seconds'}
    if 'total_seconds' in record:
        assert type(record['total_seconds']) in (int,float) and math.isfinite(record['total_seconds']) and record['total_seconds']>=0
    assert re.fullmatch('[0-9a-f]{32}',record['job_id'])
    data=(ROOT/'held_restore.npz').read_bytes()
    assert len(data)==record['bytes'] and hashlib.sha256(data).hexdigest()==record['sha256']
    with np.load(ROOT/'held_restore.npz',allow_pickle=False) as z:
        metadata=json.loads(z['metadata_json'].tobytes())
        assert metadata['job_id']==record['job_id'] and metadata['schema']=='usb_full_v2'
        assert metadata['calibration_sha256']=='6dbbd7ca2aa6f013e4f4f0861a18f7cd2d00f2434dc2e5d53185caae2d81128d'
        result_variant(metadata)
        xyz=z['completed_xyz_q12'];flags=z['completed_geometry_flags']
        assert xyz.shape==(360,320,3) and xyz.dtype==np.dtype('int32')
        assert flags.shape==(360,320)
        records=np.concatenate((xyz,flags[:,:,None]),axis=2).astype(np.int32)
    with runtime.lock:
        assert not runtime.busy and not runtime.section_busy and runtime.job_id is None
        runtime.held=records;runtime.package=data;runtime.job_id=record['job_id'];runtime.result_id=record['job_id']
        runtime.metadata=dict(metadata,package_sha256=record['sha256'],package_bytes=len(data),restored=True)
        if 'total_seconds' in record:runtime.metadata['total_seconds']=record['total_seconds']
        runtime.stage='ready';runtime.error=''
    return record
