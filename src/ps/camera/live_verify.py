"""Independent bounded acceptance of a live board result and held-photo sections."""
import base64,hashlib,io,json,math,re,time,zipfile
from pathlib import Path
from verify_full_pipeline_pc import verify_arrays,exact,np
from hardware_catalog import result_variant
ROOT=Path(__file__).resolve().parent
CALIBRATION=hashlib.sha256((ROOT/'stereo_parameters.json').read_bytes()).hexdigest()
BIT='8183863c879beb5bec68fc1e6a42e8b20df0a8ba4149af0e35871e9a0d0d854d'
H,W=360,320

def schema():
    spec={}
    def add(k,dtype,shape=(H,W)):spec[k]=(np.dtype(dtype),shape)
    add('frame_bgr','u1',(H,2*W,3));add('Q','f8',(4,4))
    for k in ('P1','P2'):add(k,'f8',(3,4))
    for side in ('left','right'):
        add('rectified_'+side,'u1',(H,W,3));add('features_'+side,'u8')
    for profile in ('detail','surface'):
        add(profile+'_valid','bool')
        for side in ('','_right'):
            for suffix,dtype in (('q4','i2'),('score','u2'),('margin','u2')):add(profile+side+'_'+suffix,dtype)
    for k in ('disparity_q4','completed_disparity_q4'):add(k,'i2')
    for k in ('valid','domain','profile_conflict'):add(k,'bool')
    for k in ('match_source','completion_origin'):add(k,'u1')
    for k in ('raw','completed'):
        add(k+'_xyz_q12','i4',(H,W,3));add(k+'_geometry_flags','i4')
    add('depth_mm','f4')
    add('dense_disparity_px','f4');add('dense_depth_mm','f4');add('dense_origin','u1');add('dense_distance_px','f4')
    add('dense3d_q4','i2');add('dense3d_xyz_q12','i4',(H,W,3));add('dense3d_flags','i4')
    add('dense3d_faces','i4',(None,3));add('dense3d_texture','u1',(H,W,3))
    return spec

def unpack(data,status,job):
    if not re.fullmatch('[0-9a-f]{32}',job):raise ValueError('Invalid photo identity')
    m=status.get('metadata') or {}
    if status.get('busy') or status.get('result_id')!=job or status.get('job_id')!=job:raise ValueError('Board photo changed')
    digest=hashlib.sha256(data).hexdigest()
    if len(data)>96*1024*1024 or len(data)!=m.get('package_bytes') or digest!=m.get('package_sha256'):raise ValueError('Result length/hash mismatch')
    spec=schema()
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        items=z.infolist();names=[v.filename for v in items]
        if len(names)!=len(set(names)) or set(names)!={k+'.npy' for k in (*spec,'metadata_json')}:raise ValueError('Unexpected result members')
        if sum(v.file_size for v in items)>160*1024*1024 or any(v.file_size>16*1024*1024 for v in items):raise ValueError('Expanded result too large')
    with np.load(io.BytesIO(data),allow_pickle=False) as z:a={k:z[k] for k in z.files}
    meta_bytes=a.pop('metadata_json')
    if meta_bytes.dtype!=np.uint8 or meta_bytes.ndim!=1 or meta_bytes.size>65536:raise ValueError('Invalid metadata')
    meta=json.loads(meta_bytes.tobytes())
    for k,(dtype,shape) in spec.items():
        v=a[k]
        if v.dtype!=dtype or v.ndim!=len(shape) or any(n is not None and n!=s for n,s in zip(shape,v.shape)):raise ValueError('Invalid array '+k)
        if shape[0] is None and len(v)>2*(H-1)*(W-1):raise ValueError('Too many triangles')
    if meta.get('job_id')!=job or any(m.get(k)!=v for k,v in meta.items()):raise ValueError('Status/package metadata mismatch')
    if meta.get('calibration_sha256')!=CALIBRATION:raise ValueError('Wrong calibration')
    result_variant(meta)
    if meta.get('maps_sha256')!=hashlib.sha256((ROOT/'rectification_maps.npz').read_bytes()).hexdigest():raise ValueError('Map identity changed')
    if meta.get('eye_size')!=[W,H] or meta.get('machine')!='aarch64' or meta.get('disparity_scale')!=16 or meta.get('xyz_scale')!=4096:raise ValueError('Wrong coordinate format')
    if meta.get('profiles')!=[{'name':'detail','p1':80,'p2':480},{'name':'surface','p1':160,'p2':720}]:raise ValueError('Unexpected matching settings')
    if meta.get('camera_sequence',0)<1 or not 0<=meta.get('source_age_seconds',-1)<=3:raise ValueError('Stale camera frame')
    return a,meta,digest

def verify(data,status,job,progress):
    start=time.monotonic();a,m,digest=unpack(data,status,job)
    progress('verify_primary');primary=verify_arrays(a,m,progress)
    with np.load(ROOT/'rectification_maps.npz') as z:exact('domain',a['domain'],((z['map0']>>42)&1).astype(bool))
    assert np.all(a['completion_origin']<=4)
    good=(a['completed_geometry_flags']&1)!=0
    assert np.all((a['completed_disparity_q4'][good]>=16)&(a['completed_disparity_q4'][good]<=2032))
    depth=a['raw_xyz_q12'][:,:,2].astype(np.float32)/4096;depth[~a['valid']]=np.nan
    assert np.array_equal(depth,a['depth_mm'],equal_nan=True)
    assert m['valid_pixels']==int(a['valid'].sum()) and m['accepted_measured_pixels']==int((a['completion_origin']==0).sum())
    assert m['completed_inside_domain_pixels']==int(good.sum())
    assert m['surface_preparation']=={'comparison_surfaces_removed':True,'seconds':0.0}
    b={};surface={'passed':True,'comparison_surfaces_removed':True}
    progress('verify_dense_fill')
    from verify_dense import verify_dense
    dense=verify_dense(a,m)
    from verify_dense_geometry import verify_dense_geometry
    dense['geometry']=verify_dense_geometry(a,m)
    report={'passed':True,'job_id':job,'source_sha256':digest,'primary':primary,'surface':surface,
            'seconds':time.monotonic()-start,'dense_fill':dense,'scope':'This live photo; coverage is not physical accuracy.'}
    return {k:v for k,v in a.items() if not k.startswith('display_')},m,b,report

def verify_section(result,a,job,request):
    if result.get('status')!='PASS' or result.get('job_id')!=job or result.get('calibration_sha256')!=CALIBRATION:raise ValueError('Section identity mismatch')
    axis=request['axis'];center=round(request['center_mm']*4096);half=round(request['thickness_mm']*2048)
    if result['axis']!=axis or result['center_q12']!=center or result['half_width_q12']!=half or result['include_inferred']!=request['include_inferred']:raise ValueError('Section parameters changed')
    flags=a['completed_geometry_flags'];xyz=a['completed_xyz_q12'];src=((flags>>8)&255).astype(np.uint8)
    valid=(flags&1)!=0;selected=valid&(abs(xyz[:,:,axis].astype(np.int64)-center)<=half)
    if not request['include_inferred']:selected&=src!=3
    expected=np.flatnonzero(selected).astype('<u4');count=len(expected)
    def decode(name,dtype,shape):
        raw=base64.b64decode(result[name],validate=True)
        if len(raw)!=int(np.prod(shape))*np.dtype(dtype).itemsize:raise ValueError('Section array length')
        return np.frombuffer(raw,dtype).reshape(shape)
    exact('section indices',decode('indices','<u4',(count,)),expected)
    coords=decode('xyz_q12','<i4',(count,3));exact('section coordinates',coords,xyz[selected])
    exact('section source',decode('source','u1',(count,)),src[selected])
    kinds=decode('origins','u1',(count,));exact('section origins',kinds,(src[selected]==3).astype(np.uint8))
    assert result['count']==count and result['measured']==int((kinds==0).sum()) and result['inferred']==int((kinds==1).sum())
    bounds=[float(v)/4096 for pair in zip(coords.min(axis=0),coords.max(axis=0)) for v in pair] if count else None
    assert result['bounds_mm']==bounds
    return expected,coords,src[selected]
