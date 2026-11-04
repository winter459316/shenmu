import hashlib,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent;OLD=ROOT.parent/'usb_320_autofill'
def edit(name,changes):
    p=ROOT/name;s=p.read_text(encoding='utf8')
    for a,b in changes:
        assert a in s,(name,a[:60]);s=s.replace(a,b)
    p.write_text(s,encoding='utf8')
for name in ('board_dma.py','full_camera.py','physical_keys.py','hdmi_output.py'):
    p=ROOT/name;s=p.read_text(encoding='utf8').replace('/usb320_autofill/','/usb320_dense3d/').replace(':8782',':8784').replace(',8782',',8784').replace(', 8782',', 8784');p.write_text(s,encoding='utf8')
edit('deploy.py',[('/usb320_autofill','/usb320_dense3d')])
edit('transfer_evidence.py',[('usb320_autofill','usb320_dense3d')])
edit('full_host.py',[('PORT=8781','PORT=8783'),(':8782',':8784'),("'surface_preview.ply',","'dense_points.ply','dense_surface.ply','surface_preview.ply',")])
edit('full_control.html',[('板端自动补全','补全视差三维版'),('三维与截面仍使用原稳定流程。','三维默认使用补全视差；截面仍使用原始坐标，可切回上一版表面对照。'),("names.dense_fill=","names.dense_geometry='PL 生成全填充点云 / A53 连面';names.dense_fill=")])
s=(ROOT/'switch_autofill_board.py').read_text(encoding='utf8').replace('autofill','dense3d').replace('8782','8784').replace('8768','8782').replace("ROOT.parent/'usb320'","ROOT.parent/'usb320_autofill'").replace('dense_replay_verified.json','dense_geometry_replay_verified.json')
(ROOT/'switch_dense3d_board.py').write_text(s,encoding='utf8')
p=ROOT/'pointcloud_viewer.html';s=p.read_text(encoding='utf8')
def replace(a,b):
    global s
    assert s.count(a)==1,(a[:100],s.count(a));s=s.replace(a,b)
replace('<option value="repaired" selected>补洞表面（保留细节）</option>','<option value="dense" selected>全填充视差表面（含推测）</option><option value="repaired">上一版表面（对照）</option>')
replace('let xyz=originalXYZ;',"const originalValid=decode(data.original_valid,Uint8Array),denseXYZ=decode(data.dense_positions,Float32Array),denseOrigins=decode(data.dense_origins,Uint8Array),denseFaces=decode(data.dense_faces,Uint32Array);\nlet xyz=originalXYZ;")
replace('rawPointIndices=allPointIndices.filter(i=>origins[i]===0);','originalPointIndices=allPointIndices.filter(i=>originalValid[i]),rawPointIndices=originalPointIndices.filter(i=>origins[i]===0);')
replace('const indices={filled:{points:indexBuffer(allPointIndices)','const indices={filled:{points:indexBuffer(originalPointIndices)')
replace("points:{filled:allPointIndices,measured:rawPointIndices},label:'未优化'","points:{filled:originalPointIndices,measured:rawPointIndices},label:'未优化'")
addition="""
layers.repaired.label='上一版表面';
const denseRawPoints=allPointIndices.filter(i=>denseOrigins[i]===0),denseRawFaces=[];
for(let i=0;i<denseFaces.length;i+=3)if(denseOrigins[denseFaces[i]]===0&&denseOrigins[denseFaces[i+1]]===0&&denseOrigins[denseFaces[i+2]]===0)denseRawFaces.push(denseFaces[i],denseFaces[i+1],denseFaces[i+2]);
positionBuffers.dense=attribute('position',denseXYZ,3,gl.FLOAT,false);originBuffers.dense=attribute('origin',denseOrigins,1,gl.UNSIGNED_BYTE,false);
layers.dense={positions:denseXYZ,label:'全填充视差表面',points:{filled:allPointIndices,measured:denseRawPoints},
normals:{filled:attribute('normal',normalsFromFaces(denseXYZ,denseFaces),3,gl.FLOAT,false),measured:attribute('normal',normalsFromFaces(denseXYZ,denseRawFaces),3,gl.FLOAT,false)},
indices:{filled:{points:indexBuffer(allPointIndices),mesh:indexBuffer(denseFaces)},measured:{points:indexBuffer(denseRawPoints),mesh:indexBuffer(new Uint32Array(denseRawFaces))}}};
"""
replace('function geometryKey(){',addition+'\nfunction geometryKey(){')
replace("return key==='repaired'&&hasRepaired?","return key==='dense'?'dense':key==='repaired'&&hasRepaired?")
replace("return geometryKey()==='repaired'?repairedOrigins:origins","return geometryKey()==='dense'?denseOrigins:geometryKey()==='repaired'?repairedOrigins:origins")
replace("originBuffers[key==='repaired'?'repaired':'original']","originBuffers[key==='dense'?'dense':key==='repaired'?'repaired':'original']")
replace("$('geometry-note').textContent=key==='repaired'?","$('geometry-note').textContent=key==='dense'?'115,200 个PL投影点、229,042 个三角面，全部网格单元连面；含外推，可能连接真实前后景。':key==='repaired'?")
replace('补洞模式保留原有深度细节，恢复有支持的推测区域；可切换上一版对照。','全填充模式用补全视差生成PL点云与完整网格，包含推测并可能跨接前后景；可切换上一版表面对照。')
replace('<div class="downloads">','<div class="downloads"><a class="download" href="dense_surface.ply" download>下载全填充表面 · PLY</a><a class="download" href="dense_points.ply" download>下载全填充点云 · PLY</a>')
s=s.replace("${usingOptimized()?'显示坐标已降噪':'原始坐标'}","${geometryKey()==='dense'?'补全视差PL投影':usingOptimized()?'显示坐标已降噪':'原始坐标'}")
s=s.replace('截面使用 PL 原坐标，不随视图旋转或显示降噪改变。','截面始终使用上一版 PL 原坐标；全填充视差层仅用于点云和表面显示，高亮点采用原截面坐标。')
p.write_text(s,encoding='utf8')
files=[p for p in OLD.iterdir() if p.is_file() and p.suffix in ('.py','.dll','.so','.html','.json','.npz','.bin','.txt')]
manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files};(ROOT/'PRESERVED_AUTOFILL_SHA256.json').write_text(json.dumps(manifest,indent=2))
latest=json.loads((OLD/'live_latest.json').read_text());photo=OLD/'live_captures'/latest['job_id']
archive=ROOT/'before_dense3d_autofill_complete.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=3) as z:
    hashes={}
    for p in files+list(photo.iterdir()):
        if not p.is_file():continue
        n=p.relative_to(OLD).as_posix();z.write(p,n);hashes[n]=hashlib.sha256(p.read_bytes()).hexdigest()
    z.writestr('SHA256.json',json.dumps(hashes,indent=2))
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    for n,h in hashes.items():assert hashlib.sha256(z.read(n)).hexdigest()==h
(ROOT/'PREVIOUS_VERSION_BACKUP.json').write_text(json.dumps({'path':str(archive),'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'files':len(hashes),'job':latest['job_id'],'verified':True},indent=2))
print('AUTOFILL_BACKUP_PASS',len(hashes),latest['job_id'])
