"""One-time isolated candidate setup; preserved viewmodes source is read only."""
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def edit(name,changes):
    p=ROOT/name;s=p.read_text(encoding='utf8')
    for old,new in changes:
        assert old in s,(name,old);s=s.replace(old,new)
    p.write_text(s,encoding='utf8')
edit('full_control.html',[
 ('USB 双目 · 按键模式对比 · 320×360','USB 双目 · HDMI 原始视差 · 320×360'),
 ('<a id="report" target="_blank">接收记录</a>', '<a id="report" target="_blank">接收记录</a><button id="rawhdmi">HDMI 显示原始视差</button><button id="hdmipreview">HDMI 返回预览</button>'),
 ('<small>从图像校正开始', '<p>拍照处理完成后，HDMI 自动显示未补全的原始视差，黑色表示无有效匹配。PL_KEY1 返回预览；三维仍使用处理后的视差。</p><small>从图像校正开始'),
 ("$('cancel').onclick", "$('rawhdmi').onclick=()=>action('/api/hdmi/raw',{job_id:showing}).catch(()=>{});\n$('hdmipreview').onclick=()=>action('/api/hdmi/preview',{}).catch(()=>{});\n$('cancel').onclick")])
edit('deploy.py',[("usb320_viewmodes","usb320_rawhdmi")])
s=(ROOT/'deploy_viewmodes_runtime.py').read_text(encoding='utf8')
s=s.replace('switch_viewmodes_board','switch_rawhdmi_board').replace('hdmi_output.py physical_keys.py','hdmi_output.py raw_disparity_hdmi.py physical_keys.py')
(ROOT/'deploy_rawhdmi_runtime.py').write_text(s,encoding='utf8')
s=(ROOT/'switch_viewmodes_board.py').read_text()
s=s.replace('usb320_tonemap','usb320_viewmodes').replace('viewmodes','rawhdmi')
# Restore the previous directory after replacing script/report names.
s=s.replace("OLD=ROOT.parent/'usb320_rawhdmi'","OLD=ROOT.parent/'usb320_viewmodes'")
s=s.replace('from test_rawhdmi import run','from test_rawhdmi import run')
(ROOT/'switch_rawhdmi_board.py').write_text(s)
s=(ROOT/'deploy_viewmodes_update.py').read_text()
s=s.replace("s=Path('/tmp/usb_stereo_probe/usb320_tonemap');d=s.parent/'usb320_viewmodes'", "s=Path('/tmp/usb_stereo_probe/usb320_viewmodes');d=s.parent/'usb320_rawhdmi'")
a=s.index('names=');b=s.index('\nsubprocess.run',a)
s=s[:a]+"names=['raw_disparity_hdmi.py','physical_keys.py','full_camera.py','hdmi_output.py','switch_rawhdmi_board.py','switch_direct3d_board.py','test_rawhdmi.py']"+s[b:]
(ROOT/'deploy_rawhdmi_update.py').write_text(s)
