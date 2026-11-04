"""One-time candidate wiring. Older sources remain preserved."""
from pathlib import Path
ROOT=Path(__file__).resolve().parent
p=ROOT/'full_control.html';s=p.read_text(encoding='utf8')
s=s.replace('USB 双目 · HDMI 原始视差 · 320×360','USB 双目 · 低延迟预览 · 320×360')
s=s.replace('网页刷新 ${document.body.dataset.previewFps', '网页新帧 ${document.body.dataset.previewFps')
start=s.index('let previewFrames=');end=s.index('</script>',start)
s=s[:start]+'''let previewFrames=0,previewWindow=performance.now(),previewWindowFrames=0;
let previewCursor='',previewUrl='';
async function preview(){
 let delay=0;
 if(standby||document.hidden){setTimeout(preview,250);return}
 const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),1800);
 try{
  const r=await fetch('/preview.jpg'+(previewCursor?'?after='+previewCursor:''),{cache:'no-store',signal:controller.signal});
  if(!r.ok)throw Error('Preview unavailable');
  const seq=r.headers.get('X-Frame-Sequence'),epoch=r.headers.get('X-Frame-Epoch'),cursor=seq+','+epoch;
  const blob=await r.blob();
  if(seq===null||epoch===null)throw Error('Frame identity missing');
  if(cursor!==previewCursor){
   const nextUrl=URL.createObjectURL(blob),img=new Image();img.src=nextUrl;
   try{await img.decode()}catch(e){URL.revokeObjectURL(nextUrl);throw e}
   const previous=previewUrl;previewUrl=nextUrl;previewCursor=cursor;$('preview').src=nextUrl;
   if(previous)URL.revokeObjectURL(previous);
   previewFrames++;document.body.dataset.previewFrames=String(previewFrames);
   document.body.dataset.previewSequence=seq;document.body.dataset.previewEpoch=epoch;
   document.body.dataset.boardFrameAgeMs=r.headers.get('X-Frame-Age-Ms');
   const now=performance.now();if(now-previewWindow>=2000){document.body.dataset.previewFps=((previewFrames-previewWindowFrames)*1000/(now-previewWindow)).toFixed(1);previewWindow=now;previewWindowFrames=previewFrames;}
  }else delay=5;
 }catch(e){delay=300;previewCursor=''}finally{clearTimeout(timer);setTimeout(preview,delay)}
}
poll();camera();preview();
'''+s[end:];p.write_text(s,encoding='utf8')
p=ROOT/'deploy.py';p.write_text(p.read_text().replace('usb320_rawhdmi','usb320_lowlatency'))
s=(ROOT/'deploy_rawhdmi_runtime.py').read_text().replace('switch_rawhdmi_board','switch_lowlatency_board')
(ROOT/'deploy_lowlatency_runtime.py').write_text(s)
s=(ROOT/'switch_rawhdmi_board.py').read_text().replace('rawhdmi','lowlatency')
s=s.replace("OLD=ROOT.parent/'usb320_viewmodes'","OLD=ROOT.parent/'usb320_rawhdmi'")
(ROOT/'switch_lowlatency_board.py').write_text(s)
s=(ROOT/'deploy_rawhdmi_update.py').read_text().replace("s=Path('/tmp/usb_stereo_probe/usb320_viewmodes');d=s.parent/'usb320_rawhdmi'", "s=Path('/tmp/usb_stereo_probe/usb320_rawhdmi');d=s.parent/'usb320_lowlatency'")
a=s.index('names=');b=s.index('\nsubprocess.run',a)
s=s[:a]+"names=['full_camera.py','shared_preview.py','hdmi_output.py','switch_lowlatency_board.py','test_lowlatency.py','test_rawhdmi.py']"+s[b:]
(ROOT/'deploy_lowlatency_update.py').write_text(s)
