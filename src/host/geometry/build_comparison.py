"""Same-Q geometry and identical mesh limits for saved baseline and learned disparity."""
from pathlib import Path
import json,hashlib,time,base64,re,shutil
import numpy as np
import cv2
from PIL import Image,ImageDraw,ImageFont
from viewer_export import save_ply,viewer_intrinsics
from mesh_limits import triangle_stretch
R=Path(__file__).resolve().parent
O=R/'comparison';O.mkdir(exist_ok=True)
a=np.load(R/'input/board_result.npz');meta=json.loads(a['metadata_json'].tobytes())
rgb=a['rectified_left'][...,::-1].copy();h,w=rgb.shape[:2]
yy,xx=np.indices((h,w));q=a['Q'];n=h*w
def enc(x):return base64.b64encode(np.ascontiguousarray(x).tobytes()).decode()
v=(np.arange(n).reshape(h,w))[:-1,:-1].ravel()
grid_faces=np.concatenate([np.stack([v,v+w,v+1],1),np.stack([v+1,v+w,v+w+1],1)]).astype(np.int32)
def geometry(disp,valid):
    coords=np.stack([xx,yy,disp,np.ones_like(disp)],-1)@q.T
    with np.errstate(divide='ignore',invalid='ignore'):xyz=(coords[...,:3]/coords[...,3:]).astype(np.float32)
    positive=valid & np.isfinite(xyz).all(-1)&(xyz[...,2]>0)&(disp>0)
    shown=positive.copy()  # No added depth-window clipping; color scale is display-only.
    faces=grid_faces[np.all(shown.ravel()[grid_faces],axis=1)]
    z=xyz.reshape(-1,3)[faces,2]
    keep=np.ptp(z,axis=1)<=np.maximum(25.,.08*z.min(axis=1))
    faces=faces[keep];faces=faces[triangle_stretch(xyz,faces)<=25.]
    return xyz,positive,shown,faces
entries=[('baseline_raw','稳定版原始匹配',a['disparity_q4'].astype(np.float32)/16,a['valid']),
 ('baseline_final','稳定版补全＋平面修正',a['dense3d_q4'].astype(np.float32)/16,np.ones((h,w),bool))]
for key,title in [('light','LightStereo-S'),('fast','Fast-FoundationStereo')]:
    d=np.load(R/f'results/{key}/disparity.npy');entries.append((key,title,d,np.isfinite(d)&(d>0)))
allstats={};panels=[]
font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',19)
small=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',15)
template=(R/'viewer_template.html').read_text(encoding='utf8')
# Offline viewer: omit all board controls and labels; no credentials or runtime calls.
template=template.replace('<details id="section-panel" open>','<details id="section-panel" hidden>')
template=template.replace('<option value="measured">仅匹配来源</option>','')
template=template.replace('匹配来源 + 补全推测','全部显示点（包含估计）')
template=template.replace('const allPointIndices=Uint32Array.from({length:n},(_,i)=>i)',
 'const allPointIndices=Uint32Array.from({length:n},(_,i)=>i).filter(i=>originalValid[i])')
template=re.sub(r"\$\('details'\)\.textContent=.*?;", "$('details').textContent=s.note;",template)
template=re.sub(r"\$\('geometry-note'\)\.textContent=.*?;", "$('geometry-note').textContent=s.note;",template)
template=template.replace('平面修正＋适度断边','统一连面条件').replace('平面修正点云','当前算法点云')
template=template.replace('PL 原坐标','离线坐标').replace('补全视差PL投影','同标定矩阵反投影')
template=template.replace('板端平面修正','离线估计').replace('PL 匹配与点云 · A53 表面处理 · 电脑显示','离线算法对照')
template=re.sub(r'<div class="note">.*?</div>', '<div class="note">本页为独立电脑离线对照；网络结果未经补洞和平面修正，所有坐标使用原照片的标定矩阵计算。估计的连续表面不代表真实测量，单视角不能恢复背面。稳定板端程序未改动。</div>',template,flags=re.S)
template=re.sub(r'<a class="download" href="(?:matched_points_all|completed_points_preview)\.ply".*?</a>','',template)
template=template.replace("'板上补洞推测（不是实测）'", "'补洞或平面推测（不是实测）','神经网络视差估计（不是实测）'")
template=template.replace('含补全推测','包含估计深度').replace("?'含补全':", "?'估计深度':").replace('光照使用补全表面的法线','光照使用当前表面的法线')
original=a['completed_xyz_q12'].astype(np.float32)/4096/1000
stable_subset=((a['completed_geometry_flags']&1)!=0)&(a['completion_origin']==0)
shared_center=np.median(original[stable_subset],axis=0).tolist()
shared_bounds=np.percentile(original[stable_subset],[2,98],axis=0).T.tolist()
template=template.replace("const cameraCenter=medianPointCenter(originalXYZ,subset);", "const cameraCenter="+json.dumps(shared_center)+";")
template=template.replace("let bounds=[0,1,2].map(percentiles)","let bounds="+json.dumps(shared_bounds))
for key,title,disp,valid in entries:
    dst=O/key;dst.mkdir(exist_ok=True)
    geometry(disp,valid)
    geometry_samples=[]
    for _ in range(3):
        st=time.perf_counter();xyz,positive,shown,faces=geometry(disp,valid);geometry_samples.append(time.perf_counter()-st)
    geometry_sec=float(np.median(geometry_samples))
    if key=='baseline_final':
        # Exact saved stable output, not another pass through a comparison mesher.
        xyz=a['dense3d_xyz_q12'].astype(np.float32)/4096
        positive=np.isfinite(xyz).all(-1)&(xyz[...,2]>0)
        shown=positive.copy()
        faces=a['dense3d_faces'].copy()
        assert np.all(shown.ravel()[faces])
        geometry_sec=None;geometry_samples=[]
    np.savez_compressed(dst/'geometry.npz',disparity=disp,xyz_mm=xyz,valid=positive,display_valid=shown,faces=faces,Q=q)
    origin=np.full((h,w),6,np.uint8)
    if key=='baseline_raw':origin[:]=0
    elif key=='baseline_final':origin=np.where(a['dense_origin']==0,0,5).astype(np.uint8)
    save_ply(dst/'dense_points.ply',xyz,rgb,origin,shown,comments=('Offline estimate; no ground truth; no added depth-window clipping.',))
    save_ply(dst/'dense_surface.ply',xyz,rgb,origin,shown,faces)
    for name in ['matched_points_all.ply','completed_points_preview.ply']:shutil.copyfile(dst/'dense_points.ply',dst/name)
    cv2.imwrite(str(dst/'reference.png'),a['rectified_left'])
    cv2.imwrite(str(dst/'disparity.png'),np.where(positive[...,None],cv2.applyColorMap(np.uint8(np.clip(disp/127,0,1)*255),cv2.COLORMAP_TURBO),0))
    depth=np.clip((2-xyz[...,2]/1000)/1.85,0,1)
    depth=np.nan_to_num(depth)
    cv2.imwrite(str(dst/'depth.png'),np.where(positive[...,None],cv2.applyColorMap(np.uint8(depth*255),cv2.COLORMAP_JET),0))
    # Photometric residual is a consistency indicator, NOT true disparity error.
    warped=cv2.remap(a['rectified_right'],(xx-disp).astype(np.float32),yy.astype(np.float32),cv2.INTER_LINEAR)
    overlap=positive&(xx-disp>=0)&(xx-disp<=w-1)&a['domain']
    residual=np.mean(np.abs(warped.astype(float)-a['rectified_left'].astype(float)),axis=2)
    values=xyz[...,2][positive]/1000
    stats={'title':title,'positive_depth_percent':float(positive.mean()*100),'display_percent':float(shown.mean()*100),
           'depth_window_culling':False,'saved_stable_geometry_exact':key=='baseline_final',
           'mesh_triangles':len(faces),'geometry_mesh_seconds_pc':geometry_sec,'geometry_mesh_samples':geometry_samples,
           'photometric_mae_native_mask':float(np.mean(residual[overlap])),
           'depth_percentiles_m':np.percentile(values,[5,50,95]).tolist(),
           'ground_truth_available':False,'network_predictions_are_not_verified_measurements':True}
    if key in ['light','fast']:stats['timing']=json.loads((R/f'results/{key}/timing.json').read_text())
    else:stats['historical_board_processing_seconds']=meta['processing_seconds']
    allstats[key]=stats
    note='不按深度色标裁掉点。稳定版最终表面直接复用原板端坐标和网格；网络使用原标定及25 mm/8%/25倍拉伸连面阈值，未补洞或平面修正。旋转后未拍到的区域可能露出缺口。'
    summary={'photo':title,'input_size_wh':[w,h],'processing_label':title+' · 电脑离线对照','test_only':True,'pl_geometry':{'valid_points':int(shown.sum())},'note':note,'dense_geometry':{'mesh_limits':True}}
    safe=np.nan_to_num(xyz,nan=0,posinf=0,neginf=0);safe[~shown]=0
    texture=a['dense3d_texture'] if key=='baseline_final' else a['rectified_left']
    _,png=cv2.imencode('.png',texture)
    data={'summary':summary,'positions':enc(safe.astype('<f4')/1000),'colors':enc(rgb),'origins':enc(origin),
      'pixels':enc(np.arange(n,dtype='<u4')),'faces':enc(faces.astype('<u4')),'original_valid':enc(shown.astype('u1')),
      'camera_intrinsics':viewer_intrinsics(q),'dense_positions':enc(safe.astype('<f4')/1000),'dense_origins':enc(origin),
      'dense_faces':enc(faces.astype('<u4')),'texture_image':'data:image/png;base64,'+base64.b64encode(png).decode(),'texture_size_wh':[w,h]}
    html=template.replace('__POINTCLOUD_DATA__',json.dumps(data,separators=(',',':'),ensure_ascii=False))
    html=html.replace('</body>', '''<script>
if(location.search.includes('embed')){const st=document.createElement('style');st.textContent='header,aside{display:none!important}main{display:block!important;min-height:0!important;height:100vh!important}#stage{height:100vh!important;min-height:0!important}.overlay{font-size:11px}';document.head.append(st);}
window.addEventListener('message',e=>{if(e.origin!==location.origin||e.data?.type!=='comparison_action')return;const a=e.data.action;if(a==='front'||a==='oblique')document.getElementById(a).click();else if(['mesh','clay','points'].includes(a)){const el=document.getElementById('mode');el.value=a;el.dispatchEvent(new Event('input'));}});
</script></body>''')
    (dst/'viewer.html').write_text(html,encoding='utf8')
    panel=Image.new('RGB',(340,820),'#101827');dr=ImageDraw.Draw(panel)
    dr.text((10,8),title,font=font,fill='white')
    panel.paste(Image.open(dst/'disparity.png'),(10,42));panel.paste(Image.open(dst/'depth.png'),(10,435))
    dr.text((10,405),'视差：统一 0–127 px',font=small,fill='#bcccdc');dr.text((10,798),'深度：近红 0.15 m → 远蓝 2.0 m',font=small,fill='#bcccdc');panels.append(panel)
common=np.ones((h,w),bool)&a['domain']
for _,_,d,vld in entries:common&=vld&(d>0)&(xx-d>=0)
for key,_,d,vld in entries:
    warped=cv2.remap(a['rectified_right'],(xx-d).astype(np.float32),yy.astype(np.float32),cv2.INTER_LINEAR)
    allstats[key]['photometric_mae_common_mask']=float(np.abs(warped.astype(float)-a['rectified_left'].astype(float))[common].mean())
    allstats[key]['photometric_common_pixels']=int(common.sum())
mosaic=Image.new('RGB',(1360,820));[mosaic.paste(im,(340*i,0)) for i,im in enumerate(panels)];mosaic.save(O/'disparity_depth_comparison.png')
hashes=json.loads((R/'preserved_sha256.json').read_text())
changed=[p for p,h in hashes.items() if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h]
assert not changed,changed
report={'photo':json.loads((R/'input/input_manifest.json').read_text())['job_id'],'results':allstats,'stable_hash_check':{'files':len(hashes),'changed':changed},'method':'No new capture; identical stored rectified 320x360 images and Q. GPU model native maxdisp192, stable SGM128. CNN no postfill. No added depth clipping. Stable final XYZ/faces copied exactly from original board_result.npz. Fixed common color scales (saturation only). No ground truth.'}
(O/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf8')
cards=''.join(f'<article><h2>{s["title"]}</h2><a href="{k}/viewer.html">打开可旋转三维点云 / 表面 ↗</a><p>显示点 {s["display_percent"]:.1f}% · 三角面 {s["mesh_triangles"]:,}</p><iframe src="{k}/viewer.html?embed"></iframe></article>' for k,s in allstats.items())
rows=''
for k,s in allstats.items():
    infer=f'{s["timing"]["median_forward_seconds"]*1000:.1f} ms' if 'timing' in s else '不适用（板端）'
    mesh_time=f'{s["geometry_mesh_seconds_pc"]*1000:.1f} ms' if s['geometry_mesh_seconds_pc'] is not None else '直接使用原板端网格'
    rows+=f'<tr><td>{s["title"]}</td><td>{infer}</td><td>{mesh_time}</td><td>{s["photometric_mae_common_mask"]:.2f}</td></tr>'
html='''<!doctype html><meta charset="utf-8"><title>同照片 CNN 双目对照</title><style>body{background:#0b1220;color:#e4edf6;font:16px/1.7 Microsoft YaHei,sans-serif;max-width:1500px;margin:30px auto;padding:0 24px}h1{margin:8px 0}p{color:#b5c6d6}a{color:#65ded0}img{width:100%}.cards{display:grid;grid-template-columns:1fr 1fr;gap:22px}article{background:#152134;padding:16px;border-radius:12px}iframe{border:0;width:100%;height:600px}table{border-collapse:collapse;width:100%;margin:24px 0}td,th{border-bottom:1px solid #345;padding:10px;text-align:left}</style><h1>同一张照片 · 320×360 · CNN 双目对照</h1>'''
html+=f'<p>照片 {report["photo"][:8]} ｜ 稳定工程 {len(hashes)} 个文件校验未变 ｜ 本页仅离线结果</p><p><b>显示已修正：取消额外的15厘米–2米深度裁剪。</b>稳定版最终结果直接使用原板端115,200个点、219,398个三角面，不重新删点或连面。第一列“原始匹配”本来就没有补洞，不能代表稳定版最终效果。网络未追加补洞和平面修正。色标范围只影响颜色，不会隐藏点；默认先看正面，再比较侧面。</p><img src="disparity_depth_comparison.png">'
html+='<table><tr><th>算法</th><th>GPU 单次推理中位数</th><th>电脑 XYZ＋连面</th><th>共同区域颜色残差 MAE ↓</th></tr>'+rows+'</table>'
html+=f'<p>该照片原板端完整处理 {meta["processing_seconds"]:.3f} s，包含匹配、补全及三维，与 GPU 单次网络推理不能直接算加速比。网络为 RTX 4060 笔记本 GPU、PyTorch CUDA，计时含同步；预热后有限 5 次取中位数，排除环境安装和模型加载。XYZ＋连面为电脑预热后3次中位数，排除磁盘导出与网页绘制。颜色残差仅是左右一致性参考，不是真实深度误差。模型搜索上限192，稳定SGM128；保留模型原配置，未伪称同搜索范围。</p>'
html+='''<h2>三维效果：四幅图可统一切换</h2><div id="actions"><button data-action="front">统一正面</button><button data-action="oblique">统一斜侧面</button><button data-action="mesh">彩色表面</button><button data-action="clay">纯色形状</button><button data-action="points">点云</button></div><style>button{background:#23435c;color:white;border:1px solid #58758d;border-radius:7px;padding:10px 18px;margin:5px;cursor:pointer}iframe{height:460px}</style><script>document.getElementById('actions').onclick=e=>{const a=e.target.dataset.action;if(a)document.querySelectorAll('iframe').forEach(f=>f.contentWindow.postMessage({type:'comparison_action',action:a},location.origin))}</script>'''
html+='<div class="cards">'+cards+'</div><p><a href="report.json">完整数据与计时</a></p>'
html+='''<style>@media(max-width:800px){body{margin:16px auto;padding:0 14px;font-size:14px}.cards{grid-template-columns:minmax(0,1fr)}article{min-width:0}h1{font-size:24px}h2{font-size:19px}table{font-size:12px;display:block;overflow-x:auto}th,td{padding:8px}iframe{height:420px}}</style>'''
(O/'index.html').write_text(html,encoding='utf8')
print(json.dumps(report,ensure_ascii=False,indent=2))
