import numpy as np
def verify_dense_geometry(a,m):
    q=a['dense3d_q4'];xyz=a['dense3d_xyz_q12'].astype(np.float64)/4096;flags=a['dense3d_flags'];fs=a['dense3d_faces']
    assert np.array_equal(q,np.clip(np.rint(a['dense_disparity_px']*16),16,2032).astype(np.int16))
    assert np.array_equal(q[(a['completion_origin']==0)],a['disparity_q4'][(a['completion_origin']==0)])
    src=np.where((a['completion_origin']==0),a['match_source'],3).astype(np.int32)
    assert np.array_equal(flags,(src<<8)|1)
    y,x=np.indices(q.shape);h=np.stack((x,y,q/16,np.ones(q.shape)),axis=-1)@a['Q'].T
    ideal=h[:,:,:3]/h[:,:,3,None];error=float(np.max(abs(xyz-ideal)));assert error<.00025
    assert np.isfinite(xyz).all() and (xyz[:,:,2]>0).all()
    assert np.array_equal(a['dense3d_xyz_q12'][(a['completion_origin']==0)],a['raw_xyz_q12'][(a['completion_origin']==0)])
    assert fs.shape==(229042,3) and fs.min()==0 and fs.max()==115199
    fx=fs%320;fy=fs//320;assert (np.ptp(fx,axis=1)==1).all() and (np.ptp(fy,axis=1)==1).all()
    cells=fy.min(axis=1)*319+fx.min(axis=1);counts=np.bincount(cells,minlength=114521);assert (counts==2).all()
    grid=np.arange(115200).reshape(360,320);tl=grid[:-1,:-1].ravel();tr=tl+1;bl=tl+320;br=bl+1
    z=a['dense3d_xyz_q12'][:,:,2].ravel().astype(np.int64);alt=abs(z[tl]-z[br])<abs(z[tr]-z[bl])
    expected=np.stack((np.stack((tl,bl,np.where(alt,br,tr)),1),np.stack((np.where(alt,tl,tr),np.where(alt,br,bl),np.where(alt,tr,br)),1)),1).reshape(-1,3)
    assert np.array_equal(fs,expected)
    assert np.array_equal(a['dense3d_texture'][a['domain']],a['rectified_left'][a['domain']])
    assert m['dense_geometry']['points']==115200 and m['dense_geometry']['triangles']==len(fs)
    return {'passed':True,'points':115200,'triangles':len(fs),'empty_grid_cells':0,'q12_max_error_mm':error,'matched_xyz_exact':True,'all_cells_two_triangles':True}
