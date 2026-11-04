import hashlib,json,zipfile,datetime
from pathlib import Path
ROOT=Path(__file__).resolve().parent;OLD=ROOT.parent/'usb_320'
def rewrite(name,changes):
    p=ROOT/name;s=p.read_text(encoding='utf8')
    for old,new in changes:s=s.replace(old,new)
    p.write_text(s,encoding='utf8')
for name in ('board_dma.py','full_camera.py','physical_keys.py','hdmi_output.py'):
    rewrite(name,[('/usb320/','/usb320_autofill/'),(':8768',':8782'),(',8768',',8782'),(', 8768',', 8782')])
rewrite('deploy.py',[('/usb320_hybrid','/usb320_autofill')])
rewrite('full_host.py',[('PORT=8776','PORT=8781'),(':8777',':8782'),("a['hybrid_origin']","a['dense_origin']"),
                       ("valid=bool(a['valid'][y,x])","valid=True"),("a['depth_mm'][y,x]","a['dense_depth_mm'][y,x]"),
                       ("float(a['disparity_q4'][y,x])/16","float(a['dense_disparity_px'][y,x])")])
rewrite('full_control.html',[('PS+PL精细匹配','板端自动补全'),('PL 立体匹配、补全与点云 · A53 HH精细匹配与表面处理 · 电脑验证和显示','PL 匹配与点云 · A53 自动填满视差空洞 · 电脑验证显示'),
('黑色无效点不补洞。','所有空洞均补值；原始匹配与推测区域单独记录。三维与截面仍使用原稳定流程。'),
('光轴深度 ${v.depth_m.toFixed(3)} m，视差 ${v.disparity_px.toFixed(2)} px','光轴深度 ${v.depth_m.toFixed(3)} m，视差 ${v.disparity_px.toFixed(2)} px；${[\'原始匹配\',\'邻近推测\',\'远处/边界推测\'][v.origin]}'),
("names.ps_precision_matching=", "names.dense_fill='A53 全视差空洞补全';names.verify_dense_fill='校验补全数值与来源';names.ps_precision_matching=")])
rewrite('switch_autofill_board.py',[('hybrid','autofill'),('8777','8782'),
("    proof=json.loads((ROOT/'replay_pc_verified.json').read_text());assert proof['passed']\n    assert proof['sha256']==hashlib.sha256((ROOT/'pipeline_320_result.npz').read_bytes()).hexdigest()\n    assert json.loads((ROOT/'completion_320_reference.json').read_text())['pl_cpu_completion_bit_exact']",
 "    proof=json.loads((ROOT/'dense_replay_verified.json').read_text());assert proof['passed'] and proof['cancel_passed']\n    assert proof['bitstream_sha256']==BIT")])
files=[p for p in OLD.iterdir() if p.is_file() and p.suffix in ('.py','.dll','.so','.html','.json','.npz','.bin','.txt')]
manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
(ROOT/'STABLE_SOURCE_SHA256.json').write_text(json.dumps(manifest,indent=2))
backup=ROOT/'stable_before_autofill.zip'
with zipfile.ZipFile(backup,'w',zipfile.ZIP_DEFLATED,compresslevel=3) as z:
    for p in files:z.write(p,p.name)
    z.writestr('SHA256.json',json.dumps(manifest,indent=2))
with zipfile.ZipFile(backup) as z:
    assert z.testzip() is None
    for n,sha in manifest.items():assert hashlib.sha256(z.read(n)).hexdigest()==sha
(ROOT/'STABLE_BACKUP.json').write_text(json.dumps({'path':str(backup),'sha256':hashlib.sha256(backup.read_bytes()).hexdigest(),'files':len(files),'verified':True},indent=2))
print('STABLE_BACKUP_VERIFIED',len(files))
