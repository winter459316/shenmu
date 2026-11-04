"""Export the independently checked A53 held-photo result, never recapture.

The stable layers stay intact. A fifth inferred layer enables same-pose A/B.
"""
import hashlib,json,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parents[1]/'experiments/usb_camera_20261016/deps'))
import numpy as np
from render_saved import export_result,encode
from viewer_export import save_ply
from surface_small_holes import seal_small_holes
from test_small_holes import CONFIG,check_result

def main(reference_photo=False):
    evidence=ROOT/'board_evidence';job='6bed0c1a3fcd43a08fcbb8ff69838f67'
    prefix='small_holes_reference' if reference_photo else 'small_holes'
    source=evidence/'full_pipeline_result.npz' if reference_photo else ROOT/'live_captures'/job/'board_result.npz'
    report=json.loads((evidence/(prefix+'_verified.json')).read_text())
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    assert report['passed'] and report['architecture']=='aarch64'
    if reference_photo:
        assert report['source_sha256']['full_pipeline_result.npz']==digest
        assert report['source_sha256']['surface_result.npz']==hashlib.sha256((evidence/'surface_result.npz').read_bytes()).hexdigest()
        assert report['all_input_files_unchanged'] and report['frame_sha256_bgr'].startswith('1c69fd2a')
    else:
        old_verified=json.loads((source.parent/'verified.json').read_text())
        assert report['source_sha256']==old_verified['source_sha256']==digest
        assert report['job_id']==job and report['all_input_arrays_unchanged']
    assert not report['shutter_triggered']
    assert report['code_sha256']==hashlib.sha256((ROOT/'surface_small_holes.py').read_bytes()).hexdigest()
    with np.load(source,allow_pickle=False) as z:a={k:z[k] for k in z.files}
    if reference_photo:
        with np.load(evidence/'surface_result.npz',allow_pickle=False) as z:
            original_surface={k:z[k] for k in z.files}
        metadata=json.loads(a['metadata_json'].tobytes());metadata['surface_preparation']=json.loads(original_surface.pop('metadata_json').tobytes())
        a['metadata_json']=np.frombuffer(json.dumps(metadata).encode(),np.uint8)
        a.update({'display_'+k:v for k,v in original_surface.items()})
    with np.load(evidence/(prefix+'_result.npz'),allow_pickle=False) as z:sealed={k:z[k] for k in z.files}
    names=('display_repaired_disparity_px','display_repaired_valid','display_repaired_xyz_mm','display_repaired_faces','display_repaired_origin','display_preview_valid','completed_disparity_q4','Q')
    # Reference is only a verifier. Viewer data below comes from the board NPZ.
    reference=seal_small_holes(*[a[k] for k in names],config=CONFIG)
    exact={k:np.array_equal(reference[k],v,equal_nan=True) for k,v in sealed.items()}
    assert all(exact.values()),exact
    if not reference_photo:
        initial=dict(np.load(evidence/'small_holes_first_result.npz',allow_pickle=False))
        assert all(np.array_equal(initial[k],v,equal_nan=True) for k,v in sealed.items())
    check_result(sealed,a[names[0]],a[names[1]],a[names[2]],a[names[4]],a[names[5]],a['Q'])
    meta=json.loads(a.pop('metadata_json').tobytes())
    b={k[8:]:v for k,v in a.items() if k.startswith('display_')}
    a={k:v for k,v in a.items() if not k.startswith('display_')}
    out=ROOT/'saved_render'/('seal_reference' if reference_photo else 'seal_candidate')
    photo='USB-PL-1c69fd2a' if reference_photo else job[:8]
    original_url='http://127.0.0.1:8770/viewer.html' if reference_photo else f'http://127.0.0.1:8771/captures/{job}/viewer.html'
    export_result(a,meta,b,meta['surface_preparation'],out)
    path=out/'viewer.html';html=path.read_text(encoding='utf8')
    pattern=r'(<script id="cloud-data" type="application/json">)(.*?)(</script>)'
    match=re.search(pattern,html,re.S);assert match
    data=json.loads(match[2]);flat=np.flatnonzero(b['preview_valid'])
    mapping=np.full(b['preview_valid'].size,-1,np.int32);mapping[flat]=np.arange(len(flat))
    valid=sealed['valid'].ravel()[flat];coords=sealed['xyz_mm'].reshape(-1,3)[flat].copy()
    coords[~valid]=a['completed_xyz_q12'].reshape(-1,3)[flat][~valid]/4096
    data.update(sealed_positions=encode(coords.astype('<f4')/1000),sealed_valid=encode(valid.astype('u1')),
                sealed_faces=encode(mapping[sealed['grid_faces']].astype('<u4')),
                sealed_origins=encode(sealed['provenance'].ravel()[flat]))
    data['summary'].update(photo=photo,surface_sealing=report,
        processing_label='同一张照片 · 板上 A53 局部封孔 · 电脑逐值验证',
        note='固定照片的独立修补对照，尚未切换实时拍照流程。')
    html=html[:match.start(2)]+json.dumps(data,ensure_ascii=False,separators=(',',':'))+html[match.end(2):]
    def replace(old,new):
        nonlocal html
        assert html.count(old)==1,old[:100]
        html=html.replace(old,new)
    replace('<h1>静态双目 · 三维渲染</h1>','<h1>同一照片 · 小孔修补对照</h1>')
    replace('彩色表面查看外观，纯色光照观察形状；单次拍摄只包含可见的一面。',
            '在“表面处理”切换修补前后，旋转角度保持一致；未知背面仍然留空。')
    replace('<option value="repaired" selected>补洞表面（保留细节）</option>',
            '<option value="sealed" selected>局部封孔表面（推测）</option><option value="repaired">修补前 · 当前稳定版</option>')
    replace('let xyz=originalXYZ;',"const sealedXYZ=decode(data.sealed_positions,Float32Array),sealedValid=decode(data.sealed_valid,Uint8Array),sealedFaces=decode(data.sealed_faces,Uint32Array),sealedOrigins=decode(data.sealed_origins,Uint8Array);\nlet xyz=originalXYZ;")
    addition="""
layers.repaired.label='修补前 · 当前稳定版';
const sealPoints=allPointIndices.filter(i=>sealedValid[i]),sealRawPoints=sealPoints.filter(i=>sealedOrigins[i]===0),sealRawFaces=[];
for(let i=0;i<sealedFaces.length;i+=3)if(sealedOrigins[sealedFaces[i]]===0&&sealedOrigins[sealedFaces[i+1]]===0&&sealedOrigins[sealedFaces[i+2]]===0)sealRawFaces.push(sealedFaces[i],sealedFaces[i+1],sealedFaces[i+2]);
positionBuffers.sealed=attribute('position',sealedXYZ,3,gl.FLOAT,false);
originBuffers.sealed=attribute('origin',sealedOrigins,1,gl.UNSIGNED_BYTE,false);
layers.sealed={positions:sealedXYZ,label:'局部封孔表面（推测）',points:{filled:sealPoints,measured:sealRawPoints},
normals:{filled:attribute('normal',normalsFromFaces(sealedXYZ,sealedFaces),3,gl.FLOAT,false),measured:attribute('normal',normalsFromFaces(sealedXYZ,sealRawFaces),3,gl.FLOAT,false)},
indices:{filled:{points:indexBuffer(sealPoints),mesh:indexBuffer(sealedFaces)},measured:{points:indexBuffer(sealRawPoints),mesh:indexBuffer(new Uint32Array(sealRawFaces))}}};
"""
    replace('function geometryKey(){',addition+'\nfunction geometryKey(){')
    replace("return key==='repaired'&&hasRepaired?", "return key==='sealed'?'sealed':key==='repaired'&&hasRepaired?")
    replace("return geometryKey()==='repaired'?repairedOrigins:origins", "return geometryKey()==='sealed'?sealedOrigins:geometryKey()==='repaired'?repairedOrigins:origins")
    replace("originBuffers[key==='repaired'?'repaired':'original']", "originBuffers[key==='sealed'?'sealed':key==='repaired'?'repaired':'original']")
    replace("$('geometry-note').textContent=key==='repaired'?", "$('geometry-note').textContent=key==='sealed'?`固定周围一圈，调整 ${s.surface_sealing.adjusted_existing_display_points.toLocaleString()} 个显示点，补回 ${s.surface_sealing.restored_display_points} 个点。均为局部推测；原始 PL 坐标保留。`:key==='repaired'?")
    counts=report['small_gap_counts'];seconds=report['seconds']
    banner=f'<p class="control-note">小孔（≤16 个网格单元）：{counts["before"]["16"]} → {counts["after"]["16"]}；本次板上修补 {seconds:.2f} 秒。<br>这是当前照片的修补对照，实时拍照仍为稳定版。</p>'
    replace('<aside><details', '<aside>'+banner+'<details')
    replace('<div class="downloads">',f'<div class="downloads"><a class="download" href="surface_sealed.ply" download>下载局部封孔表面 · PLY</a><a class="download" href="{original_url}">打开原稳定照片</a>')
    replace('补洞模式保留原有深度细节，恢复有支持的推测区域；可切换上一版对照。',
            '局部封孔根据周围一圈估计表面，会调整局部显示深度。切回“修补前”可对照原稳定表面。')
    replace("$('download-render').href=saved.url;", "$('download-render').href=new URL(saved.url,location.origin+'/').href;")
    replace('固定照片预览，实时截面控制正在接入。','此页用于修补对照；实时截面请在原稳定照片中操作。')
    if reference_photo:
        replace('此页用于修补对照；实时截面请在原稳定照片中操作。','这是历史照片对照；实时截面请返回实时拍照页面操作。')
    path.write_text(html,encoding='utf8')
    save_ply(out/'surface_sealed.ply',sealed['xyz_mm'],a['rectified_left'][:,:,::-1].copy(),sealed['provenance'],sealed['valid'],sealed['grid_faces'],
             ('A53 boundary-supported inferred display surface. Raw PL geometry is unchanged.',))
    np.savez_compressed(out/'sealed_geometry.npz',**sealed)
    (out/'sealing_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    verified={'passed':True,'photo':photo,'source_sha256':digest,'board_sha256':hashlib.sha256((evidence/(prefix+'_result.npz')).read_bytes()).hexdigest(),
              'exact_board_vs_pc':exact,'production_changed':False,'view':str(path)}
    (evidence/(prefix+'_pc_verified.json')).write_text(json.dumps(verified,indent=2));print(json.dumps(verified))
if __name__=='__main__':main(reference_photo='--reference' in sys.argv)
