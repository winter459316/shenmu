"""Independent PC oracle on the actual returned PL outputs, never production."""
from evaluate_reference import match,gray_u8,features,validity,cv2,np
import hashlib,json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def exact(name,actual,expected):
    assert actual.shape==expected.shape,(name,actual.shape,expected.shape)
    assert np.array_equal(actual,expected),(name,int(np.count_nonzero(actual!=expected)))
    print(name,'EXACT',actual.size,flush=True)
def remap_integer(raw,packed):
    x=(packed&65535).astype(np.uint16).view(np.int16).astype(np.int32)
    y=((packed>>16)&65535).astype(np.uint16).view(np.int16).astype(np.int32)
    fx=((packed>>32)&31).astype(np.uint32);fy=((packed>>37)&31).astype(np.uint32)
    h,w=raw.shape[:2];total=np.zeros(raw.shape,np.uint32)
    for dy in (0,1):
        for dx in (0,1):
            xx=x+dx;yy=y+dy;mask=(xx>=0)&(xx<w)&(yy>=0)&(yy<h)
            weight=(fx if dx else 32-fx)*(fy if dy else 32-fy)
            total+=raw[yy.clip(0,h-1),xx.clip(0,w-1)].astype(np.uint32)*(weight*mask)[:,:,None]
    return ((total+512)//1024).astype(np.uint8)
def verify_arrays(a,meta,progress=None):
    start=time.monotonic();assert meta['schema']=='usb_full_v2'
    assert hashlib.sha256(a['frame_bgr'].tobytes()).hexdigest()==meta['frame_sha256_bgr']
    p=json.loads((ROOT/'stereo_parameters.json').read_text())
    assert hashlib.sha256((ROOT/'stereo_parameters.json').read_bytes()).hexdigest()==meta['calibration_sha256']
    for k in ('Q','P1','P2'):exact(k,a[k],np.array(p[k]))
    gray=[];support=[];rounding={}
    with np.load(ROOT/'rectification_maps.npz') as z:
        for eye,name in ((0,'left'),(1,'right')):
            maps=z['map%d'%eye];s=((maps>>42)&1).astype(bool);support.append(s)
            raw=a['frame_bgr'][:,eye*320:(eye+1)*320]
            rect=remap_integer(raw,maps);exact('rectified_'+name,a['rectified_'+name],rect)
            g=gray_u8(rect);gray.append(g);packed=features(g).astype(np.uint64)|(s.astype(np.uint64)<<32)
            exact('features_'+name,a['features_'+name],packed)
            k=str(eye+1);mx,my=cv2.initUndistortRectifyMap(np.array(p['K'+k]),np.array(p['D'+k]),np.array(p['R'+k]),np.array(p['P'+k]),(320,360),cv2.CV_32FC1)
            diff=rect.astype(np.int16)-cv2.remap(raw,mx,my,cv2.INTER_LINEAR).astype(np.int16)
            rounding[name]={'opencv_max_abs_channel_difference':int(abs(diff).max()),'differing_channels':int(np.count_nonzero(diff))}
    for name,p1,p2 in (('detail',80,480),('surface',160,720)):
        for mirrored in (False,True):
            prefix=name+('_right' if mirrored else '')
            if progress:progress('verify_'+prefix)
            l,r=gray if not mirrored else [gray[1][:,::-1].copy(),gray[0][:,::-1].copy()]
            ls,rs=support if not mirrored else [support[1][:,::-1],support[0][:,::-1]]
            result=match(l,r,ls,rs,p1,p2)
            if mirrored:result=[v[:,::-1].copy() for v in result]
            for suffix,expected in zip(('q4','score','margin'),result):exact(prefix+'_'+suffix,a[prefix+'_'+suffix],expected)
        valid=validity(a[name+'_q4'],a[name+'_score'],a[name+'_margin'],a[name+'_right_q4'],a[name+'_right_score'],a[name+'_right_margin'],*support)
        exact(name+'_valid',a[name+'_valid'],valid)
    d,s=a['detail_valid'],a['surface_valid']
    conflict=d&s&(abs(a['detail_q4'].astype(np.int32)-a['surface_q4'].astype(np.int32))>16)
    exact('profile_conflict',a['profile_conflict'],conflict)
    source=np.zeros(d.shape,np.uint8);source[d&~conflict]=1;source[~d&s]=2
    fused=np.full(d.shape,-32768,np.int16);fused[source==1]=a['detail_q4'][source==1];fused[source==2]=a['surface_q4'][source==2]
    cv2.filterSpeckles(fused,-32768,20,16);source[fused==-32768]=0
    exact('fused_q4',a['disparity_q4'],fused);exact('match_source',a['match_source'],source);exact('valid',a['valid'],source>0)
    origin=a['completion_origin'];exact('outside_domain',origin==3,~support[0])
    assert not np.any((origin==0)&~a['valid'])
    exact('retained_matches',a['completed_disparity_q4'][origin==0],fused[origin==0])
    source_complete=np.where(origin==0,source,np.where(origin==3,0,3)).astype(np.uint8)
    errors={};projections={};y,x=np.indices(d.shape)
    for prefix,q,src in (('raw',fused,source),('completed',a['completed_disparity_q4'],source_complete)):
        flags=a[prefix+'_geometry_flags'];mask=src>0
        exact(prefix+'_flags',flags,((src.astype(np.int32)<<8)|mask.astype(np.int32)))
        xyz=a[prefix+'_xyz_q12'].astype(np.float64)/4096
        hom=np.column_stack((x[mask],y[mask],q[mask]/16,np.ones(int(mask.sum()))))@a['Q'].T
        ideal=hom[:,:3]/hom[:,3,None]
        error=float(abs(xyz[mask]-ideal).max());assert error<.00025;errors[prefix]=error
        assert np.all(a[prefix+'_xyz_q12'][~mask]==0)
        # Propagate the strict coordinate rounding allowance through each P.
        pix=[]
        for eye,P in enumerate((a['P1'],a['P2'])):
            expected=np.column_stack((x[mask]-eye*q[mask]/16,y[mask]))
            hi=np.column_stack((ideal,np.ones(len(ideal))))@P.T
            ideal_uv=hi[:,:2]/hi[:,2,None];assert abs(ideal_uv-expected).max()<1e-8
            ha=np.column_stack((xyz[mask],np.ones(len(ideal))))@P.T
            uv=ha[:,:2]/ha[:,2,None]
            eps=.00025;de=np.sum(abs(P[:,:3]),axis=1)*eps
            bound=(de[:2]+abs(ideal_uv)*de[2])/(hi[:,2,None]-de[2])+1e-9
            assert np.all(abs(uv-expected)<=bound),(prefix,eye)
            pix.append(float(abs(uv-expected).max()))
        projections[prefix]=pix
    result={'passed':True,'all_four_primary_pl_matches_exact':True,
            'raw_and_completed_q12_verified':True,'geometry_max_error_mm':errors,'projection_max_error_px':projections,
            'rectification_opencv_rounding':rounding,'valid_pixels':int(a['valid'].sum()),'accepted_measured':int((origin==0).sum()),
            'inferred_inside_domain':int(((origin!=0)&(origin!=3)).sum()),'seconds':time.monotonic()-start,
            'scope':'All returned matching values, calibration, rectification, fusion and geometry; not metric ground-truth acceptance.'}
    return result

def main():
    path=ROOT/'board_evidence/full_pipeline_result.npz'
    with np.load(path,allow_pickle=False) as z:a={k:z[k] for k in z.files}
    meta=json.loads(a.pop('metadata_json').tobytes())
    result=verify_arrays(a,meta)
    result['source_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    (ROOT/'board_evidence/full_pipeline_pc_verified.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
if __name__=='__main__':main()
