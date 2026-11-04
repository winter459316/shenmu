"""Package board XYZ/disparity into the existing interactive viewer, no rematch."""
from pathlib import Path
import base64,json,re,struct,sys
import cv2,numpy as np
R=Path(__file__).resolve().parent;C=R.parents[1]/'experiments/cnn_stereo_20261018'
sys.path.insert(0,str(C))
from mesh_limits import triangle_stretch
from viewer_export import save_ply,viewer_intrinsics

def export(folder,status):
    with np.load(folder/'board_result.npz',allow_pickle=False) as z:a={n:z[n] for n in z.files}
    d=a['disparity'];xyz=a['xyz_mm'];valid=a['valid'];h,w=d.shape
    assert d.shape==(360,320) and xyz.shape==(360,320,3) and valid.shape==d.shape and valid.dtype==bool
    assert np.isfinite(d).all() and np.isfinite(xyz[valid]).all() and (xyz[valid,2]>0).all()
    report=json.loads(a['metadata_json'].tobytes());assert report['job_id']==folder.name and report['pl']['calls']==2
    assert report['input_wh']==[320,360] and report['iterations']==2 and report['arithmetic']=='INT16 x INT16 / INT48 accumulation in two PL blocks; FP32 elsewhere'
    v=np.arange(h*w).reshape(h,w)[:-1,:-1].ravel()
    faces=np.concatenate([np.stack([v,v+w,v+1],1),np.stack([v+1,v+w,v+w+1],1)]).astype('<u4')
    faces=faces[valid.ravel()[faces].all(1)]
    z=xyz.reshape(-1,3)[faces,2]
    faces=faces[np.ptp(z,axis=1)<=np.maximum(25.,.08*z.min(1))]
    faces=faces[triangle_stretch(xyz,faces)<=25]
    rgb=np.ascontiguousarray(a['rectified_left'][...,::-1]);origin=np.full(d.shape,6,np.uint8)
    enc=lambda x:base64.b64encode(np.ascontiguousarray(x).tobytes()).decode()
    html=(R/'viewer_template.html').read_text(encoding='utf8')
    pattern=r'(<script id="cloud-data" type="application/json">)(.*?)(</script>)'
    _,png=cv2.imencode('.png',a['rectified_left'])
    coordinate_pl=bool(report.get('geometry_pl'))
    coordinate_label='PL 三维坐标' if coordinate_pl else 'A53 三维坐标'
    summary=dict(photo='FAST-'+folder.name[:8],input_size_wh=[w,h],processing_label='板端 PL 校正 + Fast 卷积 PL 加速匹配 + '+coordinate_label+'；电脑连面和显示',test_only=True,pl_geometry={'valid_points':int(valid.sum())},note='这次新拍照片的 Fast 结果。模型采用 INT16/FP32 混合精度、2次迭代、最大视差192。未增加补洞和平面修正；沿用25mm/8%/25连面条件。'+('坐标由板端 PL FGP1 计算，PS负责调度。' if coordinate_pl else '坐标由板端A53计算。'),dense_geometry={'mesh_limits':True})
    if status.get('replay_only'):
        summary['replay_only']=True
        summary['note']=summary['note'].replace('这次新拍照片','这次保存照片回放')
    data=dict(summary=summary,positions=enc((xyz/1000).astype('<f4')),colors=enc(rgb),origins=enc(origin),pixels=enc(np.arange(w*h,dtype='<u4')),faces=enc(faces),original_valid=enc(valid.astype('u1')),camera_intrinsics=viewer_intrinsics(a['Q']),texture_image='data:image/png;base64,'+base64.b64encode(png).decode(),texture_size_wh=[w,h])
    html=re.sub(pattern,lambda m:m[1]+json.dumps(data,separators=(',',':'),ensure_ascii=False)+m[3],html,flags=re.S)
    if valid.any():
        points=xyz[valid]/1000;bounds=np.percentile(points,[1,99],axis=0).T.tolist()
        html=re.sub(r'let bounds=\[.*?\],center=bounds\.map',lambda m:'let bounds='+json.dumps(bounds)+',center=bounds.map',html,count=1)
    html=html.replace('href="dense_points.ply"','href="points.ply"')
    html=html.replace('板上 离线坐标：','板端 '+coordinate_label+'：')
    html=html.replace('本页为独立电脑离线对照；网络结果未经补洞和平面修正，所有坐标使用原照片的标定矩阵计算。','本页显示这次新拍照片的板端结果：PL 校正，Fast 由 A53＋PL 处理，'+coordinate_label+'使用本机标定。电脑接收结果、连面和显示。')
    if status.get('replay_only'):html=html.replace('这次新拍照片','这次保存照片回放')
    (folder/'viewer.html').write_text(html,encoding='utf8')
    save_ply(folder/'points.ply',xyz,rgb,origin,valid)
    save_ply(folder/'dense_surface.ply',xyz,rgb,origin,valid,faces)
    np.savez_compressed(folder/'geometry.npz',xyz_mm=xyz,disparity=d,valid=valid,faces=faces,Q=a['Q'])
    for name,image in (('reference',a['rectified_left']),('rectified',np.concatenate([a['rectified_left'],a['rectified_right']],1))):cv2.imwrite(str(folder/(name+'.png')),image)
    disparity=cv2.applyColorMap((np.clip(d/192,0,1)*255).astype('u1'),cv2.COLORMAP_TURBO);disparity[~valid]=0
    depth=cv2.applyColorMap((np.clip(1-(np.nan_to_num(a['depth_mm'],nan=0)/1000-.2)/2.8,0,1)*255).astype('u1'),cv2.COLORMAP_JET);depth[~valid]=0
    cv2.imwrite(str(folder/'disparity.png'),disparity);cv2.imwrite(str(folder/'depth.png'),depth)
    (folder/'depth_values.json').write_text(json.dumps({'width':w,'height':h,'depth_mm':np.where(valid,np.nan_to_num(a['depth_mm']),0).round(2).ravel().tolist(),'disparity_px':d.round(4).ravel().tolist()},separators=(',',':')))
    # Float64 preserves every value previously parsed from the JSON display arrays.
    depths=np.where(valid,np.nan_to_num(a['depth_mm']),0).round(2).astype('<f8')
    disparities=d.round(4).astype('<f8')
    (folder/'depth_values.bin').write_bytes(struct.pack('<4I',0x31505444,1,w,h)+depths.tobytes()+disparities.tobytes())
    report.update(replay_only=bool(status.get('replay_only')),pl_rectification_seconds=status.get('rectification',{}).get('pl_rectification_seconds'),stage_seconds=status.get('stage_seconds',{}),processing_preview=status.get('processing_preview',{}))
    report.update(total_seconds=status['total_seconds'],triangles=len(faces),stable_restored=status['stable_restored'],package_sha256=status['package_sha256'],viewer_url='/captures/'+folder.name+'/viewer.html',job_id=folder.name)
    if 'archive_seconds' in status.get('inference',{}):report['archive_seconds']=status['inference']['archive_seconds']
    (folder/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf8')
    return report
