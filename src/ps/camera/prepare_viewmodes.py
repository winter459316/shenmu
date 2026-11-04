import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent;OLD=ROOT.parent/'usb_320_tonemap'
record={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OLD.iterdir() if p.is_file() and p.suffix in ('.py','.html','.so','.dll','.npz','.bin')}
(ROOT/'PRESERVED_TONEMAP_SHA256.json').write_text(json.dumps(record,indent=2))
def edit(name,changes):
    p=ROOT/name;s=p.read_text(encoding='utf8')
    for old,new in changes:
        assert old in s,(name,old);s=s.replace(old,new)
    p.write_text(s,encoding='utf8')
edit('preview_rectify.py',[("MODES=('color','rectified','gray','median','sobel')","MODES=('color','auto_enhanced','rectified','gray','median','sobel')")])
edit('physical_keys.py',[("MODES=('color','rectified','gray','median','sobel')","from preview_rectify import MODES")])
edit('shared_preview.py',[
 ('def render(self,frame,sequence,mode,tone_enabled=True):','def render(self,frame,sequence,mode):'),
 ('            if tone_enabled:\n                t=time.monotonic();grid=tone_map(grid);tone_seconds=time.monotonic()-t\n',''),
 ("if tone_enabled and mode!='sobel':","if mode=='auto_enhanced':"),
 ("if mode!='color':","if mode not in ('color','auto_enhanced'):")])
edit('full_camera.py',[
 ('        self.tone_enabled=True\n',''),
 ('''        with self.ready:
            if self.tone_enabled!=enabled:
                self.tone_enabled=enabled;self.epoch+=1;self.packet=None;self.jpeg=None
                self.wake.set();self.ready.notify_all()''',"        self.set_mode('auto_enhanced' if enabled else 'color')"),
 ('                tone_enabled=self.tone_enabled\n',''),
 ('self.processor.render(frame,seq,mode,tone_enabled)','self.processor.render(frame,seq,mode)'),
 ("dict(tone_description(self.tone_enabled),applied=self.tone_enabled and self.mode!='sobel')","dict(tone_description(self.mode=='auto_enhanced'),applied=self.mode=='auto_enhanced')")])
edit('hdmi_output.py',[("'USB STEREO | '+mode.upper()+' | '+state['stage']","'USB STEREO | '+{'color':'COLOR ORIGINAL','auto_enhanced':'AUTO EXPOSURE + SHADOW LIFT'}.get(mode,mode.upper())+' | '+state['stage']")])
edit('full_host.py',[("PORT=8799;","PORT=8801;"),("('color','rectified','gray','median','sobel')","('color','auto_enhanced','rectified','gray','median','sobel')")])
edit('full_control.html',[
 ('USB 双目 · 暗部增强 · 320×360','USB 双目 · 按键模式对比 · 320×360'),
 ('自动曝光＋暗部提亮 · 高光柔和压缩 · 左右共用亮度曲线','PL_KEY1：原始彩色 → 自动曝光增强 → 校正 → 灰度 → 中值 → 边缘'),
 ('<option value="color">彩色</option>','<option value="color">彩色（原始）</option><option value="auto_enhanced">自动曝光增强（暗部提亮）</option>'),
 ('<label><input id="tone" type="checkbox" checked> 暗部提亮＋高光压缩</label>\n',''),
 ('作用于网页和 HDMI 预览；取消勾选可对照原画面。匹配输入和旧照片保持原样。','原始彩色和增强模式都保留摄像头自动曝光；增强模式另加暗部提亮、高光压缩，仅作用于预览。'),
 ("let tonePending=false;\n$('tone').onchange=async()=>{tonePending=true;$('tone').disabled=true;try{const s=await action('/api/tone',{enabled:$('tone').checked});$('tone').checked=s.tone_map.enabled}catch(e){$('tone').checked=!$('tone').checked}finally{tonePending=false;$('tone').disabled=false}};\n",''),
 ("if(!tonePending)$('tone').checked=!!s.tone_map?.enabled;\n",''),
 ("$('tone_status').textContent=s.mode==='sobel'?'边缘模式保持原计算；切回彩色或校正画面查看提亮效果。':'原始彩色和增强模式都保留摄像头自动曝光；增强模式另加暗部提亮、高光压缩，仅作用于预览。';", "$('tone_status').textContent=s.mode==='auto_enhanced'?'当前：自动曝光增强。网页和 HDMI 同步提亮暗部、压缩高光。':'当前为原始预览处理。PL_KEY1 在原始彩色之后切换到自动曝光增强。';")])
edit('deploy.py',[('/usb320_tonemap','/usb320_viewmodes')])
# Adapt the reviewed warm switch; photo algorithms are still byte-identical.
p=ROOT/'switch_viewmodes_board.py';p.write_text((ROOT/'switch_tone_board.py').read_text(),encoding='utf8')
edit(p.name,[("OLD=ROOT.parent/'usb320_exposure'","OLD=ROOT.parent/'usb320_tonemap'"),
 ("tone_private_snapshot.json","viewmodes_private_snapshot.json"),
 ("'rectification_maps.npz','physical_keys.py','hdmi_output.py'","'rectification_maps.npz'"),
 ('from test_tone import run','from test_viewmodes import run'),
 ('tone_tests.json','viewmodes_tests.json'),('tone_activation.json','viewmodes_activation.json'),
 ("'mode':request(8788,'/status')['mode']","'mode':request(8788,'/status')['mode'],'tone':request(8788,'/status')['tone_map']['enabled']"),
 ("report=start_services(OLD,8788,saved,True)\n", "report=start_services(OLD,8788,saved,True)\n    request(8788,'/preview/tone',{'enabled':saved['tone']})\n")])
for p in ROOT.glob('*.py'):compile(p.read_text(encoding='utf8'),str(p),'exec')
print('Six modes prepared; original tone-map source preserved.')
