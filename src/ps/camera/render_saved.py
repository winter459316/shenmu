"""Export verified board point cloud and current surface only; no comparison surfaces."""
import base64,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[1]/'experiments/usb_camera_20261016/deps'))
import numpy as np
import cv2
from viewer_export import save_ply,viewer_intrinsics

def encode(a):return base64.b64encode(np.ascontiguousarray(a).tobytes()).decode()

def export_result(a,m,b,s,out,job_id=None,token=None,captured_pc=None):
    assert not b and s.get('comparison_surfaces_removed')
    out=Path(out);out.mkdir(exist_ok=True,parents=True)
    good=(a['completed_geometry_flags']&1)!=0;origin=a['completion_origin'];rgb=a['rectified_left'][:,:,::-1].copy()
    dense=a['dense3d_xyz_q12'].astype(np.float32)/4096
    original=a['completed_xyz_q12'].astype(np.float32)/4096
    display=original.copy();display[~good]=dense[~good]
    raw=a['raw_xyz_q12'].astype(np.float32)/4096;raw[~a['valid']]=np.nan
    summary={'photo':job_id[:8] if job_id else 'REPLAY-'+m['frame_sha256_bgr'][:8], 'input_size_wh':[320,360],
        'test_only':not bool(job_id),'captured_pc':captured_pc,'preview_depth_range_m':[.15,2.],
        'pl_geometry':{'valid_points':int(good.sum())},'dense_geometry':m['dense_geometry'],
        'calibration_sha256':m['calibration_sha256'],'frame_sha256_bgr':m['frame_sha256_bgr'],
        'comparison_surfaces_removed':True,'algorithm_verified':False,'board_processing_ms':m['processing_seconds']*1000,
        'processing_label':'PL 匹配与点云 · 复用快速补全 · A53 当前表面连面 · 电脑直接显示',
        'note':'仅生成当前全填充表面；旧版工程和照片另行保留。推测区域可能连接前后景。'}
    dense_origin=np.where(a['dense_origin']==0,0,5).astype(np.uint8)
    if m.get('plane_correction'):
        summary['plane_correction']=m['plane_correction']
        summary['processing_label']='PL 匹配 · A53 平面修正 · PL 修正后点云 · A53 连面 · 电脑显示'
        summary['note']='当前点云和表面使用平面修正结果，修正点标记为推测；原始匹配与截面坐标另行保留。'
    if m['dense_geometry'].get('mesh_limits'):
        summary['processing_label']='PL 点云 · A53 平面修正及适度断边 · 保留短连接 · 电脑显示'
        summary['mesh_limits']=m['dense_geometry']['mesh_limits']
        summary['remesh']=m.get('remesh')
    data={'summary':summary,'positions':encode(display.reshape(-1,3).astype('<f4')/1000),
        'colors':encode(rgb.reshape(-1,3)),'origins':encode(origin.ravel()),'pixels':encode(np.arange(good.size,dtype='<u4')),
        'faces':'','original_valid':encode(good.ravel().astype(np.uint8)),
        'camera_intrinsics':viewer_intrinsics(a['Q']),
        'dense_positions':encode(dense.reshape(-1,3).astype('<f4')/1000),
        'dense_origins':encode(dense_origin.ravel()),'dense_faces':encode(a['dense3d_faces'].astype('<u4'))}
    save_ply(out/'matched_points_all.ply',raw,rgb,origin,(origin==0)&a['valid'])
    save_ply(out/'completed_points_preview.ply',original,rgb,origin,good)
    save_ply(out/'dense_points.ply',dense,rgb,dense_origin,np.ones(good.shape,bool))
    save_ply(out/'dense_surface.ply',dense,rgb,dense_origin,np.ones(good.shape,bool),a['dense3d_faces'],('Fast completed disparity projected by PL; unrestricted mesh includes inferred depths.',))
    ok,png=cv2.imencode('.png',a['rectified_left']);assert ok;(out/'reference.png').write_bytes(png.tobytes())
    ok,texture=cv2.imencode('.png',a['dense3d_texture']);assert ok
    data['texture_image']='data:image/png;base64,'+base64.b64encode(texture).decode();data['texture_size_wh']=[320,360]
    np.savez_compressed(out/'geometry.npz',**a)
    (out/'report.json').write_text(json.dumps({'summary':summary,'primary':m},ensure_ascii=False,indent=2),encoding='utf8')
    template=(ROOT/'pointcloud_viewer.html').read_text(encoding='utf8')
    if not m.get('plane_correction'):
        template=template.replace('平面修正表面','原版补全表面').replace('当前点云和表面使用A53平面修正后的视差，由PL生成坐标；修正点属于推测。','这张历史照片未执行平面修正，仍显示原版结果。')
    if job_id:
        config='<script>window.AUTO_CLOUD_REVISION='+json.dumps(job_id)+';window.HDMI_TOKEN='+json.dumps(token)+';</script>'
        template=template.replace('<script id="cloud-data"',config+'<script id="cloud-data"')
    (out/'viewer.html').write_text(template.replace('__POINTCLOUD_DATA__',json.dumps(data,separators=(',',':'),ensure_ascii=False)),encoding='utf8')
    print('SAVED_CURRENT_SURFACE',out,'points',good.size,'triangles',len(a['dense3d_faces']),flush=True)
    return summary
